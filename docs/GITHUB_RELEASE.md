# GitHub release preparation

This document prepares a future public release. It does not create a GitHub repository, configure
a remote, push commits, create tags, or publish a Release.

## Suggested repository metadata

- Repository name: `BioLab-Copilot`
- Description: `Local-first, traceable biological experiment data analysis and reporting pilot.`
- Suggested topics: `python`, `scientific-computing`, `bioinformatics`, `experimental-data`,
  `reproducible-research`, `gradio`, `quality-control`
- License: MIT

## Before the first push

1. Complete [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) and review the complete Git history.
2. Confirm no real data, secrets, personal information, generated reports, outputs, or local
   absolute paths are present.
3. Create the empty repository manually under the intended GitHub account with the metadata above.
4. Add the remote only after the owner has reviewed the exact URL.
5. Push the reviewed branch and inspect the first GitHub Actions run.

Example commands to execute only after explicit owner authorization:

```powershell
git remote add origin https://github.com/<owner>/BioLab-Copilot.git
git push -u origin master
```

## First GitHub Actions review

Confirm that the Python 3.11, 3.12, and 3.13 matrix jobs install declared dependencies, run
pytest/ruff/mypy, build wheel and sdist, reject generated/private archive members, install the
wheel, import version `0.1.0`, run CLI help, and construct the UI without starting a server.
The workflow must not upload artifacts or reports and must not create a public Gradio share.

Python 3.11 and 3.12 become verified only after their corresponding CI jobs actually pass. The
current local verification claim remains limited to Python 3.13.9.

## v0.1.0 tag and Release draft

After the public branch and CI are reviewed, and only with separate authorization:

```powershell
git tag -a v0.1.0 -m "BioLab Copilot v0.1.0"
git push origin v0.1.0
```

Create a GitHub Release draft from `v0.1.0` with the relevant `CHANGELOG.md` entry. Do not attach
user outputs or private reports. State clearly that the release is a local, research-use pilot,
not clinically validated or production-ready.

## Known limitations

- The current host has verified Python 3.13.9; Python 3.11/3.12 require CI confirmation.
- First-time dependency installation may require network access or a local cache.
- There is no authentication, multi-user deployment, database, cloud service, telemetry, or
  public hosting workflow.
- ELISA inverse estimates are research-only and do not establish validated quantification.

## Rollback

If a public release is found to contain an incorrect document or packaging issue, mark the GitHub
Release as draft or remove it according to repository policy, then publish a corrected release.
Do not rewrite shared history without an explicit incident decision. For a local branch before
publication, inspect and revert only the specific reviewed commit; never use destructive reset
operations without owner authorization.
