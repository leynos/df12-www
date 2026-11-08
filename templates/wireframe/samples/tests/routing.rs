//! Routes, envelopes, and handlers.

use std::{num::NonZeroUsize, sync::Arc};

use wireframe::{
    WireframeError,
    app::{Envelope, Handler, Packet, PacketParts, WireframeApp},
    codec::LengthDelimitedFrameCodec,
    correlation::CorrelatableFrame,
    serializer::{BincodeSerializer, Serializer},
    testkit::drive_with_partial_frames,
};

// ANCHOR: routes
const LOGIN: u32 = 1;
const TELEMETRY: u32 = 2;

fn handler(name: &'static str) -> Handler<Envelope> {
    Arc::new(move |env: &Envelope| {
        let id = env.id();
        Box::pin(async move { println!("{name} handled message {id}") })
    })
}

fn scope() -> wireframe::Result<WireframeApp> {
    WireframeApp::new()?
        .route(LOGIN, handler("login"))?
        .route(TELEMETRY, handler("telemetry"))
}
// ANCHOR_END: routes

#[test]
fn a_message_id_is_routed_once() {
    // ANCHOR: duplicate
    let app = scope().expect("two distinct routes");
    let refused = app.route(LOGIN, handler("impostor"));
    assert!(matches!(
        refused,
        Err(WireframeError::DuplicateRoute(LOGIN))
    ));
    // ANCHOR_END: duplicate
}

// ANCHOR: stroke
/// What handlers see in place of `Envelope`: a 16-bit opcode, a tag, and the
/// payload. The wire still carries the serializer's `Envelope`.
#[derive(bincode::Encode, bincode::BorrowDecode, Debug, PartialEq)]
struct Stroke {
    opcode: u16,
    tag: Option<u64>,
    payload: Vec<u8>,
}

impl CorrelatableFrame for Stroke {
    fn correlation_id(&self) -> Option<u64> {
        self.tag
    }
    fn set_correlation_id(&mut self, tag: Option<u64>) {
        self.tag = tag;
    }
}

impl Packet for Stroke {
    fn id(&self) -> u32 {
        u32::from(self.opcode)
    }

    fn into_parts(self) -> PacketParts {
        PacketParts::new(u32::from(self.opcode), self.tag, self.payload)
    }

    fn from_parts(parts: PacketParts) -> Self {
        Self {
            opcode: u16::try_from(parts.id()).unwrap_or(u16::MAX),
            tag: parts.correlation_id(),
            payload: parts.into_payload(),
        }
    }
}
// ANCHOR_END: stroke

// ANCHOR: stroke-app
type StrokeApp = WireframeApp<BincodeSerializer, (), Stroke>;

fn stroke_scope() -> wireframe::Result<StrokeApp> {
    let draw: Handler<Stroke> = Arc::new(|stroke: &Stroke| {
        let opcode = stroke.opcode;
        Box::pin(async move { println!("drawing opcode {opcode}") })
    });
    StrokeApp::new()?.route(107, draw)
}
// ANCHOR_END: stroke-app

#[tokio::test]
async fn a_custom_envelope_changes_what_handlers_see_not_the_wire() {
    let app = stroke_scope().expect("a stroke route");
    let codec = LengthDelimitedFrameCodec::new(1024);
    let request = Envelope::new(107, Some(42), b"move".to_vec());
    let wire = BincodeSerializer
        .serialize(&request)
        .expect("encode the envelope");

    let one_byte = NonZeroUsize::new(1).expect("non-zero");
    let replies = drive_with_partial_frames(app, &codec, vec![wire], one_byte)
        .await
        .expect("the app answers");

    let (reply, _): (Envelope, usize) = BincodeSerializer
        .deserialize(&replies[0])
        .expect("the reply leaves as an Envelope");
    assert_eq!(reply, request, "the default reply echoes the request");
}

#[tokio::test]
async fn trailing_bytes_after_an_envelope_are_a_decode_failure() {
    let app = scope().expect("two distinct routes");
    let codec = LengthDelimitedFrameCodec::new(1024);
    let request = Envelope::new(LOGIN, Some(1), b"sign in".to_vec());
    let mut wire = BincodeSerializer.serialize(&request).expect("encode");
    wire.push(0);

    let one_byte = NonZeroUsize::new(1).expect("non-zero");
    let replies = drive_with_partial_frames(app, &codec, vec![wire], one_byte)
        .await
        .expect("the connection survives one failure");
    assert!(
        replies.is_empty(),
        "nothing is dispatched, so nothing answers"
    );
}
