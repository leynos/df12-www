# `command -v` rather than `which`: under `bun run`, node_modules/.bin leads
# PATH, and the `which` npm package (a stylelint dependency) installs a shim
# there that starts node on every lookup, slowing every nested make.
# The fallback is Bun's global bin, where the estate installs the linter,
# so a missing linter is reported by name rather than leaving MDLINT empty.
MDLINT ?= $(shell command -v markdownlint-cli2 2>/dev/null || printf '%s' "$$HOME/.bun/bin/markdownlint-cli2")
# `make fmt` and `make check-fmt` call mdtablefix directly. `--git` selects the
# Markdown files Git tracks and `--include-untracked` adds the untracked files
# Git does not ignore, so a new document is formatted before it is staged.
# Both modes need mdtablefix 0.6.0 or later; CI pins the version at the
# install-mdtablefix step.
MDTABLEFIX ?= mdtablefix
MDTABLEFIX_SELECT = --git --include-untracked
MDTABLEFIX_RULES = --wrap --renumber --breaks --ellipsis --fences
NIXIE ?= $(shell command -v nixie)
TOOLS = $(MDLINT) $(NIXIE) uv bun
VENV_TOOLS = pytest
UV_ENV = UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools
# Ruff comes from the dev group, so uv.lock fixes its version; ty is pinned
# here. A new release of either therefore cannot fail the gates on code
# nobody has changed: moving to it is a deliberate bump and its fixes.
# The gates run the Ruff that `make build` installed, straight from the
# virtualenv, so checking never resolves, syncs, or rewrites the environment;
# `uv run` would sync it first.
RUFF = .venv/bin/ruff
TY_VERSION ?= 0.0.82
TY = $(UV_ENV) uv tool run ty==$(TY_VERSION)
SKIP_PLAYWRIGHT ?= 0
PYTEST_FILTER ?=
TYPOS_CONFIG_BUILDER_VERSION ?= v0.1.1
TYPOS_CONFIG_BUILDER = uv tool run --from \
	"git+https://github.com/leynos/typos-config-builder.git@$(TYPOS_CONFIG_BUILDER_VERSION)" \
	typos-config-builder
NODE_MODULES_STAMP := node_modules/.install-stamp
EPISODIC_SOURCE ?= ../episodic
CUPRUM_SOURCE ?= ../cuprum

ifeq ($(strip $(SKIP_PLAYWRIGHT)),1)
PYTEST_FILTER += -m 'not playwright'
endif

.PHONY: help all clean build build-release lint fmt check-fmt check-site-data \
        cuprum-api-data check-cuprum-api-data \
        docs-check markdownlint nixie site-data spelling stylelint test typecheck \
        typecheck-js venv-ruff \
        $(TOOLS) \
        $(VENV_TOOLS) dev

.DEFAULT_GOAL := all

all: build check-fmt lint stylelint test test-js typecheck docs-check spelling

.venv: pyproject.toml
	$(UV_ENV) uv venv --clear

build: uv .venv ## Build virtual-env and install deps
	$(UV_ENV) uv sync --group dev

site-data: ## Regenerate committed Episodic data from its authoritative roadmap
	uv run scripts/build_episodic_roadmap_data.py --episodic-root "$(EPISODIC_SOURCE)"

check-site-data: ## Check the committed Episodic roadmap projection for drift
	uv run scripts/build_episodic_roadmap_data.py --episodic-root "$(EPISODIC_SOURCE)" --check

cuprum-api-data: ## Regenerate the Cuprum API reference from a Cuprum checkout at the documented release
	uv run scripts/build_cuprum_api_data.py --cuprum-root "$(CUPRUM_SOURCE)"

check-cuprum-api-data: ## Check the committed Cuprum API reference against its source
	uv run scripts/build_cuprum_api_data.py --cuprum-root "$(CUPRUM_SOURCE)" --check

# Biome, Tailwind, and the test runner all live in node_modules, so every
# target that shells out to bun has to depend on this. `bun` is order-only:
# it is a phony tool check, and a normal prerequisite would reinstall on
# every run rather than only when the manifest or lockfile moves.
#
# The target is a stamp file rather than the node_modules directory itself.
# A failed install still leaves a directory behind, with an mtime newer than
# the manifest that triggered it, so make would call it up to date and every
# later run would skip the install and fail in the recipe instead. The stamp
# is written only when bun exits cleanly, so a failure is retried. It lives
# inside node_modules, so removing the tree removes the stamp with it.
$(NODE_MODULES_STAMP): package.json bun.lockb | bun ## Install locked JS dependencies
	bun install --frozen-lockfile
	@touch $@

