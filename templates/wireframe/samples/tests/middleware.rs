//! Middleware and lifecycle hooks.

use std::{
    convert::Infallible,
    num::NonZeroUsize,
    sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    },
};

use async_trait::async_trait;
use wireframe::{
    app::{Envelope, Handler, Packet, WireframeApp},
    codec::LengthDelimitedFrameCodec,
    message::Message,
    middleware::{HandlerService, Service, ServiceRequest, ServiceResponse, Transform},
    serializer::{BincodeSerializer, Serializer},
    testkit::drive_with_partial_frames,
};

// ANCHOR: tally
/// Counts every request that passes through, on any route.
struct Tally {
    tallied: Arc<AtomicUsize>,
}

struct TallyService<S> {
    inner: S,
    tallied: Arc<AtomicUsize>,
}

#[async_trait]
impl<S> Service for TallyService<S>
where
    S: Service<Error = Infallible> + Send + Sync + 'static,
{
    type Error = Infallible;

    async fn call(&self, req: ServiceRequest) -> Result<ServiceResponse, Infallible> {
        self.tallied.fetch_add(1, Ordering::Relaxed);
        self.inner.call(req).await
    }
}

#[async_trait]
impl<E: Packet> Transform<HandlerService<E>> for Tally {
    type Output = HandlerService<E>;

    async fn transform(&self, service: HandlerService<E>) -> Self::Output {
        let id = service.id();
        let tallied = Arc::clone(&self.tallied);
        HandlerService::from_service(
            id,
            TallyService {
                inner: service,
                tallied,
            },
        )
    }
}
// ANCHOR_END: tally

#[derive(bincode::Encode, bincode::BorrowDecode)]
struct PointV1 {
    id: u64,
    name: String,
}

/// Version 2 added beam intensity, so a version 1 payload is too short to
/// decode as version 2.
#[derive(bincode::Encode, bincode::BorrowDecode, Debug, PartialEq)]
struct PointV2 {
    id: u64,
    display_name: String,
    intensity: u32,
}

/// Rewrites version 1 points so handlers only ever see version 2.
struct UpgradePoints;

struct UpgradeService<S> {
    inner: S,
}

#[async_trait]
impl<S> Service for UpgradeService<S>
where
    S: Service<Error = Infallible> + Send + Sync + 'static,
{
    type Error = Infallible;

    // ANCHOR: upgrade
    async fn call(&self, mut req: ServiceRequest) -> Result<ServiceResponse, Infallible> {
        if PointV2::from_bytes(req.frame()).is_err() {
            if let Ok((v1, _)) = PointV1::from_bytes(req.frame()) {
                let v2 = PointV2 {
                    id: v1.id,
                    display_name: v1.name,
                    intensity: 0,
                };
                *req.frame_mut() = v2.to_bytes().expect("encode PointV2");
            }
        }
        self.inner.call(req).await
    }
    // ANCHOR_END: upgrade
}

#[async_trait]
impl Transform<HandlerService<Envelope>> for UpgradePoints {
    type Output = HandlerService<Envelope>;

    async fn transform(&self, service: HandlerService<Envelope>) -> Self::Output {
        let id = service.id();
        HandlerService::from_service(id, UpgradeService { inner: service })
    }
}

#[derive(Default)]
struct Link {
    opened: AtomicUsize,
}

type LinkApp = WireframeApp<BincodeSerializer, Link, Envelope>;

fn scope(tallied: Arc<AtomicUsize>, closed: Arc<AtomicUsize>) -> wireframe::Result<LinkApp> {
    let points: Handler<Envelope> = Arc::new(|_: &Envelope| Box::pin(async {}));
    let app: WireframeApp = WireframeApp::new()?
        .route(5, points)?
        .wrap(UpgradePoints)?
        .wrap(Tally { tallied })?;
    // ANCHOR: lifecycle
    let app = app
        .on_connection_setup(|| async {
            let link = Link::default();
            link.opened.fetch_add(1, Ordering::Relaxed);
            link
        })?
        .on_connection_teardown(move |link: Link| {
            let closed = Arc::clone(&closed);
            async move {
                closed.fetch_add(link.opened.load(Ordering::Relaxed), Ordering::Relaxed);
            }
        })?;
    // ANCHOR_END: lifecycle
    Ok(app)
}

#[tokio::test]
async fn handlers_only_ever_see_version_two() {
    let tallied = Arc::new(AtomicUsize::new(0));
    let closed = Arc::new(AtomicUsize::new(0));
    let app = scope(Arc::clone(&tallied), Arc::clone(&closed)).expect("configure");

    let legacy = PointV1 {
        id: 7,
        name: "origin".into(),
    };
    let legacy_bytes = legacy.to_bytes().expect("encode");
    assert!(
        PointV2::from_bytes(&legacy_bytes).is_err(),
        "a version 1 payload must not pass as version 2"
    );
    let request = Envelope::new(5, Some(1), legacy_bytes);
    let wire = BincodeSerializer.serialize(&request).expect("encode");

    let codec = LengthDelimitedFrameCodec::new(1024);
    let chunk = NonZeroUsize::new(16).expect("non-zero");
    let replies = drive_with_partial_frames(app, &codec, vec![wire], chunk)
        .await
        .expect("the app answers");

    let (reply, _): (Envelope, usize) = BincodeSerializer.deserialize(&replies[0]).expect("decode");
    let (point, _) = PointV2::from_bytes(reply.payload_bytes()).expect("version 2");
    assert_eq!(
        point,
        PointV2 {
            id: 7,
            display_name: "origin".into(),
            intensity: 0,
        }
    );
    assert_eq!(tallied.load(Ordering::Relaxed), 1);
    assert_eq!(
        closed.load(Ordering::Relaxed),
        1,
        "teardown received the setup state"
    );
}
