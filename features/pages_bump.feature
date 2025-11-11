Feature: Updating latest release metadata for docs pages
  Scenario: Persisting release tags from GitHub
    Given a pages config referencing public repositories
    And GitHub responses are replayed via betamax
    When I run the pages bump workflow
    Then the config records the expected release tags
