# VideoGuard browser-frame prototype

This is experimental frame-based image classification, **not a temporal video
model**. No calibrated probability, video classification threshold or demonstrated
real-world accuracy is claimed. The user reports 8/10 on five real/five fake
examples (five real and three fake correctly classified); this tiny experiment
is not independent validation. No payment action or fusion/history write occurs.
Existing financial inference, scenarios and simulated enforcement are unchanged.
Audio and fusion video signals remain simulated; VideoGuard is a separate real
inference panel when its optional local inference dependencies are available.

## Data flow and limits

The browser accepts MP4/WebM only when its native decoder succeeds. MIME and
extension are not proof of codec support. It checks nonempty size <=50 MiB,
finite duration <=60 seconds and dimensions 32×32 through 1920×1080. No original
video is uploaded. Five timestamp samples span the clip; the last is at 99.9%
to avoid seeking beyond available media. Native seeking is approximate: it is
not identical to OpenCV's linspace over frame indices, especially with variable
frame rates and very short clips. Metadata loading, initial pixel readiness and seeking each have a 10s timeout.
Each file selection gets a fresh video element with `preload="auto"`. Metadata
listeners are attached before assigning the object URL; dimension/duration
validation runs only after that source emits `loadedmetadata` with
`HAVE_METADATA`. Canvas drawing separately waits for decoded pixels. This avoids
using a stale `loadeddata` event from a reused/reset element as a metadata gate.

File replacement/clear aborts pending listeners, detaches the old media source,
then revokes its object URL. The active URL stays valid through preview and
sampling. Error cleanup resets the media element, so zero dimensions/readyState
observed after an error do not identify the original failure state. A failure
before metadata now reports metadata timeout or decoding failure rather than
premature dimension validation.

CSP remains `connect-src 'self'` and `media-src 'self' blob:`. Native video
loading uses `media-src`; no JavaScript blob fetch is needed. A manually issued
`fetch(blobURL)` is intentionally blocked and does not establish that the native
video decoder was blocked. Browser regression tests cover delayed metadata,
early/stale `loadeddata`, replacement, cancellation, timeout, URL lifetime and
a synthetic 1280×720 MP4, without weakening CSP.

For each sample the operator selects the largest face using percentage controls.
The preview adds `floor(0.25 * max(face_width, face_height))` pixels on every side,
clipped to the source boundaries. This matches the supplied padding rule but
manual selection differs from Haar detection; **end-to-end Kaggle parity is not
established**. There is no face detection/tracking. If a face cannot be selected,
clear/reject that video rather than interpret missing faces as real. Every crop
must be confirmed. Source-resolution crops are encoded as JPEG (quality .9),
without frontend resizing or normalization. JPEG compression/browser color
handling can change pixels compared with Kaggle's original RGB crops.

Same-origin POST `/api/video/jobs` accepts JSON `{duration, frames}` with each
frame `{timestamp, image}` (bare base64 JPEG). It returns 202 with an opaque
`job_id`. GET `/api/video/jobs/<id>` returns queued, processing, complete or
failed; unknown/expired IDs return 404. Results include per-frame timestamps and
scores, mean Deepfake score, count, model, warnings and advisory status, with no
classification. IDs are capabilities, not authentication; do not share them.

Server limits: request body <=3 MiB before reading; no transfer encoding; max
two concurrent upload readers; <=8 frames, <=256 KiB per JPEG, dimensions
32×32 through 1920×1080 checked before full decode. The browser sends five frames;
the API permits 1–8 for diagnostic use. Oversized JPEG crops must be reselected
or rejected, not silently downscaled. Metadata timestamps must be finite,
strictly increasing, within a declared duration <=60s. Declared original video
properties cannot be independently verified from submitted frames alone.
Existing routes retain their 64 KiB limit. Upload reads use the existing 5s
socket timeout; an upload failure can require retrying over a slow tunnel.

One persistent spawned CPU worker processes one job at a time with at most one
queued job. It lazily imports the optional libraries and loads the model once;
sets Torch/OMP threads to two; processes frame inference sequentially; and is
terminated/recreated after timeout or failure. Each job has a 180s deadline
including cold model loading. The browser stops polling after 390s (allowing one queued job plus cold inference), with bounded
10s requests. Stopping browser waiting does not cancel a submitted server job.
No media is written to disk or SQLite. At most 16 results are retained, expire
five minutes after completion/failure, and are lost on restart. Frames are released after jobs;
the bounded queue temporarily retains submitted bytes. Model memory persists.

