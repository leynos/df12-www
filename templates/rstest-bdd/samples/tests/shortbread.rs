use rstest::fixture;
use rstest_bdd_macros::{given, scenario, then, when};

#[derive(Clone, Copy, Debug, Default, PartialEq)]
struct Tin(u32);

#[fixture]
fn tin() -> Tin {
    Tin::default()
}

#[given("a tin of {count:u32} shortbread biscuits")]
fn filled(count: u32) -> Tin {
    Tin(count)
}

#[when("{friends:u32} friends take one each")]
fn share(tin: Tin, friends: u32) -> Result<Tin, String> {
    tin.0
        .checked_sub(friends)
        .map(Tin)
        .ok_or_else(|| format!("only {} biscuits for {friends} friends", tin.0))
}

#[then("{left:u32} biscuits remain in the tin")]
fn remain(tin: Tin, left: u32) {
    assert_eq!(tin, Tin(left));
}

#[scenario(path = "tests/features/shortbread.feature")]
fn sharing(tin: Tin) {
    let _ = tin;
}
