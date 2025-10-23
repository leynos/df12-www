mock_provider "null" {}
mock_provider "external" {}

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
    bucket_name          = "static-bucket"
    bucket_region        = "fr-par"
    github_owner         = "example"
    github_repo          = "repo"
    github_branch        = "main"
    github_token         = "dummy"
    scaleway_access_key  = "SCWACCESS"
    scaleway_secret_key  = "SCWSECRET"
    cloudflare_api_token = "dummy_cf"
    cloudflare_zone_id   = "0123456789abcdef0123456789abcdef"
  }

  assert {
    condition     = null_resource.deploy.triggers.commit == "deadbeef"
    error_message = "expected deploy null_resource triggers to include the commit hash"
  }
}
