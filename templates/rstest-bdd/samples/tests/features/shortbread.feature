Feature: Sharing the shortbread
  Scenario: One biscuit each
    Given a tin of 12 shortbread biscuits
    When 3 friends take one each
    Then 9 biscuits remain in the tin
