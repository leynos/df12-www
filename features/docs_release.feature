Feature: Rendering docs from tagged releases
  Scenario: Documentation metadata reflects the latest release
    Given a docs config referencing a release-tagged repo
    And documentation fetches are replayed via betamax
    When I render the docs for that page
    Then the HTML shows the release version and tag date
