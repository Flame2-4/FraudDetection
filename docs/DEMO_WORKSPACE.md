# FraudGuard presentation workspace

Scope: Financial Fraud Detection + VideoGuard. Both detectors are advisory.
No new voice detector, trained model, decision threshold or serving dependency
was added. All payment intervention remains simulated. The existing financial
API and VideoGuard job API, resource limits, CSP and retention are unchanged.

## Judge workflow

The two overview cards and primary sidebar links open **Financial Fraud** or
**Video Deepfake**. One detector occupies the main workspace at a time; switching
does not discard inputs, video crops or ongoing analysis. The smaller
**Investigation lab** links retain the existing synthetic fusion scenarios,
event investigation, history and human-review information. Its legacy simulated
audio/video telemetry is separate from real VideoGuard inference.

Financial Fraud: enter the five PaySim fields or select a verified editable
example, then click **Analyze Transaction**. The server supplies the actual
portable-model score, FRAUD/NOT_FRAUD classification and financial-only 0.30
threshold. No event is saved and no payment/fusion action is performed. PaySim
units are preserved and step is a simulation step, not a date.

Video Deepfake:

1. Choose a consented/synthetic MP4 or WebM within the displayed limits.
2. Draw a box around the largest face. Drag the box to move it or its corners to
   resize. The crop preview immediately includes the existing 25% padding.
3. Choose **Apply to all frames** to reuse that region and confirm five crops.
   Each frame is decoded/cropped separately; this does not copy one image five
   times and does not call the model yet.
4. Review frame buttons. If the face moves, adjust that frame and click
   **Confirm this frame**. Editing changes its badge to Needs crop. The live
   count, for example **3 of 5 frames ready**, controls Analyze availability.
5. Click **Analyze video**. The existing asynchronous LinuxONE model job supplies
   the mean sampled-frame Deepfake score and frame count, with progress/status,
   model identity and research limitations. No REAL/FAKE threshold is applied.

The editor is manual, not automatic detection/tracking. Touch Pointer Events are
supported where available. Keyboard: focus the frame canvas; arrows move the
box, Shift+arrows resize. **Advanced · enter percentages** retains explicit
coordinates. Clear stops browser preparation/waiting and releases its media;
already submitted server jobs finish independently and expire normally.

The video score is uncalibrated and is not a real-world fraud probability. This
is frame-based image analysis, not a temporal video model. The financial score
and 0–100 fusion risk index remain separate. No measured accuracy or real-world
protection is asserted by the redesign.

## Validation and manual release

No target deployment or restart is performed by development tests. Local browser
validation uses preinstalled Chromium and Playwright; no frontend framework,
Node.js, remote font, CDN, or new native serving dependency is required.

```sh
PYTHONPATH=src python3.12 -m unittest discover -s tests -v
PYTHONPATH=src:tests python3.12 tests/browser_smoke.py
PYTHONPATH=src:tests python3.12 tests/browser_video.py
PYTHONPATH=src:tests python3.12 tests/browser_selection.py
```

The financial browser suite covers actual portable financial predictions,
validation/errors/retries, synthetic fusion scenarios, histories and cooling-off.
The video suite covers native WebM/H.264/rotated-MP4 decoding, bounds, lifecycle,
local diagnostics and jobs. The selection suite covers draw/move/resize, bounds,
native touch/cancel, keyboard/advanced controls, apply-all, individual adjustment,
confirmation invalidation, separately captured frames, no request on preparation,
real HTTP submission to a test worker, navigation during jobs, cancellation and
recovery, CSP, and 1440/1280/390-pixel layouts. Video test scores come from a
clearly isolated test worker; actual model inference is not run on this host.

The user reports the existing detectors are working on LinuxONE. Serving paths
and model code are unchanged by this UI task. After reviewing a release, manually
verify the target browser/device, actual video model and financial samples,
bulk crop cancellation, inference during detector switching, and target memory
limits before presenting. Follow [VideoGuard acceptance](VIDEOGUARD.md) for
image parity and provenance checks. No new parity or accuracy claim is made.
