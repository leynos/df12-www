//! The `scenarios!` macro auto-discovering feature files, tag filtering, and
//! a step that skips a scenario at runtime.

use rstest::fixture;
use rstest_bdd_macros::{given, scenarios, then};

#[derive(Default)]
struct Evening {
    forecast: String,
}

#[fixture]
fn evening() -> Evening {
    Evening::default()
}

#[given("the forecast is \"{forecast}\"")]
fn forecast(evening: &mut Evening, forecast: String) {
    if forecast == "thunder" {
        rstest_bdd::skip!("no picnics in a thunderstorm");
    }
    evening.forecast = forecast;
}

#[then("the blanket goes on the grass")]
fn blanket(evening: &Evening) {
    assert_eq!(evening.forecast, "dry");
}

#[then("the lanterns are lit early")]
fn lanterns(evening: &Evening) {
    assert_eq!(evening.forecast, "fog");
}

scenarios!(
    "tests/features/auto",
    tags = "@smoke and not @wip",
    fixtures = [evening: Evening]
);
