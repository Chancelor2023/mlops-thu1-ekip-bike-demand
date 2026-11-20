# Demo rehearsals — 13 November 2026

Jerry executed these runs on Windows with Docker; Codex assisted with script
corrections, checks and documentation. No new live run is claimed by this update.
The checked demo source was `44cd4e94d53d5811a55437c093459747e82f1de4`.
The local image ID was
`sha256:01f986632a69e5d5e53db7733d273da8f193e291938ae121445bf69f415e08e5`.

| Retained run | Observed outcome |
|---|---|
| `20261113T140649Z-2131-5988` | Local rehearsal with API tests: exit 0; health 200, valid prediction 200, invalid input 422 |
| `20261113T141902Z-2305-4448` | Cloud authentication attempt failed: health 401, no returned request ID; exit 1 |
| `20261113T142351Z-2390-3272` | Full local/cloud rehearsal: exit 0; cloud health 200, valid prediction 200, invalid input 422 |

The successful cloud responses identify `baseline-4df84bfe8121` and historical
code `ea37b8a45d4a6738585d9de7d0f95d624ad1d3be`. The local and deployed code
revisions intentionally differ. The successful prediction was 61.68078588386617.
The failed 401 remains a failed attempt; a later success does not erase it.
No cause is inferred solely from a 401 or from a token's decoded payload.

[Selected original records](demo-rehearsal-20261113/) retain source/image IDs,
exit codes and available client HTTP records, copied byte-for-byte from the
ignored demo folders. [SHA256SUMS](demo-rehearsal-20261113/SHA256SUMS) covers these
copies. Request IDs here are client observations; no independent server-log
correlation is claimed for these demo runs. They do not prove current cloud
availability, cold-start latency, model quality or a newly deployed release.

Romain left positive **COMMENTED** feedback on
[PR #42](https://github.com/Chancelor2023/mlops-thu1-ekip-bike-demand/pull/42#pullrequestreview-5892546833).
This is not a formal APPROVED review or evidence that he independently ran it.
