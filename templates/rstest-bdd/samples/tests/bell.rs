//! A step pattern inferred from its function name, and a cucumber-rs-style
//! `expr =` pattern with a typed placeholder.

use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};

#[derive(Default)]
struct Bell {
    rings: u32,
}

#[fixture]
fn bell() -> Bell {
    Bell::default()
}

// No pattern: it is inferred from the function name, underscores as spaces.
#[given]
fn a_bell_on_the_trolley(bell: &mut Bell) {
    bell.rings = 0;
}

// cucumber-rs style, accepted to ease a migration.
#[when(expr = "the bell rings {times:u32} times")]
fn ring(bell: &mut Bell, times: u32) {
    bell.rings += times;
}

#[then("the rabbit hears {count:u32} rings")]
fn hears(bell: &Bell, count: u32) {
    assert_eq!(bell.rings, count);
}

#[scenario(path = "tests/features/bell.feature")]
fn ring_three_times(bell: Bell) {
    let _ = bell;
}
