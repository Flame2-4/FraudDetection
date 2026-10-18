# FraudGuard AI project instructions

These instructions apply to this entire repository and future development tasks.
Read [the research bibliography](docs/REFERENCES.md) and
[the proposed architecture](docs/ARCHITECTURE.md) before changing the design.

## Scope and development sequence

Preserve this sequence; complete and review each phase before starting the next:

1. Research knowledge base.
2. Fraud fusion engine.
3. Mock real-time telemetry streams.
4. Risk scoring and payment intervention simulation.
5. Streamlit dashboard.
6. LinuxONE deployment and testing.

The current task is phase 1 only. Do not implement application code, install
application dependencies, create telemetry generators, train models, integrate
payments, or build the dashboard during this phase. Existing starter code is not
an approved or validated production design. Later phases require a subsequent
user task; this document does not authorize advancing automatically.

## Engineering requirements

- Require Python 3.12 compatibility. Prioritize Linux on IBM LinuxONE / IBM Z
  (s390x) as the deployment target. Keep a CPU-only path; never assume CUDA,
  an x86 instruction set, or access to hardware acceleration.
- Write readable, modular, tested, documented code with explicit interfaces,
  type annotations where useful, small responsibilities, and actionable errors.
  Keep ingestion, normalization, feature adapters, correlation, scoring, policy,
  storage, and presentation separate. Avoid speculative infrastructure.
- Implement original project code. Do not copy code, notebooks, scripts, model
  implementations, or configuration from reference repositories, even where a
  license permits copying. Cite conceptual inspiration. Normal dependency use
  is distinct from copying; review licenses for dependencies, data and weights.
- Review existing files and Git status before edits. Preserve unrelated work.
  Use the existing checkout in this isolated cloud environment; do not create a
  Git worktree unless the user explicitly requests one.
- Maintain docs alongside behavior. Label evidence, hypotheses, design proposals,
  measured results, and simulated signals distinctly. Never invent citations,
  benchmark results, link checks, platform support, or security guarantees.

## Dependency and platform gate

Before adding any dependency, check its Python 3.12 requirement, license,
maintenance, security advisories, transitive dependencies, s390x artifact
availability, native libraries, build requirements, and CPU behavior. Prefer the
standard library and small pure-Python dependencies where practical. A universal
wheel does not establish compatibility of native transitive dependencies.

Pin a reproducible compatible set when implementation begins; retain lockfiles,
artifact hashes, build provenance and dataset/model versions. Never disable TLS,
artifact checksums, package signatures, or failing tests to make installation
succeed. Record wheel versus native-build evidence per selected version, Linux
distribution, glibc, ABI, and architecture. Run actual tests on s390x with Python
3.12 before claiming LinuxONE compatibility; x86 tests and metadata are insufficient.
Do not downgrade the project Python requirement to run an old research stack.

## Security, privacy and safety gate

- Threat-model spoofed telemetry, entity mis-linking, replay, malicious media,
  model tampering, resource exhaustion, and unauthorized access.
- Validate schemas, sizes, timestamps and provenance at trust boundaries;
  authenticate producers, enforce tenant isolation and least privilege, protect
  transport/storage, and isolate media decoding with resource limits.
- Never commit credentials, personal financial records, biometric recordings,
  identity documents, or sensitive logs. Use synthetic fixtures by default;
  minimize identifiers and use tenant-scoped pseudonyms with protected keys.
- Document purpose, consent or other applicable lawful basis, access, retention,
  deletion and audit controls before processing real data. Embeddings and derived
  features may remain sensitive; hashing alone is not anonymization.
- Keep payment intervention simulated and explicitly labeled. No live payment
  credentials, banking calls, real holds or transfers in the MVP. Require human
  review and an appeal/correction path for consequential decisions.

## Verification and research discipline

For future implementation, test normal and adverse paths: missing modalities,
low confidence, duplicates, out-of-order/late events, clock skew, retries, score
boundaries, tenant isolation, deletion, deterministic replay and simulated policy
transitions. Add integration checks for alert explanations and idempotency.

Evaluate fraud models with temporal splits, label-availability delays, held-out
entities where appropriate, imbalance-aware metrics, calibration, subgroup
analysis and drift checks. Split related media by source/speaker/session to
prevent leakage. Report false positives, false negatives and review workload,
not accuracy alone. Compare channel-only baselines with fusion using ablations.

Record seeds, configurations, dataset licenses/checksums, model provenance,
platform details, commands, counts and limitations. Distinguish executed tests
from planned checks. For documentation-only work, verify links and content,
review the diff and branch, and do not install dependencies or run unrelated
application builds.
