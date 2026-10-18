"""Bounded, ephemeral frame analysis. No video codecs or fusion side effects."""

import base64
import binascii
import io
import math
import multiprocessing as mp
import os
import queue
import secrets
import threading
import time
import warnings

from .models import CapacityError, ValidationError

MODEL_ID = "prithivMLmods/Deep-Fake-Detector-v2-Model"
MODEL_PATH = "/home/ibm-user/VideoGuard/model"
MAX_BODY = 3 * 1024 * 1024
MAX_FRAMES = 8
MAX_IMAGE = 256 * 1024
TTL = 300
WARNING = ("Experimental, uncalibrated sampled-frame score; not a real-world probability. "
           "Frame-based analysis, not a temporal video model. Manual crop; no automatic face detection. "
           "Manual face boxes differ from Haar detection; end-to-end Kaggle parity is unverified. Advisory only; no payment or fusion action.")


def validate(value: object) -> dict:
    """Validate untrusted metadata and bounded image bytes before queuing."""
    if not isinstance(value, dict) or set(value) != {"duration", "frames"}:
        raise ValidationError("video request requires duration and frames only")
    duration = value["duration"]
    if type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= 60:
        raise ValidationError("duration must be finite and within 60 seconds")
    frames = value["frames"]
    if not isinstance(frames, list) or not 1 <= len(frames) <= MAX_FRAMES:
        raise ValidationError("submit 1–8 manually cropped frames")
    checked, previous = [], -1
    for frame in frames:
        if not isinstance(frame, dict) or set(frame) != {"timestamp", "image"}:
            raise ValidationError("each frame requires timestamp and base64 JPEG image")
        stamp, encoded = frame["timestamp"], frame["image"]
        if (type(stamp) not in (int, float) or not math.isfinite(stamp)
                or not previous < stamp < duration):
            raise ValidationError("frame timestamps must increase within video duration")
        if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_IMAGE + 2) // 3):
            raise ValidationError("frame exceeds 256 KiB")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValidationError("invalid base64 image") from exc
        if len(raw) > MAX_IMAGE or not raw.startswith(b'\xff\xd8\xff'):
            raise ValidationError("only bounded JPEG frames are accepted")
        checked.append((stamp, raw))
        previous = stamp
    return {"frames": checked}


def decode_image(raw):
    """Decode only JPEG, checking headers before allocating full pixel buffers."""
    from PIL import Image
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(raw), formats=["JPEG"]) as image:
            if image.format != "JPEG" or not (32 <= image.width <= 1920 and 32 <= image.height <= 1080):
                raise ValueError("JPEG dimensions must be within 32×32 and 1920×1080")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("animated images are unsupported")
            image.load()
            return image.convert("RGB")


def model_worker(incoming, outgoing, model_path):
    """Persistent spawned CPU worker; imports stay outside financial serving path."""
    os.environ["OMP_NUM_THREADS"] = "2"
    os.environ["MKL_NUM_THREADS"] = "2"
    processor = model = torch = None
    while True:
        payload = incoming.get()
        if payload is None:
            return
        images = []
        try:
            images = [decode_image(raw) for _, raw in payload["frames"]]
            if model is None:
                import torch
                from transformers import AutoImageProcessor, AutoModelForImageClassification
                torch.set_num_threads(2)
                processor = AutoImageProcessor.from_pretrained(model_path, local_files_only=True,
                                                                trust_remote_code=False)
                model = AutoModelForImageClassification.from_pretrained(
                    model_path, local_files_only=True, trust_remote_code=False,
                    use_safetensors=True).cpu().eval()
                labels = {int(k): v for k, v in model.config.id2label.items()}
                if labels != {0: "Realism", 1: "Deepfake"} or model.config.num_labels != 2:
                    raise ValueError("unexpected class labels")
            scores = []
            for image in images:
                inputs = processor(images=image, return_tensors="pt")
                with torch.inference_mode():
                    logits = model(**inputs).logits
                    if tuple(logits.shape) != (1, 2):
                        raise ValueError("unexpected logits")
                    score = float(torch.softmax(logits, dim=-1)[0, 1].item())
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("invalid model score")
                scores.append(score)
            outgoing.put({"scores": scores})
        except Exception:
            # Do not return filesystem paths, media data, or model internals.
            outgoing.put({"error": "Frame decoding or local model inference failed. Check deployment and image format."})
            return  # fail closed; supervisor replaces worker on the next job
        finally:
            for image in images:
                image.close()


