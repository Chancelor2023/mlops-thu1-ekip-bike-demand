# Week 2, Labs 3: dependency lock, Docker, clean rerun

## Student / team

- **Student:** Brett FAJGENBAUM
- **Team:** Ekip
- **Team repository:** https://github.com/Chancelor2023/mlops-thu1-ekip-bike-demand

## Links to code and pull requests

- **Lab 3 pull request:** Dependency lock by Jerry (https://github.com/Chancelor2023/mlops-thu1-ekip-bike-demand/pull/11)
                          Docker build by Romain (https://github.com/Chancelor2023/mlops-thu1-ekip-bike-demand/pull/12)
                          Base line rerun by Mathis (https://github.com/Chancelor2023/mlops-thu1-ekip-bike-demand/pull/13)
- **Docker image:** [image name and tag, if applicable]

## Test and execution results (commands, revision, observed output)

### Dependency lock

The repository reports uv.lock as current. The lock file is treated as the artifact that drives installation, rather than relying on a developer's local environment. The pyproject.toml and uv.lock files were unchanged during the documented work.

A throwaway clone was used to demonstrate the failure mode for a stale or missing lock file. The intended lesson is that a clean environment must not silently resolve a different dependency graph. The stale/missing-lock demonstration is evidence of the guardrail, not evidence of a successful installation from a stale lock.

The CI workflow includes an explicit check before installation:

    uv lock --check
    uv sync --locked

The first command checks that the lock is consistent with the project metadata. The second installs exactly the locked dependency set. No claim is made here about a particular CI run ID, commit SHA, build log, or test output because those identifiers and logs were not supplied.


### Docker build and baseline rerun

Romain's Dockerfile uses:

- Base image: python:3.12.9-slim
- uv image source: ghcr.io/astral-sh/uv:0.12.19
- A git dependency in the project dependency configuration
- Manifest-first caching: pyproject.toml and uv.lock are copied before the rest of the project
- Locked installation with uv sync --locked --no-install-project
- An exec-form CMD that launches bike_demand.train with configs/baseline.yaml

The Dockerfile copies the following project content into the image:

- data/
- configs/
- tests/
- README.md
- python-version
- reports/
- .github/

The .dockerignore excludes local or generated state, including:

- .venv
- dependency/tool caches
- mlflow.db
- artifacts/
- tracking/
- mlruns/
- .env

The manifest-first order is intended to preserve reusable dependency layers when application code changes. The locked installation and clean build context are intended to prevent host-specific state, secrets, caches, and stale generated outputs from affecting the image.

Important validation note: the README build/rerun commands should be checked against the actual Dockerfile before being treated as the final executable procedure. This report does not assert that an unprovided command sequence, image tag, image ID, architecture, or build log was verified.

Mathis Groult's README work adds a build/rerun section covering prerequisites, image building, container rerun, tests, output collection, MAE reporting, run IDs, and comparison. Jerry Cheng reviewed this documentation.

The section is intended to let another teammate rebuild and rerun the project without asking the original author. The commands still require validation against the actual Dockerfile and repository state. No specific MAE, run ID, model name, image ID, architecture, SHA, or CI/build/test log is recorded here because none was supplied as verified evidence.

## Screenshots


1. ![Description of screenshot 1](reports/images/w2-lab3-pytest-pass.png.png)

2. ![Description of screenshot 2](reports/images/w2-lab3-stale-lock-fail.png.png)


## Blockers / missing evidence

None

## Assistance and recovery acknowledgement

None