Image bounds and job limits bound application allocations, not the entire Torch
runtime's address space. For deployment, apply OS/service CPU and memory limits
appropriate to measured model usage; the process boundary is not a hardened
sandbox against decoder/native-library vulnerabilities. Only use consented or
synthetic media. Do not log media, filenames or job payloads. There is no
production authentication/tenant isolation; preserve loopback serving and use
an SSH tunnel. Do not expose this server publicly.

## Local model and preprocessing

Fixed default path: `/home/ibm-user/VideoGuard/model`; no client path is accepted.
`AutoImageProcessor` reads the actual local processor configuration; no resize,
rescale or normalization constants are invented. CPU
`AutoModelForImageClassification` must have labels exactly `0: Realism`,
`1: Deepfake`; inference uses `torch.inference_mode()` and
`torch.softmax(logits, dim=-1)[0,1]`. The aggregate is arithmetic mean of usable
frame scores. This version fails the whole job if any submitted frame fails,
rather than quietly changing the denominator. No financial 0.30 threshold is used.

Loading is local-only with remote code disabled and **safetensors required**.
If the existing download contains only pickle `.bin` weights, serving fails
closed. Review source/provenance and export trusted weights to safetensors in
the model preparation environment; do not enable untrusted deserialization.
Verify licenses, model revision, weight/config hashes and processor provenance.

## Manual LinuxONE deployment and acceptance

No target deployment or restart was performed by this change. The development
host is x86_64; actual s390x inference is not validated here. User reports
Python 3.12, PyTorch 2.11.0+cpu and Transformers 5.19.0 already working on target.
No new serving dependency is introduced: video inference additionally uses the
existing target Torch/Transformers/Pillow stack; finance remains stdlib-only.
Pillow JPEG support is still required; no FFmpeg, OpenCV or PyAV is used.

Before manually updating the service:

1. Record the current commit and service configuration for rollback. Review the
   diff and optional dependency security/license/build provenance. Keep the
   working Python environment; do not install replacement x86 wheels on s390x.
2. Verify Python 3.12, architecture, CPU libraries, Pillow JPEG decoding,
   `config.json`, `preprocessor_config.json`, local safetensors and label mapping.
   Record processor configuration and SHA-256 hashes of every model artifact.
   Ensure the service account can read only the intended model directory.
3. Run `PYTHONPATH=src python3.12 -m unittest discover -s tests -v` in a test
   checkout. Video synthetic decoder tests require Pillow; no weights are used.
4. Produce identical consented/synthetic cropped JPEG files and Kaggle reference
   scores by decoding those **same JPEG bytes** through the same processor/model.
   Create a manifest list with `image`, `sha256`, `expected_score`. Run:

   ```sh
   PYTHONPATH=src python3.12 tools/verify_video_images.py reference_crops.json
   ```

   Default absolute tolerance is 1e-6; review differences rather than relax it
   blindly. This proves only image-level score parity, not original video parity.
5. In a separate test service/port, run the normal command:
   `PYTHONPATH=src python3.12 -m fraudguard serve --port 8001`.
   Forward that loopback port with SSH. Test Windows Chrome/Edge MP4/H.264 and
   WebM support, five previews, padding/boundary clipping, short/variable-rate
   clips, invalid files, repeated jobs, refresh/clear and expired results.
6. Measure cold/warm latency, peak RSS, Torch thread use and request responsiveness
   while financial scoring runs during video inference. Exercise full queue,
   timeout and recovery, missing model, wrong labels and malformed images.
   Review the 180s deadline, memory/service limits and two-thread budget from
   these measurements before the presentation. No performance SLA is established.
7. Run all financial/scenario/audit/cooling-off regressions and confirm no video
   writes or fusion changes. Only then manually promote/restart the service.

Optional development browser checks (preinstalled Playwright + Chromium only):
`PYTHONPATH=src:tests python3.12 tests/browser_video.py` and
`PYTHONPATH=src:tests python3.12 tests/browser_smoke.py`.
The video browser suite uses a clearly isolated test worker, not real model
scores. Actual model parity and s390x resource acceptance remain manual gates.
