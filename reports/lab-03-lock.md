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

<!-- Avec tes mots, 3-5 phrases :
- Que garantit --locked ? (exp. 1, 2 et 4)
- Pourquoi --frozen n'est pas une réparation ? (exp. 3 : exit 0 alors que le lock ne correspond plus)
- Note : en exp. 3, le .venv de la copie contenait déjà les paquets d'un essai précédent ;
  seul bike-demand a été réinstallé, mais la commande n'a fait aucune vérification.
-->

## CI change

Added `uv lock --check` before `uv sync --locked` in `.github/workflows/ci.yml`.
`uv sync --locked` already rejects a stale lock; the separate step makes the failure explicit
and named ("lock is stale") and stops before installing anything.

## Team rule

Never run `uv lock` to turn a failing check green. Change `pyproject.toml` on purpose,
regenerate the lock, review both, and commit `pyproject.toml` and `uv.lock` together.