class VideoJobs:
    """One active job, one queued job, bounded results and 5-minute retention."""

    def __init__(self, model_path=MODEL_PATH, *, worker=model_worker, timeout=180, ttl=TTL):
        self.model_path, self.worker, self.timeout, self.ttl = model_path, worker, timeout, ttl
        self.jobs, self.pending = {}, queue.Queue(maxsize=2)
        self.lock, self.stop = threading.Lock(), threading.Event()
        self.process = self.incoming = self.outgoing = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _expire(self):
        now = time.monotonic()
        for key in list(self.jobs):
            if (self.jobs[key]["status"] in {"complete", "failed"}
                    and now - self.jobs[key]["created"] > self.ttl):
                del self.jobs[key]

    def submit(self, value):
        with self.lock:
            self._expire()
            if self.stop.is_set() or sum(j["status"] in {"queued", "processing"} for j in self.jobs.values()) >= 2:
                raise CapacityError("VideoGuard busy; retry after current jobs finish")
            if len(self.jobs) >= 16:
                raise CapacityError("VideoGuard result capacity reached; retry after expiry")
            payload = validate(value)
            job_id = secrets.token_urlsafe(24)
            self.jobs[job_id] = {"created": time.monotonic(), "status": "queued"}
            self.pending.put_nowait((job_id, payload))
            return {"job_id": job_id, "status": "queued"}

    def get(self, job_id):
        with self.lock:
            self._expire()
            job = self.jobs.get(job_id)
            return {k: v for k, v in job.items() if k != "created"} if job else None

    def _reset(self):
        if self.process:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=2)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=2)
            self.process.close()
        for channel in (self.incoming, self.outgoing):
            if channel:
                channel.cancel_join_thread()
                channel.close()
        self.process = self.incoming = self.outgoing = None

    def _infer(self, payload):
        if self.process is None:
            ctx = mp.get_context("spawn")
            self.incoming, self.outgoing = ctx.Queue(1), ctx.Queue(1)
            self.process = ctx.Process(target=self.worker,
                                       args=(self.incoming, self.outgoing, self.model_path), daemon=True)
            self.process.start()
        self.incoming.put(payload, timeout=1)
        deadline = time.monotonic() + self.timeout
        while not self.stop.is_set() and time.monotonic() < deadline:
            try:
                result = self.outgoing.get(timeout=.1)
                if "error" in result:
                    self._reset()
                    raise ValueError(result["error"])
                scores = result["scores"]
                if (len(scores) != len(payload["frames"]) or
                        any(type(s) not in (int, float) or not math.isfinite(s) or not 0 <= s <= 1 for s in scores)):
                    raise ValueError("invalid inference result")
                return scores
            except queue.Empty:
                if not self.process.is_alive():
                    break
        self._reset()
        raise ValueError("Video inference timed out or worker exited; retry later")

    def _run(self):
        while not self.stop.is_set():
            try:
                job_id, payload = self.pending.get(timeout=.2)
            except queue.Empty:
                with self.lock:
                    self._expire()
                continue
            with self.lock:
                if job_id not in self.jobs:
                    continue
                self.jobs[job_id]["status"] = "processing"
            try:
                scores = self._infer(payload)
                result = {"status": "complete", "mean_deepfake_score": sum(scores) / len(scores),
                          "frames_analyzed": len(scores), "model": MODEL_ID, "labels": {0: "Realism", 1: "Deepfake"},
                          "warning": WARNING, "advisory_only": True, "persisted": False,
                          "frames": [{"timestamp": stamp, "score": score}
                                     for (stamp, _), score in zip(payload["frames"], scores)]}
            except Exception:
                self._reset()
                result = {"status": "failed", "error": "Video inference unavailable. Check local model, JPEG support, labels and worker timeout."}
            finally:
                payload = None
            with self.lock:
                if job_id in self.jobs:
                    self.jobs[job_id].update(result)
                    self.jobs[job_id]["created"] = time.monotonic()
        self._reset()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=self.timeout + 3)
        with self.lock:
            self.jobs.clear()
        while not self.pending.empty():
            try:
                self.pending.get_nowait()
            except queue.Empty:
                break
