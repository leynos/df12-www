//! Frame codecs and preambles.

use std::{io, num::NonZeroUsize, sync::Arc};

use bytes::{Buf, BufMut, Bytes, BytesMut};
use tokio_util::codec::{Decoder, Encoder};
use wireframe::{
    app::{Envelope, Handler, WireframeApp},
    codec::FrameCodec,
    serializer::{BincodeSerializer, Serializer},
    testkit::drive_with_partial_frames,
};

// ANCHOR: codec-types
/// Two bytes of length, four bytes of tag, then the payload.
const HEADER_LEN: usize = 6;

#[derive(Debug, Clone)]
pub struct TaggedFrame {
    pub tag: u32,
    pub payload: Bytes,
}

#[derive(Clone)]
pub struct TagCodec {
    max_frame_length: usize,
}

impl TagCodec {
    pub fn new(max_frame_length: usize) -> Self {
        Self {
            max_frame_length: max_frame_length.min(usize::from(u16::MAX)),
        }
    }
}

pub struct TagDecoder {
    max_frame_length: usize,
}

impl Decoder for TagDecoder {
    type Item = TaggedFrame;
    type Error = io::Error;

    fn decode(&mut self, src: &mut BytesMut) -> io::Result<Option<TaggedFrame>> {
        if src.len() < HEADER_LEN {
            return Ok(None);
        }
        let len = usize::from(u16::from_be_bytes([src[0], src[1]]));
        if len > self.max_frame_length {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "frame too large",
            ));
        }
        if src.len() < HEADER_LEN + len {
            src.reserve(HEADER_LEN + len - src.len());
            return Ok(None);
        }
        src.advance(2);
        let tag = src.get_u32();
        let payload = src.split_to(len).freeze();
        Ok(Some(TaggedFrame { tag, payload }))
    }
}

pub struct TagEncoder;

impl Encoder<TaggedFrame> for TagEncoder {
    type Error = io::Error;

    fn encode(&mut self, frame: TaggedFrame, dst: &mut BytesMut) -> io::Result<()> {
        let len = u16::try_from(frame.payload.len())
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "payload too large"))?;
        dst.reserve(HEADER_LEN + frame.payload.len());
        dst.put_u16(len);
        dst.put_u32(frame.tag);
        dst.extend_from_slice(&frame.payload);
        Ok(())
    }
}
// ANCHOR_END: codec-types

// ANCHOR: codec-impl
impl FrameCodec for TagCodec {
    type Frame = TaggedFrame;
    type Decoder = TagDecoder;
    type Encoder = TagEncoder;

    fn decoder(&self) -> TagDecoder {
        TagDecoder {
            max_frame_length: self.max_frame_length,
        }
    }

    fn encoder(&self) -> TagEncoder {
        TagEncoder
    }

    fn frame_payload(frame: &TaggedFrame) -> &[u8] {
        &frame.payload
    }

    fn frame_payload_bytes(frame: &TaggedFrame) -> Bytes {
        frame.payload.clone()
    }

    fn wrap_payload(&self, payload: Bytes) -> TaggedFrame {
        TaggedFrame { tag: 0, payload }
    }

    fn correlation_id(frame: &TaggedFrame) -> Option<u64> {
        Some(u64::from(frame.tag))
    }

    fn max_frame_length(&self) -> usize {
        self.max_frame_length
    }
}
// ANCHOR_END: codec-impl

#[test]
fn the_defaults_are_small_and_explicit() {
    // ANCHOR: defaults
    let app: WireframeApp = WireframeApp::new().expect("builder");
    assert_eq!(app.codec().max_frame_length(), 1024);

    let roomier: WireframeApp = WireframeApp::new()
        .expect("builder")
        .buffer_capacity(64 * 1024)
        .read_timeout_ms(250);
    assert_eq!(roomier.codec().max_frame_length(), 64 * 1024);
    // ANCHOR_END: defaults
}

#[tokio::test]
async fn a_custom_codec_survives_one_byte_reads() {
    // ANCHOR: install
    let codec = TagCodec::new(4096);
    let echo: Handler<Envelope> = Arc::new(|_: &Envelope| Box::pin(async {}));
    let app: WireframeApp<_, _, Envelope, TagCodec> = WireframeApp::<BincodeSerializer>::new()
        .expect("builder")
        .with_codec(codec.clone())
        .route(1, echo)
        .expect("a route");
    // ANCHOR_END: install

    let request = Envelope::new(1, Some(9), b"vertex".to_vec());
    let wire = BincodeSerializer.serialize(&request).expect("encode");
    let one_byte = NonZeroUsize::new(1).expect("non-zero");
    let replies = drive_with_partial_frames(app, &codec, vec![wire.clone()], one_byte)
        .await
        .expect("the app answers");
    assert_eq!(replies, vec![wire]);
}
