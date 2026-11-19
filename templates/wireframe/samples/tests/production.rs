//! Running in production: workers, backoff, timeouts, shutdown, metrics.

use std::{io, time::Duration};

use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpStream,
    sync::oneshot,
};
use wireframe::{
    app::WireframeApp,
    metrics,
    server::{BackoffConfig, ServerError, WireframeServer},
};

fn app() -> WireframeApp {
    WireframeApp::new().expect("builder").read_timeout_ms(250)
}

#[tokio::test]
async fn the_server_stops_when_asked() {
    // ANCHOR: server
    let backoff = BackoffConfig {
        initial_delay: Duration::from_millis(10),
        max_delay: Duration::from_secs(1),
    };
    let server = WireframeServer::new(app)
        .workers(4)
        .accept_backoff(backoff)
        .bind("127.0.0.1:0".parse().expect("a socket address"))
        .expect("bind");
    assert_eq!(server.worker_count(), 4);

    let (stop, stopped) = oneshot::channel::<()>();
    let running = tokio::spawn(server.run_with_shutdown(async {
        let _ = stopped.await;
    }));

    stop.send(()).expect("the server is listening for shutdown");
    running
        .await
        .expect("the server task joins")
        .expect("a clean stop");
    // ANCHOR_END: server
}

#[tokio::test]
async fn shutdown_needs_a_deadline_of_your_own() {
    let server = WireframeServer::new(app)
        .bind("127.0.0.1:0".parse().expect("a socket address"))
        .expect("bind");
    let addr = server.local_addr().expect("a bound address");
    let shutdown = server.spawn().await.expect("the application prepares");

    // A client that connects, sends one byte, and then says nothing more.
    let mut quiet = TcpStream::connect(addr).await.expect("connect");
    quiet.write_all(&[0]).await.expect("a first byte");
    tokio::time::sleep(Duration::from_millis(50)).await;

    // ANCHOR: drain
    shutdown.stop();
    let drained = tokio::time::timeout(Duration::from_millis(200), shutdown.drained()).await;
    // ANCHOR_END: drain
    assert!(drained.is_err(), "an open connection holds up the drain");

    drop(quiet);
    shutdown
        .drained()
        .await
        .expect("a clean stop once it leaves");
}

#[tokio::test]
async fn a_failing_factory_stops_the_server_starting() {
    // ANCHOR: factory
    fn fallible_app() -> Result<WireframeApp, io::Error> {
        Err(io::Error::other("no configuration"))
    }

    let server = WireframeServer::new(fallible_app)
        .bind("127.0.0.1:0".parse().expect("a socket address"))
        .expect("bind");
    let refused = server.spawn().await;
    assert!(matches!(refused, Err(ServerError::FactoryBuild(_))));
    // ANCHOR_END: factory
}

#[tokio::test]
async fn a_silent_client_is_disconnected_at_the_deadline() {
    let server = WireframeServer::new(app)
        .preamble_timeout(Duration::from_millis(50))
        .bind("127.0.0.1:0".parse().expect("a socket address"))
        .expect("bind");
    let addr = server.local_addr().expect("a bound address");
    let shutdown = server.spawn().await.expect("the application prepares");

    // No preamble is configured, but the server still reads a first byte.
    let mut silent = TcpStream::connect(addr).await.expect("connect");
    let mut buffer = Vec::new();
    tokio::time::timeout(Duration::from_secs(5), silent.read_to_end(&mut buffer))
        .await
        .expect("the server hangs up without being asked")
        .expect("a clean close");
    assert!(buffer.is_empty(), "the server never speaks first");

    shutdown.stop();
    shutdown.drained().await.expect("a clean stop");
}

#[test]
fn metric_names_are_public_constants() {
    // ANCHOR: metrics
    assert_eq!(
        metrics::FRAMES_PROCESSED,
        "wireframe_frames_processed_total"
    );
    assert_eq!(
        metrics::DECODE_REJECTIONS,
        "wireframe_decode_rejections_total"
    );
    // ANCHOR_END: metrics
}
