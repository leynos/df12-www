mock_provider "aws" {}
mock_provider "godaddy-dns" {}

run "plan" {
  command = "plan"
}
