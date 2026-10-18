# Local development and LinuxONE deployment guide

## Core execution mode: no third-party dependencies

The core uses Python 3.12 standard-library modules (`sqlite3`, `http.server`,
`datetime`, `decimal`, `json`, threading and argparse). There is no required
`requirements.txt` or dependency installer. The checkout is run through
`PYTHONPATH=src`; no build backend, external ML runtime or GPU is needed. Python,
SQLite and OS libraries remain native platform prerequisites.

Local workstation workflow, from the repository root:

```bash
python3.12 --version
python3.12 -c 'import platform, sqlite3; print(platform.machine(), sqlite3.sqlite_version)'
PYTHONPATH=src python3.12 -m unittest discover -s tests -v
PYTHONPATH=src python3.12 -m fraudguard --db var/local.sqlite3 replay normal
PYTHONPATH=src python3.12 -m fraudguard --db var/local.sqlite3 replay verify
PYTHONPATH=src python3.12 -m fraudguard --db var/local.sqlite3 replay freeze
PYTHONPATH=src python3.12 -m fraudguard --db var/local.sqlite3 serve
```

Keep a second terminal for requests; the server stays in the foreground. Stop it
with Ctrl-C. The portable HTML dashboard is included at `/`; all assets are local.
An optional virtual environment is fine, but no packages need installing. Keep
`var/` and virtual environments out of Git; synthetic SQLite files are ignored.

## LinuxONE / Linux on IBM Z (s390x)

**Not tested on s390x in this task.** No LinuxONE host was available. The code
avoids architecture-specific Python packages; that is a portability design
choice, not evidence of target execution or deployment.

1. Obtain a supported Python 3.12 build for your approved LinuxONE distribution
   through your distribution/vendor process. Do not assume `apt`, a particular
   RPM package, a CUDA runtime or an x86 binary is appropriate. Verify vendor
   signatures and Python maintenance/security updates.
2. Confirm the actual target, runtime and SQLite module:

   ```bash
   uname -m
   python3.12 --version
   python3.12 -c 'import platform, sqlite3, ssl; print(platform.platform()); print(sqlite3.sqlite_version); print(ssl.OPENSSL_VERSION)'
   ```

   Expected machine is `s390x`; Python must be 3.12.x. Resolve a missing `sqlite3`
   module via a supported distribution build, not by silently removing storage.
3. Use the repository checkout already supplied to the task. For a separate host,
   clone through its authorized Git workflow and enter the repository root.
   No worktree or source-copying step is required. Record the exact commit.
4. Choose a local filesystem directory with appropriate ownership, disk space
   and backup policy; do not use network filesystems with uncertain SQLite
   locking. Keep synthetic-only data and avoid multi-user access.
5. Run the tests and replay commands above on the target **before** claiming
   compatibility. Then start the loopback API and validate the health, all three
   scenarios, explanations, histories and expiry with the requests in API.md.
6. On a remote host, use approved access controls and an SSH local port forward:

   ```bash
   ssh -L 8000:127.0.0.1:8000 your-approved-host
   ```

   Start the API on that host separately. The dashboard is then available in a
   local browser. Replace the example host with your authorized host; this task
   does not provision credentials, firewall changes or production infrastructure.

No s390x-specific installer, container image or acceleration claim is supplied.
On the target, validate big-endian serialization and numerical score equality,
SQLite durability/locking, concurrency, bounded-state performance and p95/p99
latency under representative synthetic load. The present test suite checks logic
and basic concurrency, not a production throughput/security certification.

## Optional Streamlit mode

`dashboard/streamlit_app.py` is an optional API client, not a core dependency.
Before installing it, select a supported Streamlit version and verify its
complete Python 3.12/s390x dependency graph, licenses and advisories. Universal
Streamlit wheels do not remove native NumPy/pandas/PyArrow/Pillow requirements.

A check on 2026-10-18 retrieved PyPI metadata for Streamlit 1.66.0 and its native
dependencies. No s390x wheels were listed in those latest-release responses.
The following **download-only resolution**, not installation, failed on NumPy:

```bash
python -m pip download --index-url https://pypi.org/simple --only-binary=:all: \
  --platform manylinux_2_28_s390x --platform manylinux2014_s390x \
  --python-version 3.12 --implementation cp --abi cp312 \
  --dest /tmp/fraudguard-wheel-check streamlit==1.66.0
```

This proves only that PyPI did not resolve that chosen wheel-only combination;
other versions, tags, trusted vendor packages or native builds were not ruled
out. No Streamlit stack was installed in this task. Keep the HTML fallback as the
verified mode until a complete compatible stack is independently established.
Do not disable package verification or relax the Python requirement to use an
old research environment.

If a separately verified environment already provides Streamlit:

```bash
# Terminal 1, repository root:
PYTHONPATH=src python3.12 -m fraudguard --db var/fraudguard.sqlite3 serve
# Terminal 2, same root and verified optional environment:
python3.12 -m streamlit run dashboard/streamlit_app.py --server.address 127.0.0.1
```

The optional adapter reads the loopback API (default port 8000); set non-secret
`FRAUDGUARD_API_URL=http://127.0.0.1:8001` for another local API port. It has
scenario load/replay, risk, factors, correlation, blocks and history controls.
Its source was syntax-checked only; runtime behavior is unverified here.
Streamlit may have additional browser/runtime behavior beyond this adapter, so
the strict offline/no-CDN claim applies to the default HTML dashboard only.

## Operations and limitations

Policy options are persisted with each database. Restart and replay with the same
window/threshold flags or intentionally start a new database. Changing options
against an existing database is rejected. Cooling is always 60 minutes.

The API creates local SQLite tables on startup. No schema-migration framework,
retention scheduler, authenticated reviewer API, encryption, production proxy,
service manager or public exposure is included. Synthetic history is capped;
back up/export a stopped disposable database before archiving it or starting a
new one. Recomputed decisions are not an immutable compliance audit log.

Human review of a real flagged case would require an authorized role, evidence
inspection, independent identity verification, documented reason and disposition,
appeal/correction and oversight. Those controls need a separately secured future
implementation. The current FREEZE only records a simulation in SQLite.
