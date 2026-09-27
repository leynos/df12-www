//! A Scenario Outline: one test generated per Examples row, with the
//! placeholder value threaded into the test function as a parameter.

use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};

#[derive(Default)]
struct Trolley {
    lanterns: u32,
    delivered: u32,
}

#[fixture]
fn trolley() -> Trolley {
    Trolley::default()
}

#[given("a trolley carrying {count:u32} lanterns")]
fn load(trolley: &mut Trolley, count: u32) {
    trolley.lanterns = count;
}

#[when("the departure bell rings")]
fn depart(trolley: &mut Trolley) {
    trolley.delivered = trolley.lanterns;
}

#[then("{count:u32} lanterns arrive at the picnic")]
fn arrive(trolley: &Trolley, count: u32) {
    assert_eq!(trolley.delivered, count);
}

#[scenario(path = "tests/features/counting.feature")]
fn counting_lanterns(trolley: Trolley, count: String) {
    let _ = (trolley, count);
}
