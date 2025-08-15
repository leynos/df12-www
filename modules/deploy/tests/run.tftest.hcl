mock_provider "aws" {}
mock_provider "external" {}
mock_provider "null" {}

override_data {
  target = data.external.git_sync
  values = {
    result = {
      commit = "deadbeef"
    }
  }
}

run "plan" {
  command = plan

  variables {
    bucket_name     = "dummy-bucket"
    distribution_id = "EDFD123456789A"
    github_owner    = "example"
    github_repo     = "repo"
    github_branch   = "main"
    github_token    = "dummy"
  }
}
