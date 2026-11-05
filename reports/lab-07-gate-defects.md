# Lab 7 — Quality Gate: Defects and Regression Tests

The full repository was not available in the mounted files. The cases below are implemented in `tests/test_gate.py`; observed results must be filled in after running in an environment with the project dependencies.

| Defect / scenario | Test | Expected result | Observed result | Explanation |
|---|---|---|---|---|
| Dataset checksum differs from the manifest and metadata | `test_modified_dataset_checksum_blocks` | blocked | To be run | The calculated digest must match the manifest and the declared snapshot. |
| Features reordered | `test_reordered_features_block` | blocked | To be run | The 12-feature contract is checked in exact order. |
| Accepted-model evidence missing | `test_missing_accepted_proof_blocks` | blocked | To be run | A quality/performance comparison without an accepted model, metadata, and metrics is not valid. |
| Negative or non-finite predictions | `test_negative_or_nonfinite_predictions_block` | blocked | To be run | Invalid outputs constitute an integrity failure. |
| Candidate worse than the train mean | `test_candidate_worse_than_train_mean_is_rejected` | rejected | To be run | MAE must be strictly lower than the train-mean baseline on validation. |
| Candidate worse than the accepted model by more than epsilon | `test_candidate_worse_than_accepted_by_more_than_epsilon_is_rejected` | rejected | To be run | Compared on the same validation rows, with epsilon=1e-6. |
| Tie at accepted + epsilon | `test_candidate_at_accepted_plus_epsilon_is_eligible` | eligible, equivalence note | To be run | The accepted threshold is inclusive; a difference within epsilon must not be presented as an improvement. |
| Latency greater than 1.25× the accepted model | `test_latency_over_25_percent_is_rejected` | rejected | To be run | The injected callable simulates measurements without Cloud Run. |
| Model checksum modified | `test_tampered_model_checksum_blocks` | blocked | To be run | The actual digest no longer matches the sha256 recorded in metadata. |
| Candidate metrics missing | `test_missing_candidate_metrics_blocks` | blocked | To be run | An incomplete run cannot pass the gate. |
| Accepted model unchanged after rejected/blocked decisions | `test_accepted_tree_hash_unchanged_after_rejected_or_blocked` | identical before/after hash | To be run | The gate never modifies accepted artifacts. |
| Eligible does not trigger promotion | `test_eligible_random_forest_on_same_validation_and_no_promotion` | no accepted artifacts modified or created | To be run | Promotion is outside the gate's responsibility. |
