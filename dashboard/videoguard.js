"use strict";
// No inference here: browser decoding, manual crops, and same-origin job transport only.
(() => {
  const $ = id => document.getElementById(id);
  let video = $("video-preview");
  const picker = $("video-file"), selector = $("video-frame");
  const canvas = $("crop-preview"), context = canvas.getContext("2d");
  const names = ["x", "y", "w", "h"];
  let generation = 0, url = null, frames = [], index = 0, busy = false, loading = false;
  const faceCanvas = $("face-frame"), faceContext = faceCanvas.getContext("2d");
  let batching = false, drag = null;
  let controller = new AbortController();
  let diagnostics = null;
  function record(event, media = video) {
    if (!diagnostics) return;
    diagnostics.events.push({event, elapsedMs:Math.round(performance.now()-diagnostics.started),
      width:media.videoWidth, height:media.videoHeight,
      duration:Number.isFinite(media.duration)?media.duration:null,
      readyState:media.readyState, networkState:media.networkState, connected:media.isConnected,
      sourceAssigned:media.hasAttribute("src"), sourceMatches:!!url && media.getAttribute("src")===url,
      currentSourceMatches:!!url && media.currentSrc===url,
      urlState:diagnostics.urlState, cancelled:controller.signal.aborted,
      mediaErrorCode:media.error?.code || null});
    diagnostics.events = diagnostics.events.slice(-30);
    $("video-diagnostics").textContent = JSON.stringify(diagnostics,null,2);
  }
  function failure(code, message) {
    if (diagnostics?.urlState === "revoked") code = "URL_REVOKED_BY_APPLICATION";
    else if (url && video.getAttribute("src") !== url) code = "SOURCE_LOST";
    const err = new Error(message); err.code=code; return err;
  }
  const status = text => { $("video-status").textContent = text; };
  const error = err => {
    $("video-error").hidden = false; $("video-error").textContent = err.message;
    if (diagnostics) { diagnostics.failureCode=err.code || "INPUT_OR_ANALYSIS_ERROR"; diagnostics.message=err.message; record("failure-before-cleanup"); }
  };
  function controls() {
    const disabled = loading || busy || batching || !frames.length;
    selector.disabled = disabled;
    $("video-crop").disabled = disabled;
    faceCanvas.setAttribute("aria-disabled", String(disabled));
    $("video-analyze").disabled = disabled || frames.some(f => !f.image);
    $("video-analyze").textContent = busy ? "Analyzing video…" : "Analyze video";
    $("video-assessment").setAttribute("aria-busy",String(busy));
    $("video-ready").textContent = `${frames.filter(f => f.image).length} of ${frames.length || 5} frames ready`;
    $("video-confirm").textContent = frames[index]?.image ? "✓ Frame confirmed" : "Confirm this frame";
    $("video-apply-all").textContent = batching ? "Preparing five crops…" : "Apply to all frames";
    for (const button of $("video-frames").children) {
      const i=Number(button.dataset.frame), ready=!!frames[i]?.image;
      button.disabled=disabled; button.dataset.ready=String(ready);
      button.setAttribute("aria-pressed", String(i===index));
      button.lastChild.textContent=ready ? "✓ Ready" : "Needs crop";
      selector.options[i].textContent=`Frame ${i+1} · ${frames[i].timestamp.toFixed(2)}s${ready ? " · ✓ Ready" : ""}`;
    }
  }
  function reset(reason = "cleared-or-replaced") {
    record(`cleanup:${reason}`);
    generation++; controller.abort(); controller = new AbortController();
    // A fresh element isolates queued media events from the previous source.
    // Abort listeners first, detach the old source, then revoke its object URL.
    const previous = video;
    previous.pause(); previous.removeAttribute("src"); previous.load();
    video = previous.cloneNode(false);
    video.preload = "auto";
    previous.replaceWith(video);
    if (url) {
      URL.revokeObjectURL(url);
      if (diagnostics) diagnostics.urlState = "revoked";
    }
    record(`released:${reason}`, previous);
    url = null; frames = []; selector.replaceChildren(); $("video-frames").replaceChildren();
    busy = loading = batching = false; drag = null;
    faceContext.clearRect(0,0,faceCanvas.width,faceCanvas.height);
    $("frame-placeholder").hidden = false;
    context.clearRect(0, 0, canvas.width, canvas.height);
    $("video-result").hidden = true; $("video-empty").hidden = false; $("video-error").hidden = true; $("video-error").textContent = "";
    controls(); status("Select a video to begin. Submitted jobs finish independently and expire automatically.");
  }
  function waitEvent(name, action, signal, ready = () => true) {
    // Capture this source's element: cancellation must not clean up a replacement.
    const media = video;
    return new Promise((resolve, reject) => {
      const clean = () => { clearTimeout(timer); media.removeEventListener(name, ok); media.removeEventListener("error", fail); signal.removeEventListener("abort", abort); };
      const ok = () => { if (!ready()) return; clean(); resolve(); };
      const fail = () => { clean(); reject(failure(`MEDIA_ERROR_${media.error?.code || "UNKNOWN"}`,
        `Video decoding failed (media error ${media.error?.code || "unknown"}). Try a browser-supported MP4/H.264 or WebM file.`)); };
      const abort = () => { clean(); record(`cancelled:${name}`, media); reject(new DOMException("Cancelled", "AbortError")); };
      const timer = setTimeout(() => { clean(); reject(failure(name === "loadedmetadata" ? "METADATA_TIMEOUT" : "FRAME_TIMEOUT", `Video ${name === "loadedmetadata" ? "metadata loading" : "frame decoding"} timed out.`)); }, 10000);
      media.addEventListener(name, ok); media.addEventListener("error", fail, {once: true});
      signal.addEventListener("abort", abort, {once: true});
      if (signal.aborted) { abort(); return; }
      try { action(); } catch (err) { clean(); reject(err); }
    });
  }
  async function waitForPixels(signal) {
    const media = video;
    if (media.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && !media.seeking) return;
    await waitEvent("loadeddata", () => {}, signal,
      () => media.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && !media.seeking);
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
    renderSelection(values);
  }
  async function selectFrame() {
    const token = generation, signal = controller.signal;
    loading = true; controls();
    try {
      const frame = frames[index];
      if (Math.abs(video.currentTime - frame.timestamp) > .0001) await waitEvent("seeked", () => { video.currentTime = frame.timestamp; }, signal,
        () => !video.seeking);
      await waitForPixels(signal);
      if (token !== generation) return;
      names.forEach((n,i) => { $("crop-"+n).value = frame.crop[i]; });
      loading = false; crop();
      status(`Frame ${index+1}/${frames.length}, ${frame.timestamp.toFixed(2)}s. Inspect and confirm its manual face crop.`);
    } finally { if (token === generation) { loading = false; controls(); } }
  }
  picker.addEventListener("change", async () => {
    const file = picker.files[0]; reset(); if (!file) return;
    const token = generation, signal = controller.signal;
    diagnostics={loaderVersion:"orientation-diagnostics-v1", started:performance.now(), fileBytes:file.size, fileType:file.type,
      urlState:"not-created", events:[], containerInfo:{note:"Inspection pending"}};
    record("selected");
    loading = true; controls();
    try {
      if (file.size > 50*1024*1024 || file.size === 0) throw new Error("Choose a nonempty video up to 50 MiB.");
      if (!["video/mp4", "video/webm"].includes(file.type) || !video.canPlayType(file.type)) throw new Error("Choose a browser-supported MP4 or WebM video.");
      // Advisory inspection uses local File slices, not fetch(blobURL).
      window.VideoGuardMedia.inspect(file).then(info => {
        if (token === generation) { diagnostics.containerInfo=info; record("container-inspected"); }
      }).catch(() => {});
      url = URL.createObjectURL(file);
      diagnostics.urlState="active";
      for (const name of ["loadstart", "loadedmetadata", "loadeddata", "resize", "emptied", "abort", "stalled", "suspend", "error", "seeked"]) {
        video.addEventListener(name, () => record(`media:${name}`), {signal});
      }
      record("url-created");
      status("Loading video metadata…");
      const media = video, source = url;
      await waitEvent("loadedmetadata", () => { media.src = source; media.load(); }, signal,
        () => media.currentSrc === source && media.readyState >= HTMLMediaElement.HAVE_METADATA);
      // Dimensions/duration are meaningful only after this source's metadata.
      // Pixel readiness is checked separately before the first canvas draw.
      if (token !== generation) return;
      if (!Number.isFinite(video.duration) || video.duration <= 0 || video.duration > 60) throw new Error("Video must have a finite duration within 60 seconds.");
      await waitForPixels(signal);
      if (token !== generation) return;
      const width=video.videoWidth, height=video.videoHeight;
      diagnostics.decoded={width,height,duration:video.duration};
      record("dimensions-checked");
      if (!width || !height) throw failure("NO_VIDEO_DIMENSIONS", "Decoded media reports 0×0 video dimensions. The file may have no supported video track; inspect local diagnostics.");
      if (Math.min(width,height) < 32 || Math.min(width,height) > 1080 || Math.max(width,height) > 1920) {
        throw failure("DIMENSION_LIMIT", `Video reports ${width}×${height}. Limits: short side 32–1080, long side ≤1920, either orientation.`);
      }
      const count = 5;
      frames = Array.from({length: count}, (_,i) => ({timestamp: (video.duration * .999) * i/(count-1), crop: [25,15,50,70], image: null}));
      frames.forEach((f,i) => {
        const option = document.createElement("option"); option.value = i;
        option.textContent = `Frame ${i+1} · ${f.timestamp.toFixed(2)}s`; selector.append(option);
        const button=document.createElement("button"); button.type="button"; button.dataset.frame=String(i);
        const title=document.createElement("span"); title.textContent=`Frame ${i+1}`;
        const state=document.createElement("small"); state.textContent="Needs crop";
        button.append(title,state);
        button.addEventListener("click", () => { selector.value=String(i); selector.dispatchEvent(new Event("change")); });
        $("video-frames").append(button);
      });
      index = 0; await selectFrame();
    } catch (err) {
      if (token === generation) {
        // Keep the failed element/source for inspection. Revoke only on explicit
        // clear/replacement/page exit; resetting here previously erased evidence.
        loading=busy=batching=false; frames=[]; selector.replaceChildren(); $("video-frames").replaceChildren(); controls();
        error(err); status("Video loading failed. Inspect local diagnostics, then clear or choose another file.");
      }
    }
  });
  selector.addEventListener("change", async () => {
    const token = generation;
    index = Number(selector.value);
    try { await selectFrame(); }
    catch (err) { if (token === generation && err.name !== "AbortError") error(err); }
  });
  names.forEach(n => $("crop-"+n).addEventListener("input", () => {
    if (!frames.length) return;
    frames[index].image = null; controls(); $("video-result").hidden = true; $("video-empty").hidden=false;
    try { crop(); $("video-error").hidden = true; } catch (err) { context.clearRect(0,0,canvas.width,canvas.height); error(err); }
  }));
  function encodeCrop() {
    crop();
    const data = canvas.toDataURL("image/jpeg", .9).split(",")[1];
    if (!data || data.length > 4*Math.ceil(256*1024/3)) throw new Error("Crop image exceeds 256 KiB; choose a smaller region.");
    return data;
  }
  $("video-confirm").addEventListener("click", () => {
    if (loading || busy || batching || !frames.length) return;
    try {
      frames[index].image = encodeCrop();
      status(`${frames.filter(f => f.image).length}/${frames.length} manual crops confirmed. Select the next frame or analyze when all are confirmed.`);
      $("video-error").hidden = true; controls();
    } catch (err) { error(err); }
  });
  // Canvas uses intrinsic video pixels; pointer coordinates map its displayed
  // rectangle back to percentages. No letterboxed native-video coordinates.
  function renderSelection(values) {
    if (!video.videoWidth || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return;
    faceCanvas.width=video.videoWidth; faceCanvas.height=video.videoHeight;
    faceContext.drawImage(video,0,0);
    $("frame-placeholder").hidden=true;
    const [x,y,w,h]=values.map((n,i)=>n*(i%2===0?faceCanvas.width:faceCanvas.height)/100);
    const scale=faceCanvas.width/(faceCanvas.getBoundingClientRect().width || faceCanvas.width);
    const pad=Math.floor(.25*Math.max(Math.floor(w),Math.floor(h)));
    faceContext.strokeStyle="#dce9fa"; faceContext.lineWidth=1.5*scale;
    faceContext.setLineDash([5*scale,4*scale]);
    faceContext.strokeRect(Math.max(0,x-pad),Math.max(0,y-pad),
      Math.min(faceCanvas.width,x+w+pad)-Math.max(0,x-pad),
      Math.min(faceCanvas.height,y+h+pad)-Math.max(0,y-pad));
    faceContext.setLineDash([]); faceContext.strokeStyle="#76ffce"; faceContext.lineWidth=2.5*scale;
    faceContext.fillStyle="#76ffce20"; faceContext.fillRect(x,y,w,h); faceContext.strokeRect(x,y,w,h);
    faceContext.fillStyle="#d9fff2";
    for (const [cx,cy] of [[x,y],[x+w,y],[x,y+h],[x+w,y+h]]) faceContext.fillRect(cx-5*scale,cy-5*scale,10*scale,10*scale);
  }
  const clamp=(n,min,max)=>Math.max(min,Math.min(max,n));
  function pointerPoint(event) {
    const rect=faceCanvas.getBoundingClientRect();
    return {x:clamp(100*(event.clientX-rect.left)/rect.width,0,100), y:clamp(100*(event.clientY-rect.top)/rect.height,0,100)};
  }
  function setRegion(values) {
    const minW=Math.min(100,3300/video.videoWidth), minH=Math.min(100,3300/video.videoHeight);
    let [x,y,w,h]=values;
    w=clamp(w,minW,100); h=clamp(h,minH,100); x=clamp(x,0,100-w); y=clamp(y,0,100-h);
    names.forEach((n,i)=>{ $("crop-"+n).value=String([x,y,w,h][i]); });
    frames[index].image=null; $("video-result").hidden=true; $("video-empty").hidden=false;
    crop(); controls(); $("video-error").hidden=true;
  }
  function editable() { return frames.length && !loading && !busy && !batching; }
  faceCanvas.addEventListener("pointerdown", event => {
    if (!editable() || (event.pointerType==="mouse" && event.button!==0) || drag) return;
    event.preventDefault(); faceCanvas.focus({preventScroll:true});
    const point=pointerPoint(event), original=[...frames[index].crop], [x,y,w,h]=original;
    const rect=faceCanvas.getBoundingClientRect(), hx=1200/rect.width, hy=1200/rect.height;
    let mode="draw";
    for (const [name,cx,cy] of [["nw",x,y],["ne",x+w,y],["sw",x,y+h],["se",x+w,y+h]]) {
      if (Math.abs(point.x-cx)<=hx && Math.abs(point.y-cy)<=hy) { mode=name; break; }
    }
    if (mode==="draw" && point.x>x && point.x<x+w && point.y>y && point.y<y+h) mode="move";
    drag={point, original, image:frames[index].image, mode, id:event.pointerId, token:generation};
    faceCanvas.setPointerCapture(event.pointerId);
  });
  faceCanvas.addEventListener("pointermove", event => {
    if (!drag || drag.id!==event.pointerId || drag.token!==generation || !editable()) return;
    const point=pointerPoint(event), [x,y,w,h]=drag.original;
    const minW=Math.min(100,3300/video.videoWidth), minH=Math.min(100,3300/video.videoHeight);
    let left=x, top=y, width=w, height=h;
    if (drag.mode==="move") { left=x+point.x-drag.point.x; top=y+point.y-drag.point.y; }
    else if (drag.mode==="draw") { left=Math.min(point.x,drag.point.x); top=Math.min(point.y,drag.point.y); width=Math.abs(point.x-drag.point.x); height=Math.abs(point.y-drag.point.y); }
    else {
      if (drag.mode.includes("w")) { left=clamp(point.x,0,x+w-minW); width=x+w-left; }
      if (drag.mode.includes("e")) width=clamp(point.x-x,minW,100-x);
      if (drag.mode.includes("n")) { top=clamp(point.y,0,y+h-minH); height=y+h-top; }
      if (drag.mode.includes("s")) height=clamp(point.y-y,minH,100-y);
    }
    try { setRegion([left,top,width,height]); }
    catch (err) { error(err); }
  });
  function finishDrag(event) {
    if (!drag || event.pointerId!==drag.id) return;
    const previous=drag; drag=null;
    if (previous.token===generation && frames[index]) {
      if (event.type==="pointercancel") {
        names.forEach((n,i)=>{ $("crop-"+n).value=previous.original[i]; });
        frames[index].image=previous.image; crop(); controls();
      } else status("Face region updated. Confirm this frame or apply the region to all five.");
    }
    if (faceCanvas.hasPointerCapture(event.pointerId)) faceCanvas.releasePointerCapture(event.pointerId);
  }
  faceCanvas.addEventListener("pointerup",finishDrag);
  faceCanvas.addEventListener("pointercancel",finishDrag);
  faceCanvas.addEventListener("lostpointercapture",event=>{ if(drag) finishDrag({...event,pointerId:event.pointerId,type:"pointercancel"}); });
  faceCanvas.addEventListener("keydown", event => {
    if (!editable() || !["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key)) return;
    event.preventDefault(); const values=[...frames[index].crop];
    const horizontal=event.key==="ArrowLeft"||event.key==="ArrowRight";
    const delta=event.key==="ArrowLeft"||event.key==="ArrowUp"?-1:1;
    const at=event.shiftKey?(horizontal?2:3):(horizontal?0:1);
    values[at]+=delta;
    if(event.shiftKey) values[at]=Math.min(values[at],100-values[horizontal?0:1]);
    try { setRegion(values); } catch(err) { error(err); }
  });
  $("video-apply-all").addEventListener("click", async () => {
    if (!editable()) return;
    const token=generation, originalIndex=index;
    try {
      crop(); const region=[...frames[index].crop];
      batching=true; controls(); $("video-result").hidden=true; $("video-empty").hidden=false;
      frames.forEach(frame=>{ frame.crop=[...region]; frame.image=null; });
      for (let i=0;i<frames.length;i++) {
        if(token!==generation) return;
        index=i; selector.value=String(i);
        status(`Preparing frame ${i+1} of ${frames.length}…`);
        await selectFrame();
        if(token!==generation) return;
        frames[index].image=encodeCrop(); controls();
      }
      index=originalIndex; selector.value=String(index); await selectFrame();
      if(token===generation) status("All five crops ready. Review or adjust any frame, then Analyze video.");
    } catch(err) { if(token===generation && err.name!=="AbortError") error(err); }
    finally { if(token===generation) { batching=false; controls(); } }
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
    busy = true; controls(); $("video-result").hidden = true; $("video-empty").hidden = false; $("video-error").hidden = true;
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
          $("video-result").hidden = false; $("video-empty").hidden = true;
          $("video-meter").setAttribute("aria-valuetext",`${result.mean_deepfake_score}, uncalibrated mean sampled-frame score`);
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      throw new Error("Stopped waiting for analysis. Retry later; no score was substituted.");
    } catch (err) { if (token === generation) error(err); }
    finally { if (token === generation) { busy = false; controls(); } }
  });
  $("video-reset").addEventListener("click", () => { reset(); picker.value = ""; });
  window.addEventListener("pagehide", () => reset("page-exit"));
})();
