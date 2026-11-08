//! A connection preamble, validated before any frame is read.

use std::{net::SocketAddr, time::Duration};

use futures::FutureExt;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpStream,
    sync::oneshot,
};
use wireframe::{app::WireframeApp, client::WireframeClient, server::WireframeServer};

// ANCHOR: hello
#[derive(bincode::Encode, bincode::BorrowDecode, Debug, Clone, PartialEq)]
struct Hello {
    magic: [u8; 4],
    version: u16,
}

const MAGIC: [u8; 4] = *b"BEAM";
// ANCHOR_END: hello

async fn serve() -> std::io::Result<(SocketAddr, oneshot::Receiver<Hello>)> {
    let (seen_tx, seen_rx) = oneshot::channel();
    let seen_tx = std::sync::Mutex::new(Some(seen_tx));

    // ANCHOR: server
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
                    // An error here closes the connection, so write first.
                    Err(std::io::Error::other("unknown protocol"))
                }
            }
            .boxed()
        })
        .bind("127.0.0.1:0".parse().expect("a socket address"))
        .map_err(std::io::Error::other)?;
    // ANCHOR_END: server
    let addr = server.local_addr().expect("a bound address");
    tokio::spawn(server.run_with_shutdown(tokio::time::sleep(Duration::from_secs(5))));
    Ok((addr, seen_rx))
}

#[tokio::test]
async fn the_server_reads_the_preamble_first() {
    let (addr, seen) = serve().await.expect("server starts");

    // ANCHOR: client
    let client = WireframeClient::builder()
        .with_preamble(Hello {
            magic: MAGIC,
            version: 3,
        })
        .connect(addr)
        .await
        .expect("connect");
    // ANCHOR_END: client

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

#[tokio::test]
async fn a_rejected_preamble_closes_the_connection() {
    let (addr, _seen) = serve().await.expect("server starts");

    // Preambles use big-endian fixed-width integers, whatever the serializer.
    let config = bincode::config::standard()
        .with_big_endian()
        .with_fixed_int_encoding();
    let hello = Hello {
        magic: *b"NOPE",
        version: 3,
    };
    let bytes = bincode::encode_to_vec(&hello, config).expect("encode a preamble");

    let mut stream = TcpStream::connect(addr).await.expect("connect");
    stream.write_all(&bytes).await.expect("send the preamble");

    let mut answer = Vec::new();
    stream
        .read_to_end(&mut answer)
        .await
        .expect("the server closes rather than resets");
    assert_eq!(answer, [0], "the rejection arrives, then the stream ends");
}
