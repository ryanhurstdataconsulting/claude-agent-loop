# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- P0 repo bootstrap: seeded `payload/` from the generalized
  `claude-agent-loop-starter` export (skills, agent, hooks, tools, registry,
  mcp-specs, fragments) plus the top-level README/INSTALL/ARCHITECTURE/SECURITY
  docs and `install.sh`.
- Carried the framework test suite into `payload/tools/tests/` (fixtures
  included), retargeted `test_hook_inject.sh` at the payload hook and its
  `<resource-loop>` tag, and added `payload/tools/tests/run_all.sh` as the
  one-command suite runner.
- Learning seeds: `payload/learning/SCALES.md`, `HEURISTICS.md` (8 seed rules,
  H1–H8), `LOOP_THEMES.md`, and `CLIENT_MARKERS.template.txt`.
- `payload/MANIFEST`, the explicit link-dir/link-file/copy-if-absent list that
  install.sh v2 (P1) will consume to build the symlink engine.
- Repo meta: `VERSION`, this `CHANGELOG.md`, and `LICENSE` (MIT).
