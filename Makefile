MDLINT ?= $(shell which markdownlint-cli2)
NIXIE ?= $(shell which nixie)
MDFORMAT_ALL ?= $(shell which mdformat-all)
TOOLS = $(MDFORMAT_ALL) ruff ty $(MDLINT) $(NIXIE) uv bun
VENV_TOOLS = pytest
UV_ENV = UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools
SKIP_PLAYWRIGHT ?= 0
PYTEST_FILTER ?=
TYPOS_VERSION ?= 1.48.0
TYPOS := uv tool run typos@$(TYPOS_VERSION)

ifeq ($(strip $(SKIP_PLAYWRIGHT)),1)
PYTEST_FILTER += -m 'not playwright'
endif

.PHONY: help all clean build build-release lint fmt check-fmt \
        markdownlint nixie spelling test typecheck $(TOOLS) $(VENV_TOOLS) \
	dev

.DEFAULT_GOAL := all

all: build check-fmt lint test test-js typecheck spelling

.venv: pyproject.toml
	$(UV_ENV) uv venv --clear

build: uv .venv ## Build virtual-env and install deps
	$(UV_ENV) uv sync --group dev

# Biome, Tailwind, and the test runner all live in node_modules, so every
# target that shells out to bun has to depend on this. `bun` is order-only:
# it is a phony tool check, and a normal prerequisite would reinstall on
# every run rather than only when the manifest or lockfile moves.
node_modules: package.json bun.lockb | bun ## Install locked JS dependencies
	bun install --frozen-lockfile
	@touch node_modules

build-release: ## Build artefacts (sdist & wheel)
	python -m build --sdist --wheel

clean: ## Remove build artifacts
	rm -rf build dist *.egg-info \
	  .mypy_cache .pytest_cache .coverage coverage.* \
	  lcov.info htmlcov .venv
	rm -f .typos-oxendict-base.json .typos-oxendict-base.toml
	find . -type d -name '__pycache__' -print0 | xargs -0 -r rm -rf

dev: node_modules ## Run the dev server
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

fmt: ruff node_modules $(MDFORMAT_ALL) ## Format sources
	ruff format
	ruff check --select I --fix
	bun run lint:js:fix
	$(MDFORMAT_ALL)

check-fmt: ruff ## Verify formatting
	ruff format --check
	# Biome's formatting is checked by the lint target, which runs
	# `biome check` — formatter, linter, and assists in one pass.
	# mdformat-all doesn't currently do checking

lint: ruff node_modules ## Run linters
	ruff check
	bun run lint:js

typecheck: build ty ## Run typechecking
	ty --version
	ty check

markdownlint: $(MDLINT) ## Lint Markdown files
	$(MDLINT) '**/*.md'
	+$(MAKE) spelling

spelling: ## Enforce en-GB-oxendict spelling in Markdown prose
	@uv run scripts/generate_typos_config.py
	@find . -type f -name '*.md' -not -path './node_modules/*' -print0 | \
		xargs -0 -r $(TYPOS) --config typos.toml --force-exclude

nixie: $(NIXIE) ## Validate Mermaid diagrams
	$(NIXIE) --no-sandbox

test: build uv $(VENV_TOOLS) ## Run tests
	$(UV_ENV) uv run pytest -v $(PYTEST_FILTER)

test-js: node_modules ## Run JavaScript unit tests
	bun run test:js

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":"; printf "Available targets:\n"} {printf "  %-20s %s\n", $$1, $$2}'
