Feature: Packing the hamper
  Background:
    Given an empty hamper

  Scenario: Pack the picnic
    When the following items are packed:
      | item       | quantity | fragile |
      | shortbread | 12       | no      |
      | teapot     | 1        | yes     |
      | lantern    | 2        | yes     |
    Then the hamper holds 15 items
    And 2 kinds of item need careful handling

  Scenario: Leave a note on top
    When a note is tucked under the lid:
      """
      Back by dusk.
      Save Marrow a biscuit.
      """
    Then the note mentions "biscuit"
