# Local release-image check — 20 November 2026

Jerry built and ran image code `569f2920c0587912a5996bad70957a12fd6c8543` on
Windows Docker Desktop, Linux ARM64. The API tests passed inside the image;
HTTP health/version responses match the frozen accepted model and exact code.
The accepted bundle was bind-mounted read-only; no training or cloud operation
was performed. Raw selected outputs are copied byte-for-byte and hashed in
SHA256SUMS. Full build/image/container snapshots remain under ignored artifacts.

The image ID is local, not a published Artifact Registry digest. This check does
not verify a Cloud Build image, the future merge commit or a live Cloud Run
revision. The container inspect snapshot was captured before Jerry stopped it;
cleanup success was reported separately. Codex assisted with evidence checking
and asset preparation.
