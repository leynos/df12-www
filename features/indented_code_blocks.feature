Feature: Rendering indented fenced code blocks
  Scenario: Nested code fences with qualifiers render properly
    Given a docs config for indented code blocks
    And markdown content with indented fenced code blocks is stubbed
    When I render the sample docs page
    Then the HTML includes a highlighted code block for the sample
