## Team working agreement

* **Team and repository (`mlops-<session>-<team-name>-bike-demand`):** `mlops-thu1-ekip-bike-demand`
* **Members:** Romain Cortyl, Jerry, Mathis
* **Current driver / reviewer / evidence recorder:**
  - Driver: Mathis (Role D, `train.py` implementation)
  - Reviewer: Romain Cortyl (Role C, peer inspection & MLflow audit)
  - Evidence recorder: Romain Cortyl (Role C, report compilation & run capture)
* **Fourth member's temporary responsibility, if applicable:** Not applicable (3-member team rotation)

## Workflow

* Keep each change small and work on a task branch.
* Open a pull request; a different member reviews the diff before merge.
* Record one actionable observation and the author's response.
* Run the relevant local checks and inspect CI on the latest pushed revision.
* Never commit `.venv`, artifacts, tracking databases, credentials or private reports.
* Rotate substantive work; acknowledge supplied code and other assistance.

## Support and handover

* **Approved support route / supported workstation:** Windows 11 x64 / PowerShell with `uv` environment isolation; team communication via private Discord/Teams group and GitHub Issues.
* **How to report a setup or repository-access blocker:** Open a GitHub Issue tagged `blocker` and notify the team immediately via group chat to unblock local configuration before opening a PR.
* **Next driver and unfinished work:** Jerry (Lead B) as next driver for Lab 3 data pipeline automation; current core Lab 1 and Lab 2 requirements are fully completed and verified on `main`.
