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

/// Counts every request that crosses the weighbridge, on any route.
struct Weighbridge {
    weighed: Arc<AtomicUsize>,
}

struct WeighbridgeService<S> {
    inner: S,
    weighed: Arc<AtomicUsize>,
}

#[async_trait]
impl<S> Service for WeighbridgeService<S>
where
    S: Service<Error = Infallible> + Send + Sync + 'static,
{
    type Error = Infallible;

    async fn call(&self, req: ServiceRequest) -> Result<ServiceResponse, Infallible> {
        self.weighed.fetch_add(1, Ordering::Relaxed);
        self.inner.call(req).await
    }
}

#[async_trait]
impl<E: Packet> Transform<HandlerService<E>> for Weighbridge {
    type Output = HandlerService<E>;

    async fn transform(&self, service: HandlerService<E>) -> Self::Output {
        let id = service.id();
        let weighed = Arc::clone(&self.weighed);
        HandlerService::from_service(
            id,
            WeighbridgeService {
                inner: service,
                weighed,
            },
        )
    }
}

#[derive(bincode::Encode, bincode::BorrowDecode)]
struct ManifestV1 {
    id: u64,
    name: String,
}

#[derive(bincode::Encode, bincode::BorrowDecode, Debug, PartialEq)]
struct ManifestV2 {
    id: u64,
    display_name: String,
}

/// Rewrites version 1 manifests so handlers only ever see version 2.
struct UpgradeManifests;

struct UpgradeService<S> {
    inner: S,
}

#[async_trait]
impl<S> Service for UpgradeService<S>
where
    S: Service<Error = Infallible> + Send + Sync + 'static,
{
    type Error = Infallible;

    async fn call(&self, mut req: ServiceRequest) -> Result<ServiceResponse, Infallible> {
        if ManifestV2::from_bytes(req.frame()).is_err() {
            if let Ok((v1, _)) = ManifestV1::from_bytes(req.frame()) {
                let v2 = ManifestV2 {
                    id: v1.id,
                    display_name: v1.name,
                };
                *req.frame_mut() = v2.to_bytes().expect("encode ManifestV2");
            }
        }
        self.inner.call(req).await
    }
}

#[async_trait]
impl Transform<HandlerService<Envelope>> for UpgradeManifests {
    type Output = HandlerService<Envelope>;

    async fn transform(&self, service: HandlerService<Envelope>) -> Self::Output {
        let id = service.id();
        HandlerService::from_service(id, UpgradeService { inner: service })
    }
}

#[derive(Default)]
struct Shift {
    opened: AtomicUsize,
}

type ShiftApp = WireframeApp<BincodeSerializer, Shift, Envelope>;

fn yard(weighed: Arc<AtomicUsize>, closed: Arc<AtomicUsize>) -> wireframe::Result<ShiftApp> {
    let manifests: Handler<Envelope> = Arc::new(|_: &Envelope| Box::pin(async {}));
    let app: WireframeApp = WireframeApp::new()?
        .route(5, manifests)?
        .wrap(UpgradeManifests)?
        .wrap(Weighbridge { weighed })?;
    let app = app
        .on_connection_setup(|| async {
            let shift = Shift::default();
            shift.opened.fetch_add(1, Ordering::Relaxed);
            shift
        })?
        .on_connection_teardown(move |shift: Shift| {
            let closed = Arc::clone(&closed);
            async move {
                closed.fetch_add(shift.opened.load(Ordering::Relaxed), Ordering::Relaxed);
            }
        })?;
    Ok(app)
}

#[tokio::test]
async fn handlers_only_ever_see_version_two() {
    let weighed = Arc::new(AtomicUsize::new(0));
    let closed = Arc::new(AtomicUsize::new(0));
    let app = yard(Arc::clone(&weighed), Arc::clone(&closed)).expect("configure");

    let legacy = ManifestV1 {
        id: 7,
        name: "coal".into(),
    };
    let request = Envelope::new(5, Some(1), legacy.to_bytes().expect("encode"));
    let wire = BincodeSerializer.serialize(&request).expect("encode");

    let codec = LengthDelimitedFrameCodec::new(1024);
    let chunk = NonZeroUsize::new(16).expect("non-zero");
    let replies = drive_with_partial_frames(app, &codec, vec![wire], chunk)
        .await
        .expect("the app answers");

    let (reply, _): (Envelope, usize) = BincodeSerializer.deserialize(&replies[0]).expect("decode");
    let (manifest, _) = ManifestV2::from_bytes(reply.payload_bytes()).expect("version 2");
    assert_eq!(
        manifest,
        ManifestV2 {
            id: 7,
            display_name: "coal".into()
        }
    );
    assert_eq!(weighed.load(Ordering::Relaxed), 1);
    assert_eq!(
        closed.load(Ordering::Relaxed),
        1,
        "teardown received the setup state"
    );
}
