//! The client reading a multi-frame reply that ends in a terminator.
//!
//! wireframe 0.3.0's routed server sends one reply per request, so the
//! server here is a few lines of plain Tokio that speak the same framing.

use std::net::SocketAddr;

use futures::{SinkExt, StreamExt};
use tokio::net::TcpListener;
use tokio_util::codec::{Framed, LengthDelimitedCodec};
use wireframe::{
    app::{Packet, PacketParts},
    client::WireframeClient,
    correlation::CorrelatableFrame,
    message::Message,
};

// ANCHOR: envelope
/// An envelope whose message ID 0 means "end of stream".
#[derive(bincode::Encode, bincode::BorrowDecode, Debug, Clone, PartialEq)]
struct Row {
    id: u32,
    correlation_id: Option<u64>,
    payload: Vec<u8>,
}

impl CorrelatableFrame for Row {
    fn correlation_id(&self) -> Option<u64> {
        self.correlation_id
    }

    fn set_correlation_id(&mut self, id: Option<u64>) {
        self.correlation_id = id;
    }
}

impl Packet for Row {
    fn id(&self) -> u32 {
        self.id
    }

    fn into_parts(self) -> PacketParts {
        PacketParts::new(self.id, self.correlation_id, self.payload)
    }

    fn from_parts(parts: PacketParts) -> Self {
        Self {
            id: parts.id(),
            correlation_id: parts.correlation_id(),
            payload: parts.into_payload(),
        }
    }

    fn is_stream_terminator(&self) -> bool {
        self.id == 0
    }
}
// ANCHOR_END: envelope

/// Answer one request with three rows and a terminator, all correlated.
async fn streaming_server() -> SocketAddr {
    let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
    let addr = listener.local_addr().expect("an address");
    tokio::spawn(async move {
        let (socket, _) = listener.accept().await.expect("accept");
        let mut framed = Framed::new(socket, LengthDelimitedCodec::new());
        let bytes = framed.next().await.expect("a request").expect("a frame");
        let (request, _) = Row::from_bytes(&bytes).expect("decode");
        for (id, body) in [(1, "coal"), (1, "timber"), (1, "empties"), (0, "")] {
            let row = Row {
                id,
                correlation_id: request.correlation_id,
                payload: body.as_bytes().to_vec(),
            };
            let encoded = row.to_bytes().expect("encode");
            framed.send(encoded.into()).await.expect("send");
        }
    });
    addr
}

#[tokio::test]
async fn the_client_reads_rows_until_the_terminator() {
    let addr = streaming_server().await;
    let mut client = WireframeClient::builder()
        .connect(addr)
        .await
        .expect("connect");

    // ANCHOR: call
    let request = Row {
        id: 1,
        correlation_id: None,
        payload: b"manifest".to_vec(),
    };
    let mut rows = client.call_streaming::<Row>(request).await.expect("sent");

    let mut cargo = Vec::new();
    while let Some(row) = rows.next().await {
        let row = row.expect("a correlated row");
        cargo.push(String::from_utf8(row.payload).expect("text"));
    }
    // ANCHOR_END: call

    assert_eq!(cargo, ["coal", "timber", "empties"]);
}
