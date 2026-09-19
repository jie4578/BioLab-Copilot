# Public release checklist

This checklist is for review before any GitHub remote, push, tag, or Release action. Phase 4D
does not execute those actions.

## Scope and documentation

- [ ] README explains the problem, four supported workflows, local operation, synthetic demo,
      research-use limitations, unsupported scope, and deterministic/AI separation.
- [ ] `CHANGELOG.md` describes only implemented behavior and does not imply clinical validation.
- [ ] `LICENSE` is present and matches the intended license.
- [ ] `SECURITY.md` and `CONTRIBUTING.md` prohibit real data and secrets.
- [ ] Windows installation, demo, pilot acceptance, architecture, and release instructions are
      internally consistent.
- [ ] No unverified CI badge, download number, provider claim, or production claim is present.

## Scientific and privacy boundary

- [ ] Raw source data remains immutable and is absent from Git.
- [ ] QC warnings, plan confirmation, hashes, and research-only labels remain visible.
- [ ] No new scientific method, threshold, data-contract meaning, AI, database, cloud, telemetry,
      or network runtime feature was added.
- [ ] No Antibody AI repository or other project was read or copied.

## CI and build

- [ ] `.github/workflows/ci.yml` parses and runs on push and pull request.
- [ ] Python 3.11, 3.12, and 3.13 jobs run declared tests, ruff, mypy, wheel/sdist build,
      archive inspection, wheel import, CLI help, and UI construction smoke checks.
- [ ] CI uses synthetic tests only and does not upload artifacts or reports.
- [ ] Wheel and sdist contain no outputs, caches, virtual environments, secrets, private files,
      local absolute paths, or `tests/phase2a-boundaries-lliqpk1e/`.
- [ ] No PyPI publication occurs as part of this preparation.

## Git and history

- [ ] Current-tree secret/path scan is clean or every finding is documented and non-sensitive.
- [ ] Complete Git history scan is clean; history is not rewritten automatically.
- [ ] `git status` and staged file list contain only the reviewed scope.
- [ ] No remote, push, tag, or Release was created without separate authorization.
- [ ] `tests/phase2a-boundaries-lliqpk1e/` remains untouched.
