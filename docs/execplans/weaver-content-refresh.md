# Refresh the Weaver sub-site to document the planned UX and capability surface

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: DRAFT (content execution BLOCKED pending the Weaver daisyUI/Tailwind
migration — see `Constraints`)

## Purpose / big picture

The Weaver sub-site (`/weaver/` on df12.net, generated from
`templates/weaver/`) currently documents the prototype `observe` / `act` /
`verify` command grammar. That grammar has been formally superseded: the
Weaver repository's branch `sempai-query-pipeline-rfc` (and its parent branch
`mutation-vertical-slice`) contain a documentation-only reset of the public
surface — ADR 007 plus RFCs 0002 and 0003 and ADRs 008–012 — defining a
noun-verb command grammar, a multi-workspace daemon model, a shared safe
mutation engine, and the Sempai query-to-selector pipeline.

Because a drastic product refresh is planned, the site should describe the
*planned* user experience (clearly labelled as planned where the distinction
matters), not the prototype that will be discarded. After this work, a visitor
to `/weaver/` sees the 0.1.0 target surface: `weaver symbols list --lang rust
--query 'fn $NAME($...ARGS)' --json` piped through `jq` into `weaver symbols
rename --selectors -`, rather than `weaver observe get-definition`.

Success is observable: `uv run pages generate --site weaver` produces pages
whose command examples, feature claims, and vocabulary match the authoritative
Weaver branch documents cited below, with no remaining references to the
retired `observe`/`act`/`verify` public grammar except in an explicit
"superseded prototype" context.

## Constraints

- **Do not edit `templates/weaver/`, `src/static/weaver/`, or
  `config/pages.yaml`'s weaver block yet.** A migration of the Weaver
  sub-site from the Tailwind Play CDN to compiled Tailwind v4 + daisyUI is in
  progress on branch `weaver-daisy-migration` (semantic markup vocabulary,
  split stylesheets and tokens, contrast fixes, vendored images and icons; as
  of 2026-08-17 this branch is rebased onto it). Editing the same templates
  while the migration is still moving would create conflicts. Content
  execution starts only after the migration lands on `main` (or the user
  directs otherwise), at which point Stage B reconciles this plan with the
  final migrated template structure.
- Nothing under `public/` is tracked; never edit generated output. All
  content changes go into `templates/weaver/pages/*.jinja`, the weaver chrome
  templates, and `config/pages.yaml`.
- Public-facing prose must follow the `df12-copy` voice skill and
  `en-gb-oxendict` (British English, Oxford spelling).
- The site must remain honest about status. RFC 0003 acceptance criterion 16
  requires documentation to "distinguish implemented, compatibility-subset,
  parse-only, unsupported, and planned behaviour". The site presents the
  planned surface as the product story but labels it planned (the existing
  `.status-pill-planned` pattern, or its daisyUI successor).
- Do not invent capabilities. Every command, flag, schema name, and claim
  must trace to a cited Weaver document (see `Source documents`).
- Markdown changes in this repo gate on `make markdownlint` and `make nixie`.
  Template changes gate on the full `make check-fmt lint typecheck` plus
  `bun run build:static && make test-js` (the weaver mobile-nav test loads
  built output).

## Tolerances (exception triggers)

- Scope: content execution touches only the weaver templates, weaver static
  assets, weaver YAML config, and weaver-referencing copy in the main-site
  YAML (homepage card, reference-library entry). Anything beyond that: stop
  and escalate.
- Source conflict: if two authoritative Weaver documents contradict each
  other on a user-visible claim and the precedence rules in `Source
  documents` below do not resolve it, stop and present the conflict rather
  than choosing.
- Upstream drift: if, at execution time, the Weaver branches have moved such
  that a cited document no longer says what this plan quotes, re-survey the
  branch and update this plan before writing copy.
- Illustrations: this plan rewords captions and swaps commands in terminal
  mock-ups; if a page's PNG illustration itself depicts retired concepts so
  centrally that text cannot compensate, flag it for regeneration rather than
  silently shipping a contradictory image.
- Iterations: if a gate still fails after 3 attempts on one page, stop and
  escalate.

## Risks

