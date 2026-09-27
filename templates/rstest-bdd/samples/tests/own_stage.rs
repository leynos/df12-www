use rstest::fixture;
use rstest_bdd_harness::{HarnessAdapter, HarnessResult, StdScenarioRunRequest};
use rstest_bdd_macros::{given, scenario, then, when};

/// A harness that announces the stage, then runs the scenario on the test
/// thread, as the standard harness does.
#[derive(Default)]
struct LanternStage;

impl HarnessAdapter for LanternStage {
    type Context = ();

    fn run<T>(&self, request: StdScenarioRunRequest<'_, T>) -> HarnessResult<T> {
        eprintln!("lighting the lantern stage");
        Ok(request.run_without_context())
    }
}

#[derive(Default)]
struct Trolley {
    arrived: bool,
    upright: bool,
}

#[fixture]
fn trolley() -> Trolley {
    Trolley::default()
}

#[given("a lantern on the trolley")]
fn load(trolley: &mut Trolley) {
    trolley.upright = true;
}

#[when("the departure bell rings")]
fn depart(trolley: &mut Trolley) {
    trolley.arrived = true;
}

#[then("the lantern arrives upright")]
fn check(trolley: &Trolley) {
    assert!(trolley.arrived && trolley.upright);
}

#[scenario(path = "tests/features/own_stage.feature", harness = LanternStage)]
fn lantern_stage(trolley: Trolley) {
    let _ = trolley;
}
