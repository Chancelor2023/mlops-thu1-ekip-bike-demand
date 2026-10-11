# Lab 1 Evidence and Report

## Team and setup

* **Team/repository:** `mlops-thu1-ekip-bike-demand`
* **Week/date:** Week 1 / October 11, 2026
* **Members and temporary roles:**
  - Lead B: Jerry (Repository setup, coordination)
  - Role C: Romain Cortyl (Author edge-case test, peer reviewer)
  - Role D: Mathis (Collaborator, runner verification)
* **Repository/authentication access checks:** SSH/HTTPS git authentication verified; clone and branch push successful on remote origin.
* **Mac version/architecture, Python and uv versions:** Windows 11 x64, Python 3.12 (via uv), uv version 0.5+
* **Environment/preflight command and actual outcome:** `uv run --locked pytest -q -m lab1` passed (4 passed, 44 deselected in 77.76s).
* **Working agreement and backlog links:** GitHub Issues & Project Board: `https://github.com/Chancelor2023/mlops-thu1-ekip-bike-demand/projects`
* **Ignored outputs and secret-protection checks:** `.gitignore` verified (ignoring `.venv/`, `artifacts/`, `tracking/mlflow.db`, `__pycache__/`, local cache files).

## Reviewed change and checks

* **Branch, pull request and checked commit:** Branch `Romain-Cortyl's-branch`, PR #7 (`https://github.com/Chancelor2023/mlops-thu1-ekip-bike-demand/pull/7`), merged into `main`.
* **Substantive change and responsible contributor:** Romain Cortyl (Role C) implemented additional normalization unit test in `tests/lab1/test_team.py`.
* **Additional test and why it is useful:** Added `test_normalize_team_slug_multiple_spaces_and_tabs`. It guards against edge cases where dirty user input contains consecutive whitespaces or horizontal tabulations, ensuring string sanitization cleanly collapses them into single hyphens.
* **Reviewer observation, response and merge status:** Reviewed and approved by Lead B; confirmed all tests pass locally and on GitHub Actions CI; merged into `main`.
* **Local lint/format/test commands and actual results:**
  - `uv run --locked ruff format tests/lab1/test_team.py` -> 1 file left unchanged
  - `uv run --locked ruff check tests/lab1/test_team.py` -> All checks passed!
  - `uv run --locked pytest -q -m lab1` -> 4 passed, 44 deselected
* **Intentional exercise failure versus infrastructure failures:** Exercise tests were deliberately failing prior to slug normalization fix; no unexpected infrastructure/network failures.
* **CI check names, actual statuses and checked revision:** CI Workflow `ci.yml` / job `test` passing (`success`) on commit merged to `main`.
* **Starter/reference/collaborator/other assistance:** Repository documentation and starter guidelines.

## Lab 2 handover

* **Next driver/reviewer:** Mathis (Role D) as driver for `train.py`; Romain Cortyl (Role C) as peer reviewer.
* **Readiness and remaining blockers:** Repository clean, dependencies synchronized with `uv.lock`, no remaining blockers.
* **One bounded next action and owner:** Mathis (Role D) implements feature selection and RF training; Romain (Role C) reviews PR and verifies MLflow tracking.
* **Own-contribution links retained for each student's Week 1 report:** PR #7 retained for Romain Cortyl.

## Screenshots

* **Image and caption:**
  - `![Lab 1 test execution](images/Test_team.png)`: Local terminal execution showing `ruff format`, `ruff check`, and `pytest -q -m lab1` passing 4 tests on `Romain-Cortyl's-branch`.
  - `![Lab 1 test code](images/Test-team-program.png)`: Implementation of `test_normalize_team_slug_multiple_spaces_and_tabs` in `tests/lab1/test_team.py`.
