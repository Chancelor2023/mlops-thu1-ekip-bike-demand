# Lab 6 contract (agreed by the team before coding)

Decided on 2026-10-23 by Jerry, Romain, Brett and Mathis. Week 3 lead: Brett; main reviewer: Romain.

| # | Decision | Choice | Rejected option and why |
|---|---|---|---|
| 1 | Required checks | quality-and-tests and container must be green to merge into main; branch protection also requires a pull request (no direct pushes). Enabled by Jerry (repo owner) once both checks have run once. | Style checks only: they catch no data or model defect. |
| 2 | Markers | infra, lab1, exercise (incl. test_fault_b.py), api (tests/test_api.py), regression (MAE recomputation), registered in pyproject.toml. Every test file sets pytestmark; CI also runs a final full pytest -q so an unmarked test still runs. | Running markers only: an unmarked test would silently never run (today test_api.py is never run by CI). |
| 3 | Tolerance | Measured first: validation MAE of the RF on laptop (Windows arm64), container (arm64) and GitHub runner (Linux amd64). Identical values → abs=1e-6 (float noise); a difference d → about 2·d, with the three values written in the README. Never any test-period metric. | A guessed ±5 % (would hide a real defect); strict == (breaks on another machine without a defect). |
| 4 | Triggers | pull_request to main, push to main, workflow_dispatch; no paths filter (the suite takes ~25 s); concurrency cancels outdated runs of the same PR. | paths: src/** only: would miss changes in configs/, data/ or the Dockerfile. |
| 5 | Order | lock → ruff check → ruff format → preflight → infra → lab1 → exercise → api → regression → full pytest; container job needs the first job. | Everything in parallel: faster, but the first red step is less clear and a Docker build is wasted. |
| 6 | CI safety | permissions: contents: read, timeout-minutes on every job, actions pinned by commit SHA, uv sync --locked, no secrets. Cloud Run is *not* checked from CI (it would need a Google token secret); it stays a manual check by Jerry in Cloud Shell. | Storing a Google token in GitHub secrets to test Cloud Run from CI. |
| 7 | Defect PRs | Reviewer opens a *draft* PR DO NOT MERGE: defect for <area> from defect/<name>-<area>, with one believable defect unknown to the author. Closed without merging once the red run and its log are saved. A missing test is added by the author in their own PR (red with the defect, green without). | Merging defect PRs: a merge to main redeploys Cloud Run. |

## Owners

| Part | Owner | Reviewer (opens the defect PR) |
|---|---|---|
| Regression tests + defect map | Brett | Mathis |
| Workflow quality-and-tests | Jerry | Romain |
| Workflow container (separate file) | Mathis | Jerry |
| README "CI" + team report Lab 6 | Romain | Brett |

Merge order: tests → workflow → container → README. Tag m3 (Mathis) after Labs 5–6 are reviewed.