//! An async `#[when]` step under `#[tokio::test]`, awaiting a channel until
//! the kettle boils.

use std::time::Duration;

use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};
use tokio::sync::watch;

struct Kettle {
    boiled: watch::Sender<bool>,
    cups: u32,
}

#[fixture]
fn kettle() -> Kettle {
    let (boiled, _) = watch::channel(false);
    Kettle { boiled, cups: 0 }
}

#[given("a kettle on the camp stove")]
fn on_the_stove(kettle: &mut Kettle) {
    kettle.cups = 4;
}

#[when("the kettle comes to the boil")]
async fn boil(kettle: &Kettle) {
    let mut whistle = kettle.boiled.subscribe();
    let stove = kettle.boiled.clone();
    tokio::spawn(async move {
        tokio::time::sleep(Duration::from_millis(20)).await;
        stove.send_replace(true);
    });
    whistle.wait_for(|boiled| *boiled).await.expect("the stove went out");
}

#[then("there is hot water for {cups:u32} cups")]
fn pour(kettle: &Kettle, cups: u32) {
    assert!(*kettle.boiled.borrow());
    assert_eq!(kettle.cups, cups);
}

#[scenario(path = "tests/features/kettle.feature")]
#[tokio::test(flavor = "current_thread")]
async fn kettle_boils(kettle: Kettle) {
    let _ = kettle;
}
