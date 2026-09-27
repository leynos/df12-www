Feature: The props cupboard
  Scenario: Borrow a lantern for the rehearsal
    Given the props cupboard is open
    When Marrow borrows the "lantern"
    Then the rehearsal has a lantern
    And the bell is still muffled

  Scenario: Borrow nothing
    Given the props cupboard is open
    Then the rehearsal has nothing borrowed
