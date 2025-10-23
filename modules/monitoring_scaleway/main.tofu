resource "scaleway_cockpit" "this" {
  project_id = var.project_id
}

# Scaleway Cockpit currently exposes alerting via Grafana/Alertmanager.
# This module ensures Cockpit is activated for the project. Contact points
# can be managed manually or via Grafana once activated.
