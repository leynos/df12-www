//! Fragmentation, reassembly, and memory budgets.

use std::{num::NonZeroUsize, sync::Arc, time::Duration};

use wireframe::{
    app::{BudgetBytes, Envelope, Handler, MemoryBudgets, WireframeApp},
    codec::LengthDelimitedFrameCodec,
    fragment::{FragmentHeader, FragmentIndex, Fragmenter, MessageId, Reassembler},
    serializer::{BincodeSerializer, Serializer},
    testkit::drive_with_fragments,
};

#[test]
fn a_long_load_travels_in_three_wagons() {
    // ANCHOR: fragmenter
    let fragmenter = Fragmenter::new(NonZeroUsize::new(512).expect("non-zero"));
    let load = [7_u8; 1400];
    let batch = fragmenter.fragment_bytes(load).expect("fragment");
    assert_eq!(batch.len(), 3);

    let last = batch.fragments().last().expect("a final fragment");
    assert!(last.header().is_last_fragment());
    // ANCHOR_END: fragmenter
}

#[test]
fn the_reassembler_rejoins_in_order() {
    // ANCHOR: reassembler
    let cap = NonZeroUsize::new(4096).expect("non-zero");
    let mut reassembler = Reassembler::new(cap, Duration::from_secs(30));
    let id = MessageId::new(9);

    let first = FragmentHeader::new(id, FragmentIndex::zero(), false);
    assert!(
        reassembler
            .push(first, [1_u8; 8])
            .expect("accepted")
            .is_none()
    );

    let second = FragmentHeader::new(id, FragmentIndex::new(1), true);
    let whole = reassembler
        .push(second, [2_u8; 8])
        .expect("accepted")
        .expect("the final fragment completes the message");
    assert_eq!(whole.payload().len(), 16);
    // ANCHOR_END: reassembler
}

// ANCHOR: budgets
fn budgets() -> MemoryBudgets {
    let bytes = |n: usize| BudgetBytes::new(NonZeroUsize::new(n).expect("non-zero"));
    MemoryBudgets::new(bytes(16 * 1024), bytes(64 * 1024), bytes(48 * 1024))
}
// ANCHOR_END: budgets

#[tokio::test]
async fn handlers_receive_the_whole_load() {
    // ANCHOR: enable
    let echo: Handler<Envelope> = Arc::new(|_: &Envelope| Box::pin(async {}));
    let app: WireframeApp = WireframeApp::new()
        .expect("builder")
        .enable_fragmentation()
        .memory_budgets(budgets())
        .route(1, echo)
        .expect("a route");
    // ANCHOR_END: enable

    let request = Envelope::new(1, Some(1), vec![0xAB; 2000]);
    let wire = BincodeSerializer.serialize(&request).expect("encode");
    let fragmenter = Fragmenter::new(NonZeroUsize::new(256).expect("non-zero"));

    let codec = LengthDelimitedFrameCodec::new(1024);
    let replies = drive_with_fragments(app, &codec, &fragmenter, wire)
        .await
        .expect("the app answers");
    assert!(!replies.is_empty());
}
