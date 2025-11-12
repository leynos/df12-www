# Scaleway Provider Parity Notes

_Updated: 22 October 2025_

This document captures the current feature parity assessment for replacing the
AWS portions of the static site stack with Scaleway services. It is based on
exploratory research only—no implementation has been attempted yet.

## Core Hosting Components

- **Object storage** – Scaleway Object Storage exposes an Amazon S3–compatible
  API. The existing `aws s3 sync` workflow can target it by setting a custom
  `--endpoint-url` and credentials, so static assets can live entirely on
  Scaleway buckets.
- **CDN + TLS** – Scaleway Edge Services sits in front of Object Storage or
  load balancers. It supports custom domains, Let’s Encrypt or uploaded
  certificates, caching, and (beta) WAF. Functionally this maps to CloudFront +
  ACM, but only one pipeline can front a bucket at a time and origin choices
  are currently limited to Scaleway services.
- **Deploy orchestration** – The Terraform/OpenTofu provider for Scaleway
  offers resources for both Object Storage buckets and Edge Services pipelines.
  A provider toggle could reuse most of the current module shape.

## Monitoring & Observability

- **Metrics, logs, traces** – Scaleway Cockpit collects platform telemetry,
  exposes managed Grafana dashboards, and ingests Prometheus/Loki/Tempo data.
  Default retention is shorter than CloudWatch (31-day metrics, 7-day
  logs/traces), so long-term analytics would require paid retention upgrades or
  offloading data elsewhere.
- **Alerting** – Cockpit allows alert definitions through Grafana’s alert
  manager. There is no direct CloudWatch analogue, so alarm configuration would
  need to be ported or regenerated against Cockpit APIs.
- **Cost controls** – Billing Cost Manager provides spend analytics, while
  Billing Alerts let you define EUR-denominated thresholds with
  email/SMS/webhook channels. Feature depth is lighter than AWS Budgets (no
  granular service filters), but it covers the “total spend warning” use case.

## Operational Considerations

- **Feature gaps** – WAF is GA but still labelled as feature-limited; Edge
  Services currently restricts origins to Scaleway Object Storage or Load
  Balancer. AWS Shield, Route 53 health checks, and Lambda@Edge have no direct
  Scaleway counterparts.
- **Tooling pivots** – Terraform modules should be refactored so every AWS
  resource has a Scaleway analogue controlled by a `cloud_provider` flag. Edge
  Services cache purges and Cockpit alert definitions require new automation.
- **Currency & reporting** – All billing automation is euro-only. If GBP
  reporting (current budget limit) is required, conversion logic or third-party
  FinOps tooling (e.g. Holori) will be needed.

## Suggested Next Steps

1. **Design module split** – Break the existing static site and monitoring
   modules into provider-specific components and drive selection via a shared
   variable.
2. **Prototype deploy flow** – Add Scaleway sync + CDN purge paths in the
   deploy module, verifying identical asset layout and cache invalidations.
3. **Map monitoring parity** – Define Cockpit alert rules that mirror current
   CloudWatch alarms and confirm retention meets compliance needs.
4. **Evaluate cost alerts** – Configure sample Billing Alerts and compare
   signal quality to AWS Budgets; decide whether external FinOps tooling is
   needed.
5. **Plan DNS implications** – When running entirely on Scaleway, ensure
   Cloudflare (or alternate DNS) points at the correct CDN endpoint and that
   certificates remain valid.

Once these pieces are proven, the platform should be able to flip between AWS
and Scaleway by changing provider variables rather than rewriting
infrastructure code.
