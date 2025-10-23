mock_provider "scaleway" {}

run "plan" {
  command = plan

  variables {
    domain_name    = "www.example.com"
    bucket_name    = "static-bucket"
    region         = "fr-par"
    project_id     = "11111111-1111-1111-1111-111111111111"
    alert_contacts = ["alerts@example.com"]
  }

  assert {
    condition     = scaleway_cockpit.this.project_id == "11111111-1111-1111-1111-111111111111"
    error_message = "expected cockpit to target the provided project id"
  }
}
