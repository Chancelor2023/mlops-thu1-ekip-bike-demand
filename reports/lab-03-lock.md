# Lab 3: Locked dependencies

Owner: Jerry 
Reviewer: Mathis
Checked revision: `0eee89b` (main)

## Experiments

Experiments 2–4 were run on a throwaway clone (`lock-test`), deleted afterwards.
The team repository's `pyproject.toml` and `uv.lock` were never modified.

| # | Situation | Command | Exit | Observed message | Raw log |
| --- | --- | --- | --- | --- | --- |
| 1 | Committed lock, unchanged | `uv lock --check`, `uv sync --locked` | 0, 0 | `Resolved 98 packages`, `Checked 97 packages` | [01-lock-ok.log](logs/lab-03/01-lock-ok.log) |
| 2 | Stale lock (`numpy>=1.26` changed to `>=2.1` in pyproject.toml) | `uv lock --check`, `uv sync --locked` | 1, 1 | `The lockfile at uv.lock needs to be updated, but --check / --locked was provided.` | [02-stale-lock.log](logs/lab-03/02-stale-lock.log) |
| 3 | Same stale lock | `uv sync --frozen` | **0** | no error: the mismatch is not detected | [03-frozen-hides-stale.log](logs/lab-03/03-frozen-hides-stale.log) |
| 4 | Missing lock (`uv.lock` deleted) | `uv sync --locked` | 1 | `Unable to find lockfile at uv.lock, but --locked was provided.` | [04-missing-lock.log](logs/lab-03/04-missing-lock.log) |

## Explanation

`--locked` compares `pyproject.toml` with the committed `uv.lock` before installing
anything. When they disagree (experiment 2) or when the lock is missing (experiment 4),
uv stops with exit code 1, so nobody can silently install versions that were never
reviewed. `--frozen` skips that comparison: in experiment 3 it returned exit code 0 with
a stale lock, so the mismatch was hidden instead of fixed. (In that copy the `.venv`
already held the packages from an earlier attempt, so only `bike-demand` was reinstalled,
but no consistency check was made.) Running `uv lock` just to make the error disappear
would rewrite the lock with unreviewed versions, which is why the team rule below exists.


## CI change

Added `uv lock --check` before `uv sync --locked` in `.github/workflows/ci.yml`.
`uv sync --locked` already rejects a stale lock; the separate step makes the failure explicit
and named ("lock is stale") and stops before installing anything.

## Team rule

Never run `uv lock` to turn a failing check green. Change `pyproject.toml` on purpose,
regenerate the lock, review both, and commit `pyproject.toml` and `uv.lock` together.
