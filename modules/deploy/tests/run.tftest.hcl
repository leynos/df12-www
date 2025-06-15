mock_provider "aws" {}
mock_provider "external" {}
mock_provider "null" {}

override_resource null_resource.deploy {
  values = {
    triggers = {
      commit = "deadbeef"
    }
  }
}

run "plan" {
  command = plan

  variables {
    bucket_name     = "dummy-bucket"
    distribution_id = "DIST123"
    github_owner    = "example"
    github_repo     = "repo"
    github_branch   = "main"
    github_token    = "dummy"
  }

  expect_failures = [
    data.external.git_sync
  ]
}
