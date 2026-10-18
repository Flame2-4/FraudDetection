"use strict";
// No inference here: browser decoding, manual crops, and same-origin job transport only.
(() => {
  const $ = id => document.getElementById(id);
  const video = $("video-preview"), picker = $("video-file"), selector = $("video-frame");
  const canvas = $("crop-preview"), context = canvas.getContext("2d");
  const names = ["x", "y", "w", "h"];
  let generation = 0, url = null, frames = [], index = 0, busy = false, loading = false;
  let controller = new AbortController();
  const status = text => { $("video-status").textContent = text; };
  const error = err => { $("video-error").hidden = false; $("video-error").textContent = err.message; };
  function controls() {
    selector.disabled = loading || busy || !frames.length;
    $("video-crop").disabled = loading || busy || !frames.length;
    $("video-analyze").disabled = loading || busy || !frames.length || frames.some(f => !f.image);
  }
  function reset() {
    generation++; controller.abort(); controller = new AbortController();
    video.pause(); video.removeAttribute("src"); video.load();
    if (url) URL.revokeObjectURL(url);
    url = null; frames = []; selector.replaceChildren(); busy = loading = false;
    context.clearRect(0, 0, canvas.width, canvas.height);
    $("video-result").hidden = true; $("video-error").hidden = true;
    controls(); status("Select a video to begin. Submitted jobs finish independently and expire automatically.");
  }
  function waitEvent(name, action, signal) {
    return new Promise((resolve, reject) => {
      const clean = () => { clearTimeout(timer); video.removeEventListener(name, ok); video.removeEventListener("error", fail); signal.removeEventListener("abort", abort); };
      const ok = () => { clean(); resolve(); };
      const fail = () => { clean(); reject(new Error("Video decoding failed. Try a browser-supported MP4/H.264 or WebM file.")); };
      const abort = () => { clean(); reject(new DOMException("Cancelled", "AbortError")); };
      const timer = setTimeout(() => { clean(); reject(new Error("Video frame decoding timed out.")); }, 10000);
      video.addEventListener(name, ok, {once: true}); video.addEventListener("error", fail, {once: true});
      signal.addEventListener("abort", abort, {once: true});
      if (signal.aborted) { abort(); return; }
      action();
    });
  }
  function crop() {
    if (!frames.length || loading || busy) return;
    const values = names.map(n => $("crop-" + n).valueAsNumber);
    const [x,y,w,h] = values;
    if (values.some(v => !Number.isFinite(v)) || x < 0 || y < 0 || w <= 0 || h <= 0 || x+w > 100 || y+h > 100) throw new Error("Face region must fit inside the frame.");
    const width = video.videoWidth*w/100, height = video.videoHeight*h/100;
    if (width < 32 || height < 32) throw new Error("Face crop must be at least 32×32 source pixels.");
    const fx = Math.floor(video.videoWidth*x/100), fy = Math.floor(video.videoHeight*y/100);
    const fw = Math.floor(width), fh = Math.floor(height);
    const pad = Math.floor(.25*Math.max(fw,fh));
    const left = Math.max(0,fx-pad), top = Math.max(0,fy-pad);
    canvas.width = Math.min(video.videoWidth,fx+fw+pad)-left;
    canvas.height = Math.min(video.videoHeight,fy+fh+pad)-top;
    // Preserve native crop size. The server's actual model processor resizes/normalizes.
    context.drawImage(video, left, top, canvas.width, canvas.height, 0, 0, canvas.width, canvas.height);
    frames[index].crop = values;
  }
  async function selectFrame() {
    const token = generation, signal = controller.signal;
    loading = true; controls();
    try {
      const frame = frames[index];
      if (Math.abs(video.currentTime - frame.timestamp) > .0001) await waitEvent("seeked", () => { video.currentTime = frame.timestamp; }, signal);
      if (token !== generation) return;
      names.forEach((n,i) => { $("crop-"+n).value = frame.crop[i]; });
      loading = false; crop();
      status(`Frame ${index+1}/${frames.length}, ${frame.timestamp.toFixed(2)}s. Inspect and confirm its manual face crop.`);
    } finally { if (token === generation) { loading = false; controls(); } }
  }
  picker.addEventListener("change", async () => {
    const file = picker.files[0]; reset(); if (!file) return;
    const token = generation, signal = controller.signal;
    loading = true; controls();
    try {
      if (file.size > 50*1024*1024 || file.size === 0) throw new Error("Choose a nonempty video up to 50 MiB.");
      if (!["video/mp4", "video/webm"].includes(file.type) || !video.canPlayType(file.type)) throw new Error("Choose a browser-supported MP4 or WebM video.");
      url = URL.createObjectURL(file);
      await waitEvent("loadeddata", () => { video.src = url; video.load(); }, signal);
      if (token !== generation) return;
      if (!Number.isFinite(video.duration) || video.duration <= 0 || video.duration > 60) throw new Error("Video must have a finite duration within 60 seconds.");
      if (video.videoWidth > 1920 || video.videoHeight > 1080 || Math.min(video.videoWidth, video.videoHeight) < 32) throw new Error("Video dimensions must be within 1920×1080 and at least 32×32.");
      const count = 5;
      frames = Array.from({length: count}, (_,i) => ({timestamp: (video.duration * .999) * i/(count-1), crop: [25,15,50,70], image: null}));
      frames.forEach((f,i) => { const option = document.createElement("option"); option.value = i; option.textContent = `Frame ${i+1} · ${f.timestamp.toFixed(2)}s`; selector.append(option); });
      index = 0; await selectFrame();
    } catch (err) { if (token === generation) { reset(); error(err); } }
  });
  selector.addEventListener("change", async () => { index = Number(selector.value); try { await selectFrame(); } catch (err) { error(err); } });
  names.forEach(n => $("crop-"+n).addEventListener("input", () => {
    if (!frames.length) return;
    frames[index].image = null; controls(); $("video-result").hidden = true;
    try { crop(); $("video-error").hidden = true; } catch (err) { context.clearRect(0,0,canvas.width,canvas.height); error(err); }
  }));
  $("video-confirm").addEventListener("click", () => {
    try {
      crop(); const data = canvas.toDataURL("image/jpeg", .9).split(",")[1];
      if (!data || data.length > 4*Math.ceil(256*1024/3)) throw new Error("Crop image exceeds 256 KiB; choose a smaller region.");
      frames[index].image = data;
      status(`${frames.filter(f => f.image).length}/${frames.length} manual crops confirmed. Select the next frame or analyze when all are confirmed.`);
      $("video-error").hidden = true; controls();
    } catch (err) { error(err); }
  });
  async function api(path, options, signal) {
    const bounded = AbortSignal.any([signal, AbortSignal.timeout(10000)]);
    const response = await fetch(path, {...options, signal: bounded});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  }
  $("video-analyze").addEventListener("click", async () => {
    if (busy || frames.some(f => !f.image)) return;
    const token = generation, signal = controller.signal;
    busy = true; controls(); $("video-result").hidden = true; $("video-error").hidden = true;
    try {
      status("Submitting manually cropped frames…");
      const body = JSON.stringify({duration: video.duration, frames: frames.map(f => ({timestamp: f.timestamp, image: f.image}))});
      if (new TextEncoder().encode(body).length > 3*1024*1024) throw new Error("Frame request exceeds 3 MiB.");
      const job = await api("/api/video/jobs", {method: "POST", headers: {"Content-Type":"application/json"}, body}, signal);
      const deadline = Date.now()+390000;
      while (Date.now() < deadline) {
        const result = await api(`/api/video/jobs/${encodeURIComponent(job.job_id)}`, {}, signal);
        if (token !== generation) return;
        status(`VideoGuard: ${result.status}. Financial analysis remains available.`);
        if (result.status === "failed") throw new Error(result.error);
        if (result.status === "complete") {
          if (!Number.isFinite(result.mean_deepfake_score) || result.mean_deepfake_score < 0 || result.mean_deepfake_score > 1 || result.frames_analyzed !== frames.length) throw new Error("Invalid model response; no result displayed.");
          $("video-score").textContent = result.mean_deepfake_score.toPrecision(6);
          $("video-meter").value = result.mean_deepfake_score;
          $("video-count").textContent = `${result.frames_analyzed} frames analyzed. No video classification threshold applied.`;
          $("video-model").textContent = result.model;
          $("video-warning").textContent = result.warning;
          $("video-result").hidden = false; return;
        }
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      throw new Error("Stopped waiting for analysis. Retry later; no score was substituted.");
    } catch (err) { if (token === generation) error(err); }
    finally { if (token === generation) { busy = false; controls(); } }
  });
  $("video-reset").addEventListener("click", () => { reset(); picker.value = ""; });
  window.addEventListener("pagehide", reset);
})();