- Risk: the Weaver RFCs are Status: Proposed and may change before the site
  ships.
  Severity: medium. Likelihood: medium.
  Mitigation: the site labels the surface as planned; the plan pins the
  survey date (2026-08-17) and requires a re-survey at execution time.
- Risk: the daisyUI migration restructures templates (e.g. extracts a
  `partials/` chrome), invalidating this plan's per-file targets.
  Severity: medium. Likelihood: high.
  Mitigation: this plan specifies content per *page* (URL), not per template
  line; the mapping section names current files but the copy briefs are
  file-structure-independent.
- Risk: sixteen PNG illustrations embed the observe/act/verify story
  (e.g. `assets/observe/observe-hero-outline.png`,
  `assets/commands/commands-end-to-end-pipeline.png`).
  Severity: medium. Likelihood: high.
  Mitigation: audit each image during Stage C; keep neutral ones, queue
  contradictory ones for regeneration (image work is a separate follow-on
  task, not in this plan's scope).
- Risk: writing "planned" everywhere makes the site read as vapourware.
  Severity: low. Likelihood: medium.
  Mitigation: follow the users-guide split — one clear status statement per
  page plus a single site-wide framing on the home page, not a pill on every
  sentence. The df12 voice ("Honest software. Rare sight.") already supports
  this.

## Progress

- [x] (2026-08-17 00:00Z) Surveyed Weaver branch `sempai-query-pipeline-rfc`
  and parent `mutation-vertical-slice`: digested RFC 0002/0003, ADRs 007–012,
  roadmap phases 12–20, users-guide planned/built split.
- [x] (2026-08-17 00:00Z) Inventoried the df12-www weaver sub-site: 14
  templates, static assets, `config/pages.yaml` lines 1371–1456, migration
  status (Play CDN, no `src/styles/weaver.css`, migration unexecuted).
- [x] (2026-08-17 00:00Z) Authored this ExecPlan (Stage A deliverable).
- [x] (2026-08-17) Rebased this branch onto `weaver-daisy-migration`, which
  now carries the real migration work (union-merged the `typos.local.toml`
  exemption blocks; gates pass).
- [ ] Await the migration landing on `main` (external dependency; unblocks
  Stages B–E).
- [ ] Stage B: re-survey Weaver branches; reconcile this plan with the
  migrated template structure; get approval to execute.
- [ ] Stage C: rewrite page copy per the briefs below.
- [ ] Stage D: config and cross-link updates (`pages.yaml` taglines, nav,
  orphan page, docs links).
- [ ] Stage E: consistency sweep, gates, and visual check.

## Surprises & discoveries

- Observation: the Weaver branches are documentation-only; no code
  implements the new surface yet ("`Engine::compile_dsl` and
  `Engine::execute`, however, still return `NOT_IMPLEMENTED`" — RFC 0003 §2).
  Evidence: `git log main..sempai-query-pipeline-rfc` touches only `docs/`.
  Impact: confirms the user's framing — the site documents planned UX, and
  labelling matters.
- Observation: the existing site already contains internal contradictions
  (home page says Discord "is not live yet" while the roadmap page has a
  "Join Discussion" Discord button; home page and Sempai page disagree on
  language support — home says Go is planned, Sempai page says Go is core).
  Evidence: `templates/weaver/home_page.jinja` vs
  `templates/weaver/pages/roadmap.jinja` and `pages/sempai.jinja`.
  Impact: the refresh must fix these regardless of the grammar reset; added
  to Stage E.
- Observation: `pages/design-language.jinja` is an orphan (not in
  `nav_links`), extends nothing, carries GrapesJS editor residue, and loads
  four images from `storage.googleapis.com/uxpilot-auth.appspot.com/`.
  Evidence: site inventory, 2026-08-17.
  Impact: it is a styling-migration concern, not a content concern; noted
  for the migration task, out of scope here except that its copy needs no
  grammar changes.
- Observation: `docs/sempai-query-language-design.md` in the Weaver repo
  still describes the old `weaver observe query` surface; ADR 011/012 and
  RFC 0003 supersede it for anything user-facing.
  Evidence: Weaver branch survey, 2026-08-17.
  Impact: recorded as a source-precedence rule below so copywriters do not
  reintroduce the retired surface from a stale document. Flagged upstream on
  2026-08-17 as a comment on Weaver PR #228
  (<https://github.com/leynos/weaver/pull/228#issuecomment-5319893016>); if
  the Weaver branch resolves it (status note or trimmed sections), relax the
  precedence caveat at Stage B.

## Decision log

- Decision: deliver this plan now but block content execution on the
  daisyUI/Tailwind migration.
  Rationale: the user stated the migration is in progress and "the updates
  cannot be made directly at this time"; concurrent edits to the same
  templates would conflict.
  Date/Author: 2026-08-17, Claude (per user instruction).
- Decision: the site presents the planned ADR 007 surface as the primary
  product story, with one clear "planned, not shipped" framing per page,
  rather than documenting the prototype with "coming soon" asides.
  Rationale: the user explicitly asked that the site "document the planned
  UX rather than what has been built"; ADR 007 states the 0.1.0 target does
  not preserve prototype compatibility, so documenting the prototype would
  document a dead surface.
  Date/Author: 2026-08-17, Claude (per user instruction + ADR 007).
- Decision: keep the site's page inventory (URLs and nav) stable; repurpose
  the three `commands/{observe,act,verify}/` sub-pages rather than deleting
  them, renaming their focus to the read loop, the change loop, and
  verification respectively.
  Rationale: preserves inbound links and nav muscle-memory; the new surface
  maps naturally (perception → `definitions`/`references`/`cards`/`symbols
  list`; mutation → `patches apply`/`symbols rename`/`symbols move`;
  verification → Double-Lock + `diagnostics list`). Renaming URLs is a
  separate decision the user has not requested.
  Date/Author: 2026-08-17, Claude.
- Decision: Sempai and Jacquard white-paper pages are updated, not
  rewritten.
  Rationale: their language-design and card/graph content remains current;
  only their CLI-surface framing (`observe query`, JSONL op names) is stale.
  Date/Author: 2026-08-17, Claude.

## Outcomes & retrospective

To be completed at execution milestones. As of 2026-08-17 the planning stage
is complete and execution is blocked on the styling migration.

## Context and orientation

Two repositories are involved.

**This repository (df12-www)** generates the df12 Productions website. The
Weaver sub-site is fully generated: `uv run pages generate --site weaver`
(also via `bun run build:pages`) renders `templates/weaver/**/*.jinja` into
the git-ignored `public/weaver/`. Page inventory, nav, taglines, and theme
strings live in `config/pages.yaml` (weaver block at lines 1371–1456).
Hand-crafted static assets live in `src/static/weaver/` and are copied
verbatim by `bun run build:static`. The templates are:
`templates/weaver/home_page.jinja` (homepage, self-contained chrome),
`templates/weaver/doc_page.jinja` (base layout for content pages),
`templates/weaver/shared_content_page.jinja` (legal pages), and thirteen
content pages under `templates/weaver/pages/`. All weaver chrome currently
loads the Tailwind Play CDN; a migration to compiled Tailwind v4 + daisyUI
(mirroring the mxd sub-site) is planned but unexecuted.

**The Weaver repository** (worktree surveyed:
`/data/leynos/Projects/weaver.worktrees/sempai-query-pipeline-rfc`) holds the
authoritative planning documents. Branch `sempai-query-pipeline-rfc` sits on
parent `mutation-vertical-slice`; both are documentation-only. Together they
define the planned surface this refresh must document.

Vocabulary used throughout (from ADR 007): a **capability** is a public
abstraction such as `definition.get`, `symbol.rename`, `symbol.move`, or
`patch.apply`; a **perceptor** is a read-only provider; an **actuator** is a
mutation-planning provider that never commits directly; a **provider** is an
implementation (rust-analyzer, Tree-sitter, Rope, Sempai, built-ins) whose
name is hidden from the primary UX. A **selector** is a versioned record
identifying a matched code span; a **selector stream** is JSONL of
`weaver.selector.v1` records terminated by exactly one
`weaver.selector-stream-end.v1` record.

### Source documents (authoritative, with precedence)

All paths relative to the Weaver worktree root. Where documents conflict,
later items in this list lose to earlier ones:

1. `docs/adr-007-agent-native-command-surface.md` — the command-surface
   reset: noun-verb grammar, dual human/`--json` renderers, capability-first
   provider-hidden model, superseded prototype surfaces.
2. `docs/rfcs/0003-sempai-query-to-selector.md` — query → selector stream →
   pipeline → actuator; delivery plateaus; acceptance criteria.
3. `docs/adr-011-sempai-query-input-syntax.md` — `--query` / `--expr` /
   `--rule` (+ `-file` and stdin forms), no auto-detection.
4. `docs/adr-012-versioned-selector-streams.md` — selector schemas,
   `--selectors <path|->`, ordering, stale-source refusal, cardinality
   policy.
5. `docs/rfcs/0002-multi-workspace-daemon.md` with
   `docs/adr-008-workspace-scoped-daemon-tenancy.md`,
   `docs/adr-009-workspace-scoped-language-server-lifecycle.md`,
   `docs/adr-010-workspace-local-concurrency.md` — the server model.
6. `docs/roadmap.md` — phases 12–20 (13 introspection, 14 code-reading
   loop, 15 query slice, 16 safe change loop, 17 graph slices, 19 agent
   workflow: profiles, jobs, delivery sinks, feedback).
7. `docs/ui-gap-analysis.md` — current-vs-target UX matrix; best source of
   principle-level bullet copy.
8. `docs/users-guide.md` — the cleanest planned/built split ("0.1.0
   command-surface target" vs "Current prototype command reference").
9. `docs/weaver-design.md` — vision, Semantic Fusion Engine, workspace
   identity, mutation isolation.
10. `docs/jacquard-card-first-symbol-graph-design.md` — cards, graph
    slices, history matching.
11. `docs/sempai-query-language-design.md` — **language content only**
    (tokens, operators, DSL grammar, diagnostics). Its command-surface
    sections (`weaver observe query`, `--q`) are stale; never copy those.
12. ADRs 001–006 and `docs/rfcs/0001-o11y.md` — plugin capability model,
    routing refusal, verification trust boundary, observability posture.

## Plan of work

### Stage A — plan (this document; complete)

No repository changes beyond this file. Validation: `make markdownlint` and
`make nixie` pass.

### Stage B — reconcile and approve (after the migration lands)

Re-run the two surveys (Weaver branch state; migrated weaver template
structure). Update the per-page file targets below if the migration extracted
shared chrome or renamed files. Update `Progress`, note drift in `Surprises &
Discoveries`, and obtain approval before Stage C. No copy changes yet.

### Stage C — rewrite page copy

Work page by page, committing per page (or per coherent group), gating each
commit. The briefs below are the content specification; every claim they make
traces to the numbered sources above.

**Home (`/weaver/`, currently `templates/weaver/home_page.jinja`).** Keep the
positioning ("CLI tooling for code-aware agents", "the shell should speak the
language of semantics"). Replace the lead's "observe, act, and verify
operations" with the planned framing: resource-first commands
(`weaver symbols list`, `weaver patches apply`, `weaver diagnostics list`),
one human renderer and one stable `--json` contract, a multi-workspace
`weaverd` daemon, and Double-Lock plus Birdcage safety. Replace the terminal
demo with the canonical planned pipeline from RFC 0003:

```sh
weaver symbols list --lang rust --query 'fn $NAME($...ARGS)' --json \
  | jq -c 'select(.schema != "weaver.selector.v1"
           or (.captures.NAME.text | startswith("old_")))' \
  | weaver symbols rename --selectors - --new-name run --dry-run
```

Add one site-wide status statement near the hero: Weaver is in active early
development before v0.1.0; this site documents the 0.1.0 target surface, and
the prototype grammar it replaces is not preserved (README + ADR 007
wording). Fix the language-support bullet to match the Sempai page (Rust,
Python, TypeScript, Go core; HCL optional behind configuration; the first
executable slice covers Rust, Python, and TypeScript). Keep "Composable /
Safe / Fast" value props but reword Composable around selector streams and
noun-verb commands. Remove the hardcoded "Weaver CLI v0.1.0" eyebrow claim or
reword to "0.1.0 target".

**Philosophy (`/weaver/why-weaver/`, `pages/why-weaver.jinja`).** Smallest
change set. Keep the manifesto structure; refresh examples that name
`observe`/`act`/`verify` to the new grammar; add a principle drawn from the
UI gap analysis: errors that teach (every enum-shaped rejection includes the
invalid value, valid values, a stable error code, and a working next
command), bounded responses, and non-interactive-by-default behaviour.

**Architecture (`/weaver/how-it-works/`, `pages/how-it-works.jinja`).** Keep
the Semantic Fusion Engine and client–daemon sections; extend the daemon
section with the multi-workspace model from RFC 0002 / ADRs 008–010: one
local per-user `weaverd`; every request carries a workspace locator that the
daemon (not the client) canonicalizes into a workspace key; workspace-owned
state (caches, language-server pool, mutation coordinator); language servers
keyed by full execution identity so unrelated repositories never share a
process; explicit rustup toolchain resolution with structured `unavailable`
guidance; concurrency without a daemon-wide mutex, with bounded admission and
structured retryable overload results; local-first security (no network
endpoint, no raw paths in logs). Label as planned.

**Commands index (`/weaver/commands/`, `pages/commands.jinja`).** The
biggest rewrite. Replace the three-domain table with the ADR 007 grammar:
`weaver <resource> <verb>` with canonical verbs (`get`, `list`, `create`,
`update`, `delete`, `apply`, `run`, `prune`, `save`, `show`, `rename`,
`move`, `send`). Present the planned command families:

- Read: `definitions get`, `references list`, `diagnostics list`,
  `cards get`, `graph-slices get` (with explicit budget caps).
- Query: `symbols list` with exactly one of `--query | --query-file |
  --expr | --expr-file | --rule | --rule-file`.
- Change: `patches apply`, `symbols rename`, `symbols move` (all with
  `--dry-run`; typed `--selectors <path|->` intake).
- Introspection: `weaver context --json`, `capabilities list`, generated
  help/manpages/completions from one command contract.
- Agent workflow: `profiles save|list|show|delete`, `jobs list|get|prune`
  with `--wait`, delivery sinks (`--deliver stdout|file:|webhook:`),
  `feedback create|list|send`.
- Lifecycle: `daemon start|status|stop` (retained).

Document the cross-cutting renderer rules (`--json` as the single machine
switch; `--plain`, `--color`, `--no-pager`, `--width`, `--locale`; results on
stdout, progress on stderr). State plainly that the `observe`/`act`/`verify`
grammar, root `--output`, per-operation `--format`, and root `--capabilities`
are superseded prototype surfaces.

**Read loop (`/weaver/commands/observe/`, `pages/commands-observe.jinja`).**
Reframe from "the observe domain" to "perception: the code-reading loop"
(roadmap phase 14). Cover `definitions get`, `references list`,
`diagnostics list`, symbol cards (`cards get` with detail levels and bounded
one-hop relation summaries), and budgeted graph slices. Integration examples
use the new commands with `--json` and `jq`.

**Change loop (`/weaver/commands/act/`, `pages/commands-act.jinja`).**
Reframe from "the act domain" to "actuation: the safe change loop" (roadmap
phase 16). One shared mutation engine behind `patches apply`, `symbols
rename`, `symbols move` (public verb `move`; explicitly not `extract-method`;
sibling capability identifiers `extract-method`, `replace-body`,
`extract-predicate` are declared but unimplemented). Two selector entry
points per actuator (direct `--uri`/`--position` or inline `--query`; typed
`--selectors` stream). Document the safety semantics: completion-before-
actuation (no mutation while selector input is still arriving); stale-source
refusal checked twice, with `--force` unable to erase the precondition;
explicit zero/one/many/overlapping-selector policy ("no command guesses
whether a multi-match mutation is intended"); formatting on staged files
before verification; idempotency keys and transaction identifiers surviving
restart; explicit no-op results with a repeated-no-op circuit breaker.

**Verification (`/weaver/commands/verify/`, `pages/commands-verify.jinja`).**
Reframe around the Double-Lock as it appears in the mutation contract:
syntactic lock (Tree-sitter validates final staged content) and semantic lock
(LSP observes the complete proposed delta, diagnostics flushed once per
language); missing semantic backends yield explicit `unavailable` /
`inconclusive` statuses under declared policy — no path silently weakens the
contract. Post-mutation diagnostics classified as introduced,
severity-worsened, resolved, unchanged, or relocated, with concise deltas
inline and full diagnostics behind a bounded spool reference. Carry the
honesty caveat verbatim in spirit: an LSP-clean result does not claim
behavioural correctness. `diagnostics list` is the standalone read surface.

**Safety (`/weaver/safety/`, `pages/safety.jinja`).** Double-Lock and
Birdcage sections stand. Add the mutation-engine guarantees above where they
are safety claims (stale refusal, staged/shadow formatting, rollback with
base and final digests) and the daemon security posture from RFC 0002
(local, single-user, no network authentication; logs carry bounded opaque
workspace identifiers, never raw paths, source contents, or patch bodies).

**Sempai (`/weaver/sempai/`, `pages/sempai.jinja`).** Update, don't
rewrite. Replace `observe query` framing with the ADR 011 input model: bare
structural patterns via `--query` (no mandatory `pattern("…")` wrapper), the
expression DSL via `--expr` (`pattern`, `regex`, `ts`, `inside`, `anywhere`,
`not`, `and`, `or`, `where { focus(...) }`, `as`, `fix`), Semgrep-style YAML
rules via `--rule`, each with `-file` and stdin (`-`) forms, exactly one
accepted per invocation. Add the ADR 012 output story: deterministic
`weaver.selector.v1` JSONL with capture spans, source digests, and query
provenance, terminated by a completion record; canonical ordering; zero
matches is a successful completion-only stream; no invented confidence
scores. Keep the honesty cards (`taint`/`join`/`extract` parse but return
`UnsupportedMode`; `metavariable-type`/`-analysis` return
`UnsupportedConstraint`) and the `E_SEMPAI_*` diagnostics story. Note the
`weaver-syntax-compat-v1` labelled compatibility subset. Sempai selects;
Weaver actuates — `fix` surfaces as metadata only.

**Jacquard (`/weaver/jacquard/`, `pages/jacquard.jinja`).** Content largely
current; keep the "Planned" banner. Update the three commands to the
noun-verb spellings used by the roadmap (`cards get`, `graph-slices get`,
history mode per phase 17) and check quoted defaults against the design doc
at execution time.

**Install (`/weaver/install/`, `pages/install.jinja`).** Keep `cargo
install weaver`, XDG configuration discovery, and daemon auto-start. Replace
`weaver --capabilities` (a superseded root flag) with `weaver capabilities
list --json` and `weaver context --json`. Replace the "first weave"
walkthrough's observe/act/verify loop with a read → query → dry-run change
loop using the new grammar. Note profiles (`--profile`, precedence order)
briefly as the configuration story matures.

**Docs (`/weaver/docs/`, `pages/docs.jinja`).** Update the outbound link
cards to include the new authoritative documents (RFC 0002, RFC 0003, ADRs
007–012, `ui-gap-analysis.md`, `users-guide.md`) with one-line summaries
(the Weaver repo's `docs/contents.md` already provides usable nav copy).
Update the reference sections that restate CLI behaviour (JSONL protocol,
capability discovery) to the new contract; keep protocol/plugin/daemon
sections that remain accurate.

**Roadmap (`/weaver/roadmap/`, `pages/roadmap.jinja`).** Rebuild from
`docs/roadmap.md` phases 12–20: near term — command-surface reset (ADR 007),
introspection and discoverability (phase 13), code-reading loop (14); mid
term — Sempai query slice (15), safe change loop (16), graph slices (17);
long term — agent workflow and assurance (19: profiles, jobs, delivery
sinks, feedback). Mark what is already built (CLI/daemon architecture, LSP
hosting, Tree-sitter, plugin sandbox, Double-Lock, patch application, Sempai
YAML parsing) versus planned. Remove the Discord "Join Discussion" button;
point to GitHub issues, matching the home page.

**Legal pages and design-language page.** No content changes (chrome-level
divergences belong to the migration task).

### Stage D — config and cross-links

In `config/pages.yaml`: keep `hero_tagline: "CLI tooling for code-aware
agents"` (still accurate) but update the main-site homepage card description
(lines 84–88) "Observe, act, verify." to the new story (e.g. "Semantic code
operations as composable shell primitives."), and the reference-library
description (lines 652–661) likewise. Decide with the user whether
`design-language` joins `nav_links` or stays orphaned. Remove or genericize
the hardcoded `v0.1.0` sidebar claims in the chrome templates (or introduce a
`latest_release`-style config value as vk/whitaker have).

### Stage E — consistency sweep and validation

Sweep all weaver templates for: retired grammar strings (`observe`, `act`,
and `verify` as command words, `--output json`, `--capabilities`, `apply-rewrite`,
`refactor`, `get-definition`, `find-references`), Discord contradictions,
language-support claims, and version strings. Then run the full gates and a
visual check (build the site, open `/weaver/` pages, confirm rendering).

## Concrete steps

Stage A (now), from the repository root
`/data/leynos/Projects/df12-www.worktrees/weaver-content-refresh`:

```sh
make markdownlint
make nixie
git add docs/execplans/weaver-content-refresh.md
git commit  # message via the commit-message skill, no -m
```

Stages B–E (after the migration lands; all from the repository root):

```sh
# Re-survey upstream before writing copy
git -C /data/leynos/Projects/weaver.worktrees/sempai-query-pipeline-rfc \
  log --oneline -5

# Regenerate and inspect the weaver site after each page rewrite
bun run build:static
uv run pages generate --site weaver
# open public/weaver/<page>/index.html and inspect

# Gates before each commit (sequentially, never in parallel)
make check-fmt lint typecheck
make test-js
make markdownlint   # if any Markdown changed
make nixie          # if any Markdown changed
```

Expected: all gates exit 0; `pages generate` reports the weaver pages
written; the mobile-nav behavioural test passes against rebuilt output.

## Validation and acceptance

This is a documentation/content task; Red-Green-Refactor with a test
framework does not apply to prose. The observable substitutes are:

- Grep-based red/green for the grammar reset: before Stage C,
  `grep -rn 'observe get-definition\|act apply-patch\|--capabilities' \
  templates/weaver/` returns matches (red); after Stage E it returns none
  outside explicit "superseded prototype" context (green).
- Generated-output check: `uv run pages generate --site weaver` succeeds and
  the rendered pages contain the RFC 0003 canonical pipeline on the home
  page, the noun-verb table on the commands page, and the ADR 011 input
  matrix on the Sempai page.
- Consistency: no page contradicts another on language support, Discord, or
  version claims.
- Gates: `make check-fmt lint typecheck`, `make test-js`,
  `make markdownlint`, `make nixie` all pass.
- Editorial: prose passes a df12-copy voice review and is en-GB-oxendict.

Acceptance for Stage A alone: this file exists at
`docs/execplans/weaver-content-refresh.md`, passes the Markdown gates, and a
reader with no other context can execute Stages B–E from it.

## Idempotence and recovery

All steps are re-runnable: `pages generate` fully rewrites its output;
template edits are ordinary tracked-file changes recoverable via git. No
destructive operations. If a page rewrite goes wrong mid-way, `git restore`
the template and re-apply from the brief. If the Weaver branches are rebased
or renamed upstream, re-run the Stage B survey; the briefs cite documents by
path and claim, so drift is detectable.

## Artefacts and notes

The single most load-bearing quotation for the refresh, from RFC 0003 §2 —
the product the site must now sell:

> "The missing product is therefore not another schema layer. It is this:
> `weaver symbols list --lang rust --query 'fn $NAME($...ARGS) { $...BODY }'
> --json` followed by a stable stream which a human, `jq`, another Weaver
> command, or an agent can consume."

And the compatibility framing from the Weaver README that justifies
documenting the planned surface:

> "The public command surface is now being reset around ADR 007, which makes
> the 0.1.0 target human-friendly and agent-native without preserving
> compatibility with the prototype `observe` / `act` / `verify` grammar."

## Interfaces and dependencies

No code interfaces change. The plan depends on: the df12-www `pages`
generator (`uv run pages generate --site weaver`), Bun for static copy and
JS tests, the Makefile gates listed above, and — as an external gating
dependency — completion of the Weaver daisyUI/Tailwind migration described
in `docs/execplans/incorporate-sub-sites.md` Phase 7. Editorial dependencies:
the `df12-copy` and `en-gb-oxendict` skills at copywriting time.
