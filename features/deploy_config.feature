Feature: Deploy configuration uses a single config.toml

  Scenario: Using config.toml generates temporary backend and tfvars files
    Given a deploy config file with backend and site values
    When I initialise the stack with the config
    Then a temporary backend file is passed to tofu init
    And a temporary tfvars file is passed to tofu init
