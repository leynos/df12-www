use rstest::fixture;
use rstest_bdd_harness_tokio::TokioTestContext;
use rstest_bdd_macros::{given, scenario, then, when};

#[derive(Default)]
struct Trolley {
    arrived: bool,
    upright: bool,
}

#[fixture]
fn trolley() -> Trolley {
    Trolley::default()
}

#[given("the trolley is on the Tokio stage")]
fn on_stage(#[harness_context] stage: &TokioTestContext, trolley: &mut Trolley) {
    assert_eq!(stage.handle().id(), tokio::runtime::Handle::current().id());
    trolley.upright = true;
}

#[when("the departure bell rings")]
async fn depart(trolley: &mut Trolley) {
    trolley.arrived = true;
}

#[then("the lantern arrives upright")]
fn check(trolley: &Trolley) {
    assert!(trolley.arrived && trolley.upright);
}

#[scenario(
    path = "tests/features/stage.feature",
    harness = rstest_bdd_harness_tokio::TokioHarness,
)]
fn tokio_stage(trolley: Trolley) {
    let _ = trolley;
}
