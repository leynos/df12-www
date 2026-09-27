//! A `DataTableRow` struct binding a Gherkin data table, and a step that
//! captures a doc string as a plain `String` argument.

use rstest::fixture;
use rstest_bdd::datatable::Rows;
use rstest_bdd_macros::{DataTableRow, given, scenario, then, when};

#[derive(Debug, DataTableRow)]
struct Item {
    item: String,
    quantity: u32,
    #[datatable(truthy)]
    fragile: bool,
}

#[derive(Default)]
struct Hamper {
    items: Vec<Item>,
    note: String,
}

#[fixture]
fn hamper() -> Hamper {
    Hamper::default()
}

#[given("an empty hamper")]
fn empty(hamper: &mut Hamper) {
    hamper.items.clear();
}

#[when("the following items are packed:")]
fn pack(hamper: &mut Hamper, #[datatable] rows: Rows<Item>) {
    hamper.items.extend(rows);
}

#[then("the hamper holds {total:u32} items")]
fn holds(hamper: &Hamper, total: u32) {
    let packed: u32 = hamper.items.iter().map(|row| row.quantity).sum();
    assert_eq!(packed, total);
}

#[then("{kinds:usize} kinds of item need careful handling")]
fn fragile(hamper: &Hamper, kinds: usize) {
    let careful: Vec<&str> = hamper
        .items
        .iter()
        .filter(|row| row.fragile)
        .map(|row| row.item.as_str())
        .collect();
    assert_eq!(careful.len(), kinds, "fragile: {careful:?}");
}

#[when("a note is tucked under the lid:")]
fn tuck(hamper: &mut Hamper, docstring: String) {
    hamper.note = docstring;
}

#[then("the note mentions \"{word}\"")]
fn mentions(hamper: &Hamper, word: String) {
    assert!(hamper.note.contains(&word), "note: {:?}", hamper.note);
}

#[scenario(path = "tests/features/hamper.feature", name = "Pack the picnic")]
fn pack_the_picnic(hamper: Hamper) {
    let _ = hamper;
}

#[scenario(path = "tests/features/hamper.feature", name = "Leave a note on top")]
fn leave_a_note(hamper: Hamper) {
    let _ = hamper;
}
