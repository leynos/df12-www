Feature: Lantern delivery
  Scenario: Deliver a lantern
    Given a lantern on the trolley
    When the departure bell rings
    Then the lantern arrives upright
