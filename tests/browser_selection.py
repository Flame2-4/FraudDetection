"""Visual selection integration in Chromium. Synthetic video; isolated test worker.

Run with preinstalled Playwright/Chromium: PYTHONPATH=src:tests python3.12 tests/browser_selection.py
"""
import base64
import json
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
        engine=Engine(Path(tmp)/'selection.db')
        server=make_server(engine,port=0,video_jobs=VideoJobs(worker=fake_worker,timeout=10))
        thread=Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
                context=browser.new_context(viewport={'width':1440,'height':1000},has_touch=True)
                page=context.new_page(); errors=[]; violations=[]; submissions=[]
                page.on('pageerror',lambda err:errors.append(str(err)))
                page.on('console',lambda msg:violations.append(msg.text) if 'Content Security Policy' in msg.text else None)
                page.on('request',lambda req:submissions.append(json.loads(req.post_data)) if req.url.endswith('/api/video/jobs') else None)
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                expect(page.locator('#analyzer')).to_be_visible()
                expect(page.locator('#videoguard')).to_be_hidden()
                page.click('.sidebar a[href="#videoguard"]')
                expect(page.locator('#workspace-title')).to_have_text('Video Deepfake')
                expect(page.locator('#analyzer')).to_be_hidden()
                data=page.evaluate('''async () => {
                  const c=document.createElement('canvas'); c.width=640;c.height=480;
                  const ctx=c.getContext('2d'),stream=c.captureStream(10),chunks=[];
                  const recorder=new MediaRecorder(stream,{mimeType:'video/webm'});
                  recorder.ondataavailable=e=>chunks.push(e.data);
                  const done=new Promise(resolve=>recorder.onstop=async()=>{
                    const bytes=new Uint8Array(await new Blob(chunks).arrayBuffer());
                    let raw='';for(const b of bytes)raw+=String.fromCharCode(b);resolve(btoa(raw));
                  });
                  recorder.start();
                  for(let i=0;i<20;i++){ctx.fillStyle=`rgb(${20+i*8},90,110)`;ctx.fillRect(0,0,640,480);await new Promise(r=>setTimeout(r,100));}
                  recorder.stop();stream.getTracks().forEach(t=>t.stop());return done;
                }''')
                sample={'name':'synthetic.webm','mimeType':'video/webm','buffer':base64.b64decode(data)}
                page.locator('#video-file').set_input_files(sample)
                expect(page.locator('#video-confirm')).to_be_enabled(timeout=15000)
                expect(page.locator('#video-ready')).to_have_text('0 of 5 frames ready')
                def values():
                    return [float(page.locator('#crop-'+n).input_value()) for n in ('x','y','w','h')]
                def point(x,y):
                    page.locator('#face-frame').scroll_into_view_if_needed()
                    b=page.locator('#face-frame').bounding_box()
                    return b['x']+b['width']*x/100,b['y']+b['height']*y/100
                def drag(start,end):
                    sx,sy=point(*start);ex,ey=point(*end)
                    page.mouse.move(sx,sy);page.mouse.down();page.mouse.move(ex,ey,steps=8);page.mouse.up()
                drag((5,5),(45,55))
                assert all(abs(a-b)<.7 for a,b in zip(values(),[5,5,40,50])),values()
                assert abs(int(page.locator('#crop-preview').get_attribute('width'))-352)<=5
                page.click('#video-confirm')
                expect(page.locator('#video-ready')).to_have_text('1 of 5 frames ready')
                expect(page.locator('[data-frame="0"]')).to_have_attribute('data-ready','true')
                drag((25,30),(35,40))  # move existing rectangle
                assert all(abs(a-b)<.7 for a,b in zip(values(),[15,15,40,50])),values()
                expect(page.locator('#video-ready')).to_have_text('0 of 5 frames ready')
                drag((55,65),(75,85))  # resize southeast corner
                assert all(abs(a-b)<.7 for a,b in zip(values(),[15,15,60,70])),values()
                drag((45,50),(110,120))  # captured pointer outside canvas must clamp
                x,y,w,h=values();assert x>=0 and y>=0 and x+w<=100.001 and y+h<=100.001
                # Real Chromium touch events produce native PointerEvents/capture.
                cdp=context.new_cdp_session(page)
                sx,sy=point(5,5);ex,ey=point(45,55)
                cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':sx,'y':sy,'id':1}]})
                cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':ex,'y':ey,'id':1}]})
                cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
                assert all(abs(a-b)<.7 for a,b in zip(values(),[5,5,40,50])),values()
                page.click('#video-confirm');original=values()
                sx,sy=point(25,30);ex,ey=point(35,40)
                cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':sx,'y':sy,'id':1}]})
                cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':ex,'y':ey,'id':1}]})
                cdp.send('Input.dispatchTouchEvent',{'type':'touchCancel','touchPoints':[]})
                assert values()==original
                expect(page.locator('#video-ready')).to_have_text('1 of 5 frames ready')
                page.locator('#face-frame').press('ArrowRight')
                assert abs(values()[0]-original[0]-1)<.01
                page.locator('#face-frame').press('Shift+ArrowRight')
                assert abs(values()[2]-original[2]-1)<.01
                page.click('#crop-advanced summary')
                page.fill('#crop-x','99')
                expect(page.locator('#video-error')).to_be_visible()
                page.fill('#crop-x','10')
                expect(page.locator('#video-error')).to_be_hidden()
                page.click('#video-apply-all')
                expect(page.locator('#video-ready')).to_have_text('5 of 5 frames ready',timeout=20000)
                expect(page.locator('#video-analyze')).to_be_enabled()
                assert page.locator('[data-frame][data-ready="true"]').count()==5
                assert not submissions,'Preparing frames must not submit inference'
                page.click('[data-frame="2"]')
                expect(page.locator('#video-confirm')).to_be_enabled()
                page.locator('#face-frame').press('ArrowRight')
                expect(page.locator('#video-ready')).to_have_text('4 of 5 frames ready')
                expect(page.locator('#video-analyze')).to_be_disabled()
                page.click('#video-confirm')
                expect(page.locator('#video-ready')).to_have_text('5 of 5 frames ready')
                page.click('#video-analyze')
                page.click('.sidebar a[href="#analyzer"]')
                expect(page.locator('#analyzer')).to_be_visible()
                page.click('.sidebar a[href="#videoguard"]')
                expect(page.locator('#video-result')).to_be_visible(timeout=15000)
                assert len(submissions)==1 and len(submissions[0]['frames'])==5
                assert len({f['image'] for f in submissions[0]['frames']})>1,'Each sample must use its own decoded frame'
                assert float(page.locator('#video-score').inner_text())==.2
                assert engine.history('events','demo')==[] and engine.history('decisions','demo')==[]
                # Interrupt bulk preparation during a pending seek, not just polling.
                page.evaluate('''() => {
                  const d=Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype,'currentTime');
                  Object.defineProperty(document.getElementById('video-preview'),'currentTime',{get(){return d.get.call(this);},set(v){}});
                }''')
                page.click('#video-apply-all')
                expect(page.locator('#video-apply-all')).to_be_disabled()
                page.click('#video-reset')
                expect(page.locator('#video-ready')).to_have_text('0 of 5 frames ready')
                expect(page.locator('#video-result')).to_be_hidden()
                expect(page.locator('#video-error')).to_be_hidden()
                expect(page.locator('#video-analyze')).to_be_disabled()
                # New file must recover after cancelled bulk preparation.
                page.locator('#video-file').set_input_files(sample)
                expect(page.locator('#video-confirm')).to_be_enabled(timeout=15000)
                page.click('#video-apply-all')
                expect(page.locator('#video-ready')).to_have_text('5 of 5 frames ready',timeout=20000)
                page.click('#crop-advanced summary')
                page.locator('#face-frame').blur()
                page.evaluate('window.scrollTo(0,0)')
                page.screenshot(path='/tmp/fraudguard-video-desktop.png',full_page=True)
                for width in (1280,390):
                    page.set_viewport_size({'width':width,'height':900})
                    assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth'),width
                    page.locator('#face-frame').scroll_into_view_if_needed()
                    b=page.locator('#face-frame').bounding_box()
                    assert b['width']<=width and b['height']<=321
                page.evaluate('window.scrollTo(0,0)')
                page.screenshot(path='/tmp/fraudguard-video-mobile.png',full_page=True)
                assert not errors,errors
                assert not violations,violations
                browser.close()
                print('PASS visual draw/move/resize, bounds, native touch/cancel, keyboard, advanced inputs, apply-all, ready states, jobs, cancellation/recovery, responsive layout and CSP')
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':
    main()
