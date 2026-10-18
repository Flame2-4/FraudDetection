"""Optional Chromium smoke check; requires preinstalled Playwright and Chromium."""

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from playwright.sync_api import sync_playwright
from fraudguard.api import make_server
from fraudguard.engine import Engine
from helpers import event

with TemporaryDirectory() as tmp:
    engine=Engine(Path(tmp)/'browser.db')
    server=make_server(engine,port=0)
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    errors=[]
    external=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=shutil.which('chromium'),headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1360,'height':1000})
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:external.append(r.url) if not r.url.startswith(f'http://127.0.0.1:{server.server_port}/') else None)
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            for name,score,decision,count in [('normal','0','APPROVE',3),('verify','45','VERIFY',3),('freeze','100','FREEZE',4)]:
                page.select_option('#scenario',name)
                page.click('#replay')
                page.wait_for_function('(d) => document.getElementById("decision").textContent === d',arg=decision)
                assert page.locator('#risk').inner_text()==score
                assert page.locator('#events tr').count()==count
                assert page.locator('#decisions tr').count()==1
                if name=='freeze':
                    assert 'ACTIVE' in page.locator('#block').inner_text()
                    assert '13:02:00' in page.locator('#expiry').inner_text()
                page.click('#replay')
                page.wait_for_function('() => document.getElementById("status").textContent.includes("0 new")')
                assert page.locator('#events tr').count()==count
                print('PASS browser scenario:',name,'risk',score,'decision',decision,'stable records',count)
            page.fill('#at','2026-01-01T13:02:00Z')
            page.click('#refresh')
            page.wait_for_function('() => document.getElementById("decision").textContent === "APPROVE"')
            assert page.locator('#block').inner_text()=='No active block'
            print('PASS browser exact cooling-off expiry')
            page.fill('#at','bad')
            page.click('#refresh')
            page.wait_for_function('() => document.getElementById("status").textContent.includes("timestamp")')
            print('PASS browser meaningful validation errors')
            references=json.loads((Path(__file__).parent/'fixtures/financial_reference_predictions.json').read_text())
            reference=next(row for row in references if row['expected_score']>=.3)
            value=event('browser-ml',tenant='browser-ml',financial_features=reference['features'])
            response=page.request.post(f'http://127.0.0.1:{server.server_port}/api/events',data=value)
            assert response.status==201
            page.fill('#tenant','browser-ml')
            page.fill('#user','u')
            page.fill('#device','d')
            page.fill('#at','')
            page.click('#refresh')
            page.wait_for_function('() => document.getElementById("financial-score").textContent !== "Unavailable"')
            assert abs(float(page.locator('#financial-score').inner_text())-reference['expected_score'])<1e-12
            assert 'FRAUD' in page.locator('#financial-classification').inner_text()
            assert '0.30' in page.locator('#financial-classification').inner_text()
            assert page.locator('#decision').inner_text()=='APPROVE'
            assert 'FRAUD' in page.locator('#decisions').inner_text()
            assert 'Audio/video signals remain simulated' in page.locator('.banner').inner_text()
            print('PASS browser trained ML score, separate 0.30 threshold, history and unchanged fusion decision')
            page.set_viewport_size({'width':390,'height':844})
            assert page.locator('#replay').is_visible()
            assert page.locator('body').evaluate('(e) => e.scrollWidth <= window.innerWidth')
            print('PASS mobile-width layout')
            browser.close()
        assert not errors,errors
        assert not external,external
        print('PASS no browser JavaScript errors and no external/CDN requests')
    finally:
        server.shutdown();server.server_close();thread.join()