build-release: ## Build artefacts (sdist & wheel)
	python -m build --sdist --wheel

clean: ## Remove build artifacts
	rm -rf build dist *.egg-info \
	  .mypy_cache .pytest_cache .coverage coverage.* \
	  lcov.info htmlcov .venv
	rm -f .typos-oxendict-base.json .typos-oxendict-base.toml
	find . -type d -name '__pycache__' -print0 | xargs -0 -r rm -rf

dev: $(NODE_MODULES_STAMP) ## Run the dev server
	$(MAKE) build
	bun run dev

define ensure_tool
	@command -v $(1) >/dev/null 2>&1 || { \
	  printf "Error: '%s' is required, but not installed\n" "$(1)" >&2; \
	  exit 1; \
	}
endef

define ensure_tool_venv
	$(UV_ENV) uv run which $(1) >/dev/null 2>&1 || { \
	  printf "Error: '%s' is required in the virtualenv, but is not installed\n" "$(1)" >&2; \
	  exit 1; \
	}
endef

ifneq ($(strip $(TOOLS)),)
$(TOOLS): ## Verify required CLI tools
	$(call ensure_tool,$@)
endif


ifneq ($(strip $(VENV_TOOLS)),)
.PHONY: $(VENV_TOOLS)
$(VENV_TOOLS): ## Verify required CLI tools in venv
	$(call ensure_tool_venv,$@)
endif

venv-ruff: ## Verify the locked Ruff is installed; `make build` installs it
	@test -x $(RUFF) || { \
	  printf "Error: '%s' is missing; run 'make build' to install the locked dev tools\n" "$(RUFF)" >&2; \
	  exit 1; \
	}

fmt: build $(NODE_MODULES_STAMP) ## Format sources
	$(RUFF) format
	$(RUFF) check --select I --fix
	bun run lint:js:fix
	# Safe over the generated Pygments blocks: the generators emit
	# stylelint-disable markers around them, and fixes are not applied
	# inside a disabled range.
	bun run lint:css:fix
	$(MDTABLEFIX) --in-place $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)
	@unset FORCE_COLOR; $(MDLINT) --fix "**/*.md"

check-fmt: venv-ruff ## Verify formatting
	$(RUFF) format --check
	# Biome's formatting is checked by the lint target, which runs
	# `biome check` — formatter, linter, and assists in one pass.
	$(MDTABLEFIX) --check $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)

lint: venv-ruff $(NODE_MODULES_STAMP) ## Run linters
	$(RUFF) check
	bun run lint:js

stylelint: $(NODE_MODULES_STAMP) ## Lint the handwritten and Tailwind CSS
	# Lint only: Biome formats the CSS, so this is the rule set in
	# stylelint.config.js over src/**/*.css and nothing else.
	bun run lint:css

typecheck: build typecheck-js ## Run typechecking
	$(TY) --version
	$(TY) check

typecheck-js: $(NODE_MODULES_STAMP) ## Typecheck the browser scripts and build scripts
	bun run typecheck:js

markdownlint: $(MDLINT) ## Lint Markdown files
	$(MDLINT) '**/*.md'
	+$(MAKE) spelling

spelling: ## Enforce en-GB-oxendict spelling in Markdown prose
	$(TYPOS_CONFIG_BUILDER) gate --repository .

nixie: $(NIXIE) ## Validate Mermaid diagrams
	$(NIXIE) --no-sandbox

test: build uv $(VENV_TOOLS) ## Run tests
	$(UV_ENV) uv run pytest -v $(PYTEST_FILTER)

docs-check: $(NODE_MODULES_STAMP) ## Validate TypeScript documentation with TypeDoc
	bun run docs:check

test-js: $(NODE_MODULES_STAMP) ## Run JavaScript unit tests
	# The suite loads the built copies under public/, so the copy and compile
	# steps have to run first or a source change is tested in its previous
	# form.
	bun run build:static
	bun run build:js
	bun run test:js

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":"; printf "Available targets:\n"} {printf "  %-20s %s\n", $$1, $$2}'
