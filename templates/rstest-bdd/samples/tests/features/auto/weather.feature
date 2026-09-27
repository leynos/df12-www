Feature: Picnic weather
  @smoke
  Scenario: A dry evening
    Given the forecast is "dry"
    Then the blanket goes on the grass

  @wip
  Scenario: Fog over the loch
    Given the forecast is "fog"
    Then the lanterns are lit early

  @smoke @allow_skipped
  Scenario: Thunder in the hills
    Given the forecast is "thunder"
    Then the blanket goes on the grass
