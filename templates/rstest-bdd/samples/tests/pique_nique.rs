use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};

#[derive(Default)]
struct Chariot {
    debout: bool,
    arrive: bool,
}

#[fixture]
fn chariot() -> Chariot {
    Chariot::default()
}

#[given("une lanterne sur le chariot")]
fn charger(chariot: &mut Chariot) {
    chariot.debout = true;
}

#[when("la cloche du départ sonne")]
fn partir(chariot: &mut Chariot) {
    chariot.arrive = true;
}

#[then("la lanterne arrive debout")]
fn verifier(chariot: &Chariot) {
    assert!(chariot.arrive && chariot.debout);
}

#[scenario(path = "tests/features/pique_nique.feature")]
fn livrer_une_lanterne(chariot: Chariot) {
    let _ = chariot;
}
