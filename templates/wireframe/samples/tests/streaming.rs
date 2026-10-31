//! Streaming responses, push queues, the connection actor, and sessions.

use futures::{StreamExt, TryStreamExt, stream};
use tokio_util::sync::CancellationToken;
use wireframe::{
    app::{Envelope, Packet},
    connection::ConnectionActor,
    push::PushQueues,
    response::Response,
    session::{ConnectionId, SessionRegistry},
};

#[derive(Debug, Clone, PartialEq)]
struct Wagon(u32);

#[tokio::test]
async fn a_stream_response_yields_every_frame() {
    // ANCHOR: stream
    let wagons = stream::iter((1..=3).map(|n| Ok(Wagon(n))));
    let response: Response<Wagon> = Response::Stream(Box::pin(wagons));

    let frames: Vec<Wagon> = response.into_stream().try_collect().await.expect("frames");
    assert_eq!(frames, vec![Wagon(1), Wagon(2), Wagon(3)]);
    // ANCHOR_END: stream
}

#[tokio::test]
async fn a_multi_packet_sender_waits_for_room() {
    // ANCHOR: multi-packet
    let (sender, response) = Response::<Wagon>::with_channel(2);

    let producer = tokio::spawn(async move {
        for n in 1..=5 {
            // `send` waits whenever the channel already holds two wagons.
            if sender.send(Wagon(n)).await.is_err() {
                return;
            }
        }
        // Dropping the last sender ends the response.
    });

    let frames: Vec<Wagon> = response.into_stream().try_collect().await.expect("frames");
    producer.await.expect("the producer finished");
    assert_eq!(frames.len(), 5);
    // ANCHOR_END: multi-packet
}

#[tokio::test]
async fn the_actor_drains_push_traffic_and_the_response() {
    // ANCHOR: actor
    let (queues, handle) = PushQueues::<Envelope>::builder()
        .high_capacity(8)
        .low_capacity(8)
        .build()
        .expect("valid capacities");

    handle
        .push_low_priority(Envelope::new(30, None, vec![]))
        .await
        .expect("queued");
    handle
        .push_high_priority(Envelope::new(10, None, vec![]))
        .await
        .expect("queued");

    let reply = stream::iter(vec![Ok(Envelope::new(20, Some(1), vec![]))]).boxed();
    let token = CancellationToken::new();
    let mut actor: ConnectionActor<Envelope, ()> =
        ConnectionActor::new(queues, handle, Some(reply), token);

    let mut out = Vec::new();
    actor.run(&mut out).await.expect("the actor drains");
    let mut ids: Vec<u32> = out.iter().map(Envelope::id).collect();
    ids.sort_unstable();
    assert_eq!(ids, vec![10, 20, 30]);
    // ANCHOR_END: actor
}

#[tokio::test]
async fn the_registry_holds_handles_weakly() {
    let (queues, handle) = PushQueues::<u8>::builder()
        .high_capacity(1)
        .low_capacity(1)
        .build()
        .expect("valid capacities");

    // ANCHOR: registry
    let registry: SessionRegistry<u8> = SessionRegistry::default();
    let id = ConnectionId::new(42);
    registry.insert(id, &handle);
    assert!(registry.get(&id).is_some());

    drop((queues, handle));
    assert!(
        registry.get(&id).is_none(),
        "a closed connection leaves no handle behind"
    );
    // ANCHOR_END: registry
}
