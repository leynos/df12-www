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

const LOGIN: u32 = 1;
const TELEMETRY: u32 = 2;

fn handler(name: &'static str) -> Handler<Envelope> {
    Arc::new(move |env: &Envelope| {
        let id = env.id();
        Box::pin(async move { println!("{name} handled message {id}") })
    })
}

fn yard() -> wireframe::Result<WireframeApp> {
    WireframeApp::new()?
        .route(LOGIN, handler("login"))?
        .route(TELEMETRY, handler("telemetry"))
}

#[test]
fn a_message_id_is_routed_once() {
    let app = yard().expect("two distinct routes");
    let refused = app.route(LOGIN, handler("impostor"));
    assert!(matches!(
        refused,
        Err(WireframeError::DuplicateRoute(LOGIN))
    ));
}

/// A protocol's own envelope: a 16-bit opcode, a ticket, and the payload.
#[derive(bincode::Encode, bincode::BorrowDecode, Debug, PartialEq)]
struct Waybill {
    opcode: u16,
    ticket: Option<u64>,
    payload: Vec<u8>,
}

impl CorrelatableFrame for Waybill {
    fn correlation_id(&self) -> Option<u64> {
        self.ticket
    }
    fn set_correlation_id(&mut self, ticket: Option<u64>) {
        self.ticket = ticket;
    }
}

impl Packet for Waybill {
    fn id(&self) -> u32 {
        u32::from(self.opcode)
    }

    fn into_parts(self) -> PacketParts {
        PacketParts::new(u32::from(self.opcode), self.ticket, self.payload)
    }

    fn from_parts(parts: PacketParts) -> Self {
        Self {
            opcode: u16::try_from(parts.id()).unwrap_or(u16::MAX),
            ticket: parts.correlation_id(),
            payload: parts.into_payload(),
        }
    }
}

type WaybillApp = WireframeApp<BincodeSerializer, (), Waybill>;

fn waybill_yard() -> wireframe::Result<WaybillApp> {
    let unload: Handler<Waybill> = Arc::new(|bill: &Waybill| {
        let opcode = bill.opcode;
        Box::pin(async move { println!("unloading opcode {opcode}") })
    });
    WaybillApp::new()?.route(107, unload)
}

#[tokio::test]
async fn a_custom_envelope_keeps_its_ticket() {
    let app = waybill_yard().expect("a waybill route");
    let codec = LengthDelimitedFrameCodec::new(1024);
    let bill = Waybill {
        opcode: 107,
        ticket: Some(42),
        payload: b"coal".to_vec(),
    };
    let wire = BincodeSerializer
        .serialize(&bill)
        .expect("encode the waybill");

    let one_byte = NonZeroUsize::new(1).expect("non-zero");
    let replies = drive_with_partial_frames(app, &codec, vec![wire], one_byte)
        .await
        .expect("the app answers");

    let (reply, _): (Waybill, usize) = BincodeSerializer
        .deserialize(&replies[0])
        .expect("decode the reply");
    assert_eq!(reply, bill, "the default reply echoes the request");
}
