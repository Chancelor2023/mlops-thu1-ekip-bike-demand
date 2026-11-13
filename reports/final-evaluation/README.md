# Final held-test evaluation — 13 November 2026

The preselected saved model `baseline-4df84bfe8121` was evaluated once by Jerry,
without retraining or deployment, at 2026-11-13T13:33:11.460451+00:00.
Evaluation source: `474a620de2ceeace6d0d7978c03cb8d7d10128ed`.
The [selection](../final-model-selection.json) and [protocol](../final-evaluation-protocol.md)
were committed before the score was computed. They were on the personal branch at
execution; this is not a claim of a prior merged/peer-reviewed release evaluation.

## Observed result

| Item | Value |
|---|---|
| Model | baseline-4df84bfe8121 |
| Model SHA-256 | d24c050e3631d5b4c2feb8cb571bef6382d8c975c42a5c11edd28de78a0b8c07 |
| Target | cnt: hourly rental count |
| Test population | 4,376 observed hours, 1 July–31 December 2012 inclusive |
| Test MAE | **93.73505906420367 rentals per observed hour** |
| Earlier validation MAE | 86.84685685591091, January–June 2012 |
| Retraining | None |
| Exit code | 0, as reported in the operator's terminal output |

MAE is the mean absolute difference between observed counts and predictions.
Here it is approximately 94 rentals per observed hour. It is not a percent accuracy,
a maximum error or a guarantee on every hour. The test MAE is about 6.89 rentals
higher than validation MAE. These periods differ in population and season; this
comparison alone does not establish drift, overfitting, a causal explanation or
statistical significance. The result must be retained without retuning/selecting
another model on the same test period.

## Why this model was selected

This decision precedes the test score. The retained model's validation MAE was
86.84685685591091 versus 154.23179306864967 for the train-mean baseline. The two
Lab 7 candidates improved MAE slightly (86.74306881621092 and 86.6918618844724)
but failed the unchanged latency-ratio maximum 1.25, with ratios 1.3689584499363496
and 3.4593161890651265. Neither replacement satisfied all gate criteria. The team
therefore kept the accepted artifact with verified bytes and existing service/
recovery evidence. This is an operational tradeoff, not a claim of the best possible
predictive model or a new all-pass gate decision for the original reference.

## Evidence and independent arithmetic check

- [result.json](result.json): actual score, source/model/data identities and environment.
- [predictions.csv](predictions.csv): all observed identities/labels and saved predictions.
- [console.log](console.log): original captured stdout/stderr; the printed JSON equals result.json.
- [started.json](started.json): immutable pre-scoring start snapshot, not the final status.
- [verification.json](verification.json): all 4,376 saved row identities/labels match the frozen
  test partition; finite nonnegative predictions; raw hashes match; the arithmetic mean
  absolute error recomputed from saved predictions agrees within 1e-12.

The verification did not deserialize the model, call predict, fit, or run a second
held-test evaluation. All retained source/model/data/metadata/selection/lock hashes
were rechecked against result.json. `.gitattributes` preserves raw evidence bytes.

This is offline predictive-quality evidence, not an HTTP latency measurement,
Cloud Run deployment, promotion, or new recovery drill. The current accepted
model and its original metadata remain unchanged. Original training commit is
unavailable. The final Release tag will identify a later packaging revision; do
not relabel this evaluation as having run on that future tag.

Codex assisted with preparation and evidence verification. Jerry executed the
real final evaluation in Git Bash on Windows; environment versions are in result.json.
