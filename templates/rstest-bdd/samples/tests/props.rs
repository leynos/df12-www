use std::sync::OnceLock;

use rstest::fixture;
use rstest_bdd::Slot;
use rstest_bdd_macros::{ScenarioState, given, scenario, then, when};

/// Expensive to build and never changed: shared by every scenario.
struct Cupboard {
    shelves: Vec<&'static str>,
}

#[fixture]
#[once]
fn cupboard() -> &'static Cupboard {
    static CUPBOARD: OnceLock<Cupboard> = OnceLock::new();
    CUPBOARD.get_or_init(|| Cupboard {
        shelves: vec!["lantern", "bell muffler", "spare wheel"],
    })
}

/// Fresh for every scenario: what this rehearsal has borrowed.
#[derive(Default, ScenarioState)]
struct Rehearsal {
    borrowed: Slot<&'static str>,
    muffled: Slot<bool>,
}

#[fixture]
fn rehearsal() -> Rehearsal {
    Rehearsal::default()
}

/// Built per scenario from the shared cupboard.
struct Stage {
    cupboard: &'static Cupboard,
}

#[fixture]
fn stage(cupboard: &'static Cupboard) -> Stage {
    Stage { cupboard }
}

#[given("the props cupboard is open")]
fn open(rehearsal: &Rehearsal) {
    rehearsal.muffled.set(true);
}

#[when("Marrow borrows the \"{prop}\"")]
fn borrow(stage: &Stage, rehearsal: &Rehearsal, prop: String) {
    let found = stage
        .cupboard
        .shelves
        .iter()
        .find(|shelf| **shelf == prop)
        .expect("the cupboard has that prop");
    rehearsal.borrowed.set(found);
}

#[then("the rehearsal has a lantern")]
fn has_lantern(rehearsal: &Rehearsal) {
    assert_eq!(rehearsal.borrowed.get(), Some("lantern"));
}

#[then("the bell is still muffled")]
fn muffled(rehearsal: &Rehearsal) {
    assert_eq!(rehearsal.muffled.get(), Some(true));
}

#[then("the rehearsal has nothing borrowed")]
fn nothing(rehearsal: &Rehearsal) {
    assert!(rehearsal.borrowed.is_empty());
}

#[scenario(path = "tests/features/props.feature", name = "Borrow a lantern for the rehearsal")]
fn borrow_a_lantern(stage: Stage, rehearsal: Rehearsal) {
    let _ = (stage, rehearsal);
}

#[scenario(path = "tests/features/props.feature", name = "Borrow nothing")]
fn borrow_nothing(stage: Stage, rehearsal: Rehearsal) {
    let _ = (stage, rehearsal);
}
