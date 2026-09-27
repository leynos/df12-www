use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};

#[derive(Default)]
struct Trolley {
    loaded: bool,
    arrived: bool,
    upright: bool,
}

#[fixture]
fn trolley() -> Trolley {
    Trolley::default()
}

#[given("a lantern on the trolley")]
fn load(trolley: &mut Trolley) {
    trolley.loaded = true;
    trolley.upright = true;
}

#[when("the departure bell rings")]
fn depart(trolley: &mut Trolley) {
    trolley.arrived = true;
}

#[then("the lantern arrives upright")]
fn check(trolley: &Trolley) {
    assert!(trolley.loaded);
    assert!(trolley.arrived);
    assert!(trolley.upright);
}

#[scenario(path = "tests/features/lantern.feature", name = "Deliver a lantern")]
fn lantern_delivery(trolley: Trolley) {
    let _ = trolley;
}
