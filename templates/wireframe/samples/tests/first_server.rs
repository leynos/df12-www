//! Getting started: route one message, answer it, and call it.

use std::{convert::Infallible, error::Error, net::SocketAddr, sync::Arc};

use async_trait::async_trait;
use wireframe::{
    app::{Envelope, Handler, Packet, WireframeApp},
    client::WireframeClient,
    message::Message,
    middleware::{HandlerService, Service, ServiceRequest, ServiceResponse, Transform},
    server::{ServerShutdown, WireframeServer},
};

// ANCHOR: messages
#[derive(bincode::Encode, bincode::BorrowDecode, Debug)]
struct Ping {
    body: String,
}

#[derive(bincode::Encode, bincode::BorrowDecode, Debug, PartialEq)]
struct Pong {
    body: String,
}

const PING: u32 = 1;
// ANCHOR_END: messages

// ANCHOR: middleware
/// Middleware that answers every `Ping` with a `Pong`.
struct AnswerPings;

struct AnswerPingsService<S> {
    inner: S,
}

#[async_trait]
impl<S> Service for AnswerPingsService<S>
where
    S: Service<Error = Infallible> + Send + Sync + 'static,
{
    type Error = Infallible;

    async fn call(&self, req: ServiceRequest) -> Result<ServiceResponse, Infallible> {
        let ping = Ping::from_bytes(req.frame()).map(|(msg, _)| msg).ok();
        let mut response = self.inner.call(req).await?;
        if let Some(ping) = ping {
            let pong = Pong {
                body: format!("pong {}", ping.body),
            };
            *response.frame_mut() = pong.to_bytes().expect("encode Pong");
        }
        Ok(response)
    }
}

#[async_trait]
impl Transform<HandlerService<Envelope>> for AnswerPings {
    type Output = HandlerService<Envelope>;

    async fn transform(&self, service: HandlerService<Envelope>) -> Self::Output {
        let id = service.id();
        HandlerService::from_service(id, AnswerPingsService { inner: service })
    }
}
// ANCHOR_END: middleware

// ANCHOR: app
fn build_app() -> wireframe::Result<WireframeApp> {
    let handler: Handler<Envelope> = Arc::new(|env: &Envelope| {
        let id = env.id();
        Box::pin(async move { println!("routed message {id}") })
    });

    WireframeApp::new()?.route(PING, handler)?.wrap(AnswerPings)
}
// ANCHOR_END: app

// ANCHOR: serve
async fn serve() -> Result<(SocketAddr, ServerShutdown), Box<dyn Error>> {
    let server = WireframeServer::from_app(build_app()?)
        .workers(2)
        .bind("127.0.0.1:0".parse()?)?;
    let addr = server.local_addr().expect("a bound address");

    let shutdown = server.spawn().await?;
    Ok((addr, shutdown))
}
// ANCHOR_END: serve

// ANCHOR: call
async fn call(addr: SocketAddr) -> Result<Pong, Box<dyn Error>> {
    let mut client = WireframeClient::builder().connect(addr).await?;

    let ping = Ping {
        body: "from the scope".into(),
    };
    let request = Envelope::new(PING, None, ping.to_bytes()?);
    let response: Envelope = client.call_correlated(request).await?;

    let (pong, _) = Pong::from_bytes(response.payload_bytes())?;
    client.close().await;
    Ok(pong)
}
// ANCHOR_END: call

#[tokio::test]
async fn a_ping_comes_back_as_a_pong() {
    let (addr, shutdown) = serve().await.expect("server starts");
    let pong = call(addr).await.expect("the call succeeds");
    assert_eq!(
        pong,
        Pong {
            body: "pong from the scope".into()
        }
    );
    // ANCHOR: stop
    shutdown.stop();
    shutdown.drained().await.expect("a clean stop");
    // ANCHOR_END: stop
}
