Feature: Counting lanterns
  Scenario Outline: Deliver <count> lanterns
    Given a trolley carrying <count> lanterns
    When the departure bell rings
    Then <count> lanterns arrive at the picnic

    Examples:
      | count |
      | 1     |
      | 2     |
      | 0     |
