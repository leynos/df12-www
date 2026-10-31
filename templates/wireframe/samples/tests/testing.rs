//! Testing at the frame with `wireframe::testkit`.

use std::{num::NonZeroUsize, sync::Arc, time::Duration};

use wireframe::{
    app::{Envelope, Handler, WireframeApp},
    codec::LengthDelimitedFrameCodec,
    serializer::{BincodeSerializer, Serializer},
    testkit::{
        SlowIoConfig, SlowIoPacing, drive_with_partial_frames, drive_with_slow_codec_payloads,
    },
};

fn app() -> WireframeApp {
    let echo: Handler<Envelope> = Arc::new(|_: &Envelope| Box::pin(async {}));
    WireframeApp::new()
        .and_then(|app| app.route(1, echo))
        .expect("an echo app")
}

fn request(body: &[u8]) -> Vec<u8> {
    BincodeSerializer
        .serialize(&Envelope::new(1, Some(7), body.to_vec()))
        .expect("encode")
}

#[tokio::test]
async fn one_byte_at_a_time() {
    // ANCHOR: partial
    let codec = LengthDelimitedFrameCodec::new(1024);
    let one = NonZeroUsize::new(1).expect("non-zero");
    let replies = drive_with_partial_frames(app(), &codec, vec![request(b"a"), request(b"b")], one)
        .await
        .expect("the app answers");
    assert_eq!(replies, vec![request(b"a"), request(b"b")]);
    // ANCHOR_END: partial
}

#[tokio::test(start_paused = true)]
async fn a_slow_reader_on_paused_time() {
    let codec = LengthDelimitedFrameCodec::new(1024);
    // ANCHOR: slow
    let pace = |bytes: usize| {
        SlowIoPacing::new(
            NonZeroUsize::new(bytes).expect("non-zero"),
            Duration::from_millis(5),
        )
    };
    let config = SlowIoConfig::new()
        .with_writer_pacing(pace(8))
        .with_reader_pacing(pace(32))
        .with_capacity(64);

    let replies = drive_with_slow_codec_payloads(app(), &codec, vec![request(b"slow")], config)
        .await
        .expect("the app answers");
    assert_eq!(replies, vec![request(b"slow")]);
    // ANCHOR_END: slow
}
