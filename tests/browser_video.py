"""Chromium native WebM decode, manual padding, real HTTP jobs with a TEST worker.

No real model is installed on this test host. Test worker scores are never used
by the application in serving mode. Generate a synthetic moving canvas video.
"""
import base64
import shutil
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
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                data = page.evaluate('''async () => {
                  const canvas = document.createElement('canvas'); canvas.width=320; canvas.height=240;
                  const ctx = canvas.getContext('2d'); const stream = canvas.captureStream(10);
                  const recorder = new MediaRecorder(stream, {mimeType:'video/webm'}); const chunks=[];
                  recorder.ondataavailable=e=>chunks.push(e.data);
                  const result = new Promise(resolve => recorder.onstop=async()=>{
                    const bytes=new Uint8Array(await new Blob(chunks).arrayBuffer());
                    let raw=''; for (const b of bytes) raw+=String.fromCharCode(b); resolve(btoa(raw));
                  });
                  recorder.start();
                  for(let i=0;i<20;i++){ctx.fillStyle=i%2?'#347788':'#448899';ctx.fillRect(0,0,320,240); await new Promise(r=>setTimeout(r,100));}
                  recorder.stop(); stream.getTracks().forEach(t=>t.stop()); return result;
                }''')
                page.locator('#video-file').set_input_files({'name':'synthetic.webm','mimeType':'video/webm','buffer':base64.b64decode(data)})
                expect(page.locator('#video-crop')).to_be_enabled(timeout=15000)
                # Original face box: 160x168, pad floor(.25*168)=42.
                page.wait_for_function("document.getElementById('crop-preview').width === 244")
                assert page.locator('#crop-preview').get_attribute('width') == '244'
                assert page.locator('#crop-preview').get_attribute('height') == '240'
                for i in range(5):
                    page.select_option('#video-frame', str(i))
                    expect(page.locator('#video-crop')).to_be_enabled()
                    page.click('#video-confirm')
                expect(page.locator('#video-analyze')).to_be_enabled()
                for _ in range(2):
                    page.click('#video-analyze')
                    expect(page.locator('#video-result')).to_be_visible(timeout=15000)
                    assert page.locator('#video-score').inner_text() == '0.200000'
                    assert '5 frames analyzed' in page.locator('#video-count').inner_text()
                page.click('#video-reset')
                expect(page.locator('#video-result')).to_be_hidden()
                page.locator('#video-file').set_input_files({'name':'bad.mp4','mimeType':'video/mp4','buffer':b'not a video'})
                expect(page.locator('#video-error')).to_be_visible()
                assert not errors, errors
                browser.close()
                print('Video browser checks passed: native decode, padded crops, 5 frames, repeated jobs, clear, malformed video.')
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    main()
