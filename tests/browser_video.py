"""Chromium native WebM decode, manual padding, real HTTP jobs with a TEST worker.

No real model is installed on this test host. Test worker scores are never used
by the application in serving mode. Generate a synthetic moving canvas video.
"""
import base64
import json
import shutil
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from playwright.sync_api import sync_playwright, expect
from fraudguard.api import make_server
from fraudguard.engine import Engine
from fraudguard.video import VideoJobs
from test_video import fake_worker


def main():
    with TemporaryDirectory() as tmp:
        server = make_server(Engine(Path(tmp)/'test.db'), port=0,
                             video_jobs=VideoJobs(worker=fake_worker, timeout=10))
        thread = Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=shutil.which('chromium'), headless=True, args=['--no-sandbox'])
                page = browser.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}/#videoguard')
                make_video = '''async (options) => {
                  const canvas = document.createElement('canvas'); canvas.width=options.width; canvas.height=options.height;
                  const ctx = canvas.getContext('2d'); const stream = canvas.captureStream(10);
                  const recorder = new MediaRecorder(stream, {mimeType:options.mimeType}); const chunks=[];
                  recorder.ondataavailable=e=>chunks.push(e.data);
                  const result = new Promise(resolve => recorder.onstop=async()=>{
                    const bytes=new Uint8Array(await new Blob(chunks).arrayBuffer());
                    let raw=''; for (const b of bytes) raw+=String.fromCharCode(b); resolve(btoa(raw));
                  });
                  recorder.start();
                  for(let i=0;i<20;i++){ctx.fillStyle=i%2?'#347788':'#448899';ctx.fillRect(0,0,canvas.width,canvas.height); await new Promise(r=>setTimeout(r,100));}
                  recorder.stop(); stream.getTracks().forEach(t=>t.stop()); return result;
                }'''
                data = page.evaluate(make_video, {'width':320, 'height':240, 'mimeType':'video/webm'})
                mp4 = page.evaluate(make_video, {'width':1280, 'height':720, 'mimeType':'video/mp4;codecs=avc1'})
                page.locator('#video-file').set_input_files({'name':'synthetic.webm','mimeType':'video/webm','buffer':base64.b64decode(data)})
                expect(page.locator('#crop-x')).to_be_enabled(timeout=15000)
                # Original face box: 160x168, pad floor(.25*168)=42.
                page.wait_for_function("() => document.getElementById('crop-preview').width === 244")
                assert page.locator('#crop-preview').get_attribute('width') == '244'
                assert page.locator('#crop-preview').get_attribute('height') == '240'
                for i in range(5):
                    page.select_option('#video-frame', str(i))
                    expect(page.locator('#crop-x')).to_be_enabled()
                    page.click('#video-confirm')
                expect(page.locator('#video-analyze')).to_be_enabled()
                for _ in range(2):
                    page.click('#video-analyze')
                    expect(page.locator('#video-result')).to_be_visible(timeout=15000)
                    assert page.locator('#video-score').inner_text() == '0.200000'
                    assert '5 frames analyzed' in page.locator('#video-count').inner_text()
                page.click('#video-reset')
                expect(page.locator('#video-result')).to_be_hidden()
                page.locator('#video-file').set_input_files({'name':'synthetic_1280x720.mp4','mimeType':'video/mp4','buffer':base64.b64decode(mp4)})
                expect(page.locator('#crop-x')).to_be_enabled(timeout=15000)
                assert page.locator('#video-preview').evaluate('(v) => [v.videoWidth,v.videoHeight]') == [1280,720]
                expect(page.locator('#video-error')).to_be_hidden()
                # A coded 1280×720 MP4 with a 90-degree track matrix decodes as
                # 720×1280. This valid HD clip triggered the old dimension error.
                rotated = bytearray(base64.b64decode(mp4))
                tkhd = rotated.index(b'tkhd')
                matrix = tkhd+4+(52 if rotated[tkhd+4] == 1 else 40)
                for offset,value in ((0,0),(4,65536),(12,-65536),(16,0)):
                    struct.pack_into('>i',rotated,matrix+offset,value)
                page.locator('#video-file').set_input_files({'name':'rotated.mp4','mimeType':'video/mp4','buffer':bytes(rotated)})
                expect(page.locator('#crop-x')).to_be_enabled(timeout=15000)
                assert page.locator('#video-preview').evaluate('(v) => [v.videoWidth,v.videoHeight]') == [720,1280]
                page.wait_for_function("() => JSON.parse(document.getElementById('video-diagnostics').textContent).containerInfo.tracks?.length > 0")
                info = page.locator('#video-diagnostics').text_content()
                track = next(t for t in json.loads(info)['containerInfo']['tracks'] if t.get('handler') == 'vide')
                assert (track['codedWidth'],track['codedHeight']) == (1280,720)
                assert track['rotationDegrees'] == 90 and track['codec'] == 'avc1'
                assert json.loads(info)['urlState'] == 'active'
                assert json.loads(info)['decoded']['height'] == 1280
                assert json.loads(info)['loaderVersion'] == 'orientation-diagnostics-v1'
                for i in range(5):
                    page.select_option('#video-frame', str(i))
                    expect(page.locator('#crop-x')).to_be_enabled()
                    page.click('#video-confirm')
                page.click('#video-analyze')
                expect(page.locator('#video-result')).to_be_visible(timeout=15000)
                page.click('#video-reset')
                malformed = page.evaluate("async () => VideoGuardMedia.inspect(new File([new Uint8Array(12)], 'bad.mp4', {type:'video/mp4'}))")
                assert malformed['container'] == 'MP4' and 'note' in malformed
                # Regression: a stale loadeddata event must not validate zero dimensions.
                # Delay native source loading while injecting an early event/state. This
                # reproduces the old reused-element failure without external media/codecs.
                page.add_init_script("""(() => {
                  document.addEventListener('loadedmetadata', e => { if (window.suppressMetadata) e.stopImmediatePropagation(); }, true);
                  const width = Object.getOwnPropertyDescriptor(HTMLVideoElement.prototype, 'videoWidth');
                  Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', {
                    configurable:true, get() { return window.forceOversize && this.readyState >= 1 ? 2048 : width.get.call(this); }
                  });
                  const src = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
                  const duration = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'duration');
                  Object.defineProperty(HTMLMediaElement.prototype, 'duration', {
                    configurable: true, get() { return this.readyState === 0 ? 2 : duration.get.call(this); }
                  });
                  const time = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'currentTime');
                  Object.defineProperty(HTMLMediaElement.prototype, 'currentTime', {
                    configurable:true, get:time.get,
                    set(value) { if (!window.stallSeek) time.set.call(this,value); }
                  });
                  window.mediaAudit = {created:[], revoked:[], violations:[]};
                  const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
                  URL.createObjectURL = blob => { const value=create(blob); mediaAudit.created.push(value); return value; };
                  URL.revokeObjectURL = value => { mediaAudit.revoked.push(value); revoke(value); };
                  window.addEventListener('securitypolicyviolation', e => mediaAudit.violations.push(e.violatedDirective));
                  Object.defineProperty(HTMLMediaElement.prototype, 'src', {
                    configurable: true, get: src.get,
                    set(value) {
                      if (!String(value).startsWith('blob:')) return src.set.call(this,value);
                      if (window.stallMedia) return;
                      queueMicrotask(() => this.dispatchEvent(new Event('loadeddata')));
                      setTimeout(() => { if (this.isConnected) {src.set.call(this,value); this.load();} }, 500);
                    }
                  });
                })();""")
                response = page.reload()
                csp = response.headers['content-security-policy']
                assert "connect-src 'self';" in csp and "media-src 'self' blob:;" in csp
                sample = {'name':'delayed.webm','mimeType':'video/webm','buffer':base64.b64decode(data)}
                page.locator('#video-file').set_input_files(sample)
                expect(page.locator('#video-status')).to_have_text('Loading video metadata…')
                assert page.locator('#video-preview').evaluate('(v) => v.readyState') == 0
                assert page.locator('#video-preview').evaluate('(v) => v.videoWidth') == 0
                expect(page.locator('#video-error')).to_be_hidden()
                expect(page.locator('#crop-x')).to_be_disabled()
                assert page.evaluate('mediaAudit.revoked.length') == 0
                page.wait_for_function("() => document.getElementById('crop-preview').width === 244")
                expect(page.locator('#crop-x')).to_be_enabled()
                assert page.locator('#video-preview').evaluate('(v) => v.videoWidth') == 320
                assert page.evaluate('mediaAudit.revoked.length') == 0
                # Rapid replacement cancels the first source; clear cancels the second.
                page.locator('#video-file').set_input_files(sample)
                expect(page.locator('#video-status')).to_have_text('Loading video metadata…')
                page.locator('#video-file').set_input_files({**sample, 'name':'replacement.webm'})
                page.wait_for_function("() => document.getElementById('crop-preview').width === 244")
                expect(page.locator('#crop-x')).to_be_enabled()
                expect(page.locator('#video-error')).to_be_hidden()
                page.evaluate('window.stallSeek = true')
                page.select_option('#video-frame', '1')
                expect(page.locator('#crop-x')).to_be_disabled()
                page.click('#video-reset')
                page.wait_for_timeout(50)
                expect(page.locator('#video-error')).to_be_hidden()
                page.evaluate('window.stallSeek = false')
                page.locator('#video-file').set_input_files(sample)
                page.click('#video-reset')
                page.wait_for_timeout(600)  # Allow delayed old-source callbacks to fire.
                expect(page.locator('#crop-x')).to_be_disabled()
                expect(page.locator('#video-error')).to_be_hidden()
                assert page.evaluate('mediaAudit.created.length === mediaAudit.revoked.length')
                assert not page.evaluate('mediaAudit.violations')
                # A source that never emits metadata must fail within the 10s bound.
                page.evaluate('window.forceOversize = true')
                page.locator('#video-file').set_input_files(sample)
                expect(page.locator('#video-error')).to_contain_text('Video reports 2048×240.', timeout=15000)
                diagnostic = json.loads(page.locator('#video-diagnostics').text_content())
                assert diagnostic['failureCode'] == 'DIMENSION_LIMIT'
                assert diagnostic['urlState'] == 'active'
                assert page.locator('#video-preview').evaluate('(v) => v.videoWidth') == 2048
                assert diagnostic['events'][-1]['sourceAssigned']
                page.click('#video-reset')
                assert json.loads(page.locator('#video-diagnostics').text_content())['urlState'] == 'revoked'
                page.evaluate('window.forceOversize = false; window.stallMedia = true')
                page.locator('#video-file').set_input_files(sample)
                expect(page.locator('#video-error')).to_be_visible(timeout=12000)
                expect(page.locator('#video-error')).to_have_text('Video metadata loading timed out.', timeout=12000)
                expect(page.locator('#crop-x')).to_be_disabled()
                diagnostic = json.loads(page.locator('#video-diagnostics').text_content())
                assert diagnostic['failureCode'] == 'SOURCE_LOST'
                assert diagnostic['urlState'] == 'active'  # not revoked by error cleanup
                page.click('#video-reset')
                assert page.evaluate('mediaAudit.created.length === mediaAudit.revoked.length')
                page.evaluate('window.stallMedia = false; window.suppressMetadata = true')
                page.locator('#video-file').set_input_files(sample)
                expect(page.locator('#video-error')).to_be_visible(timeout=12000)
                expect(page.locator('#video-error')).to_have_text('Video metadata loading timed out.', timeout=12000)
                diagnostic = json.loads(page.locator('#video-diagnostics').text_content())
                assert diagnostic['failureCode'] == 'METADATA_TIMEOUT'
                assert diagnostic['events'][-1]['sourceMatches']
                assert diagnostic['urlState'] == 'active'
                page.click('#video-reset')
                page.evaluate('window.suppressMetadata = false')

                page.locator('#video-file').set_input_files({'name':'bad.mp4','mimeType':'video/mp4','buffer':b'not a video'})
                expect(page.locator('#video-error')).to_be_visible()
                diagnostic = json.loads(page.locator('#video-diagnostics').text_content())
                assert diagnostic['failureCode'].startswith('MEDIA_ERROR_')
                assert diagnostic['urlState'] == 'active'
                assert diagnostic['events'][-1]['sourceAssigned']
                page.click('#video-reset')
                assert json.loads(page.locator('#video-diagnostics').text_content())['urlState'] == 'revoked'
                assert not errors, errors
                browser.close()
                print('Video browser checks passed: landscape/rotated MP4 inference, local codec/rotation inspection, preserved dimension failures, source loss, timeouts, decoding errors, cancellation, URL lifecycle, CSP.')
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    main()
