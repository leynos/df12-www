Feature: Docs index uses canonical first section links
  Scenario: Entry links point to the first section as written
    Given a docs config for ordering behaviour
    And markdown with out-of-order section names is stubbed
    When I render the docs and build the index
    Then the docs index entry links to the true first section
    And the docs card exposes repo, release, and registry links
