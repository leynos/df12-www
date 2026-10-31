//! Running in production: workers, backoff, timeouts, shutdown, metrics.

use std::time::Duration;

use tokio::sync::oneshot;
use wireframe::{
    app::WireframeApp,
    metrics,
    server::{BackoffConfig, WireframeServer},
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

#[test]
fn metric_names_are_public_constants() {
    // ANCHOR: metrics
    assert_eq!(metrics::CONNECTIONS_ACTIVE, "wireframe_connections_active");
    assert_eq!(
        metrics::FRAMES_PROCESSED,
        "wireframe_frames_processed_total"
    );
    assert_eq!(metrics::CODEC_ERRORS, "wireframe_codec_errors_total");
    // ANCHOR_END: metrics
}
