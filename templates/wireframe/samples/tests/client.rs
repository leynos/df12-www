//! The client runtime: hooks, correlated calls, and pools.

use std::{
    net::SocketAddr,
    sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    },
    time::Duration,
};

use wireframe::{
    app::{Envelope, Handler, WireframeApp},
    client::{
        ClientCodecConfig, ClientError, ClientPoolConfig, PoolFairnessPolicy, SocketOptions,
        WireframeClient,
    },
    correlation::CorrelatableFrame,
    server::WireframeServer,
};

async fn echo_server() -> SocketAddr {
    let factory = || -> WireframeApp {
        let echo: Handler<Envelope> = Arc::new(|_: &Envelope| Box::pin(async {}));
        WireframeApp::new()
            .and_then(|app| app.route(1, echo))
            .expect("an echo app")
    };
    let server = WireframeServer::new(factory)
        .bind("127.0.0.1:0".parse().expect("a socket address"))
        .expect("bind");
    let addr = server.local_addr().expect("a bound address");
    tokio::spawn(server.run_with_shutdown(tokio::time::sleep(Duration::from_secs(10))));
    addr
}

#[tokio::test]
async fn a_correlated_call_comes_back_stamped() {
    let addr = echo_server().await;
    let sent = Arc::new(AtomicUsize::new(0));
    let counter = Arc::clone(&sent);

    // ANCHOR: call
    let mut client = WireframeClient::builder()
        .codec_config(ClientCodecConfig::default().max_frame_length(1024))
        .socket_options(SocketOptions::default().nodelay(true))
        .before_send(move |_bytes: &mut Vec<u8>| {
            counter.fetch_add(1, Ordering::Relaxed);
        })
        .connect(addr)
        .await
        .expect("connect");

    let request = Envelope::new(1, None, b"vector".to_vec());
    let reply: Envelope = client.call_correlated(request).await.expect("a reply");

    assert!(reply.correlation_id().is_some());
    // ANCHOR_END: call
    assert_eq!(reply.payload_bytes(), b"vector");
    assert_eq!(sent.load(Ordering::Relaxed), 1);
    client.close().await;
}

#[tokio::test]
async fn a_pool_reuses_its_sockets() {
    let addr = echo_server().await;
    // ANCHOR: pool
    let pool = WireframeClient::builder()
        .connect_pool(
            addr,
            ClientPoolConfig::default()
                .pool_size(2)
                .max_in_flight_per_socket(2)
                .max_waiters(8)
                .idle_timeout(Duration::from_secs(30))
                .fairness_policy(PoolFairnessPolicy::RoundRobin),
        )
        .await
        .expect("a pool");

    let lease = pool.acquire().await.expect("a lease");
    let request = Envelope::new(1, Some(5), b"blank".to_vec());
    let reply: Envelope = lease.call(&request).await.expect("a reply");
    assert_eq!(reply.payload_bytes(), b"blank");
    // ANCHOR_END: pool

    drop(lease);
    pool.close().await;
}

#[tokio::test]
async fn a_pool_opens_its_sockets_on_first_use() {
    // A port that was free a moment ago and has nothing listening now.
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind");
    let addr = listener.local_addr().expect("an address");
    drop(listener);

    let pool = WireframeClient::builder()
        .connect_pool(addr, ClientPoolConfig::default())
        .await
        .expect("no socket is opened yet, so the pool builds");
    let lease = pool.acquire().await.expect("a lease");

    let request = Envelope::new(1, Some(5), b"blank".to_vec());
    // The pool retries until its 30-second checkout timeout, so this takes that
    // long, and the failure names the timeout rather than the refused connection.
    let refused: Result<Envelope, ClientError> = lease.call(&request).await;
    let reason = refused.expect_err("nothing is listening").to_string();
    assert!(reason.contains("timed out"), "{reason}");

    drop(lease);
    let mut handle = pool.handle();
    pool.close().await;
    assert!(matches!(
        handle.acquire().await,
        Err(ClientError::PoolClosed)
    ));
}
