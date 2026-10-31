//! A connection preamble, validated before any frame is read.

use std::{net::SocketAddr, time::Duration};

use futures::FutureExt;
use tokio::{io::AsyncWriteExt, sync::oneshot};
use wireframe::{app::WireframeApp, client::WireframeClient, server::WireframeServer};

#[derive(bincode::Encode, bincode::BorrowDecode, Debug, Clone, PartialEq)]
struct Hello {
    magic: [u8; 4],
    version: u16,
}

const MAGIC: [u8; 4] = *b"YARD";

async fn serve() -> std::io::Result<(SocketAddr, oneshot::Receiver<Hello>)> {
    let (seen_tx, seen_rx) = oneshot::channel();
    let seen_tx = std::sync::Mutex::new(Some(seen_tx));

    let server = WireframeServer::new(|| -> WireframeApp { WireframeApp::default() })
        .with_preamble::<Hello>()
        .preamble_timeout(Duration::from_secs(2))
        .on_preamble_decode_success(move |hello: &Hello, stream| {
            if let Some(tx) = seen_tx.lock().expect("lock").take() {
                let _ = tx.send(hello.clone());
            }
            let accepted = hello.magic == MAGIC;
            async move {
                stream.write_all(&[u8::from(accepted)]).await?;
                if accepted {
                    Ok(())
                } else {
                    Err(std::io::ErrorKind::InvalidData.into())
                }
            }
            .boxed()
        })
        .bind("127.0.0.1:0".parse().expect("a socket address"))
        .map_err(std::io::Error::other)?;
    let addr = server.local_addr().expect("a bound address");
    tokio::spawn(server.run_with_shutdown(tokio::time::sleep(Duration::from_secs(5))));
    Ok((addr, seen_rx))
}

#[tokio::test]
async fn the_server_reads_the_preamble_first() {
    let (addr, seen) = serve().await.expect("server starts");

    let client = WireframeClient::builder()
        .with_preamble(Hello {
            magic: MAGIC,
            version: 3,
        })
        .connect(addr)
        .await
        .expect("connect");

    let hello = seen.await.expect("the server saw a preamble");
    assert_eq!(
        hello,
        Hello {
            magic: MAGIC,
            version: 3
        }
    );
    client.close().await;
}
