"""Optional Chromium smoke check; requires preinstalled Playwright and Chromium."""

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from playwright.sync_api import sync_playwright, expect
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
            page.wait_for_function('() => [...document.querySelectorAll("[data-sample]")].every(b => !b.disabled)')
            sample_data=page.request.get(f'http://127.0.0.1:{server.server_port}/api/financial/samples').json()['samples']
            analysis_requests=[]
            page.on('request',lambda r:analysis_requests.append(r) if r.url.endswith('/api/financial/analyze') else None)
            fields={'type':'#transaction-type','step':'#transaction-step','amount':'#transaction-amount',
                    'oldbalanceOrg':'#sender-balance','oldbalanceDest':'#recipient-balance'}
            for sample in sample_data:
                previous=len(analysis_requests)
                page.click(f'[data-sample="{sample["id"]}"]')
                assert len(analysis_requests)==previous, 'Selecting a sample must not run inference'
                for name,selector in fields.items():
                    actual=page.locator(selector).input_value()
                    assert (actual==sample['features'][name] if name=='type' else float(actual)==sample['features'][name])
                assert page.locator('#analyzer-output').is_hidden()
                page.click('#analyze-submit')
                expect(page.locator('#analyzer-output')).to_be_visible()
                expected=engine.financial_model.assess(sample['features'])
                assert abs(float(page.locator('#analyzer-exact-score').text_content())-expected['score'])<1e-12
                assert page.locator('#analyzer-classification').inner_text()==expected['classification']
                assert abs(float(page.locator('#analyzer-meter').get_attribute('value'))-expected['score'])<1e-12
                assert '0.30' in page.locator('#analyzer-threshold').inner_text()
                print('PASS analyzer sample and real backend prediction:',sample['id'])
            # The judge can edit a sample and immediately run a new real prediction.
            page.fill('#sender-balance','0')
            expect(page.locator('#analyzer-output')).to_be_hidden()
            page.click('#analyze-submit')
            expect(page.locator('#analyzer-output')).to_be_visible()
            edited={**sample_data[-1]['features'],'oldbalanceOrg':0}
            assert abs(float(page.locator('#analyzer-exact-score').text_content())-engine.financial_model.predict(edited))<1e-12
            page.screenshot(path='/tmp/fraudguard-analyzer-desktop.png',full_page=False)
            print('PASS edited sample, repeated analysis without page refresh')
            # Missing and invalid values must not trigger an API call or show stale scores.
            for selector,value,error_selector in [('#transaction-amount','-1','#amount-error'),
                                                  ('#transaction-step','2.5','#step-error'),
                                                  ('#sender-balance','','#oldbalanceOrg-error')]:
                page.click('[data-sample="low"]')
                page.fill(selector,value)
                previous=len(analysis_requests)
                page.click('#analyze-submit')
                expect(page.locator(error_selector)).not_to_be_empty()
                assert len(analysis_requests)==previous
                assert page.locator('#analyzer-output').is_hidden()
                assert page.locator(selector).get_attribute('aria-invalid')=='true'
            print('PASS analyzer required/numeric validation and stale-result prevention')
            page.click('[data-sample="low"]')
            # Hold an actual request to inspect loading state and prevent double submit.
            held=[]
            page.route('**/api/financial/analyze',lambda route:held.append(route))
            page.click('#analyze-submit')
            expect(page.locator('#analyzer-result')).to_have_attribute('aria-busy','true')
            expect(page.locator('#analyze-submit')).to_be_disabled()
            assert page.locator('#analyzer-fields').evaluate('(field) => field.disabled')
            expect(page.locator('#transaction-amount')).to_be_disabled()
            page.locator('#analyzer-form').evaluate('(form) => form.requestSubmit()')
            assert len(held)==1
            held[0].continue_()
            expect(page.locator('#analyzer-output')).to_be_visible()
            expect(page.locator('#analyze-submit')).to_be_enabled()
            page.unroute('**/api/financial/analyze')
            print('PASS analyzer loading state and duplicate-submit protection')
            # Error states never substitute scores, and the next analysis can recover.
            def fail_network(route):
                route.abort('failed')
            page.route('**/api/financial/analyze',fail_network)
            page.click('#analyze-submit')
            expect(page.locator('#analyzer-error')).to_contain_text('Unable to reach')
            assert page.locator('#analyzer-output').is_hidden()
            page.unroute('**/api/financial/analyze',fail_network)
            for status,body,mime,message in [(503,'{"error":"Temporary analysis failure; retry."}','application/json','Temporary analysis failure'),
                                           (200,'{}','application/json','unexpected model result'),
                                           (500,'<html>Error</html>','text/html','unreadable response')]:
                page.route('**/api/financial/analyze',lambda route:route.fulfill(status=status,body=body,content_type=mime))
                page.click('#analyze-submit')
                expect(page.locator('#analyzer-error')).to_contain_text(message)
                assert page.locator('#analyzer-output').is_hidden()
                page.unroute('**/api/financial/analyze')
            page.click('#analyze-submit')
            expect(page.locator('#analyzer-output')).to_be_visible()
            assert page.locator('#analyzer-error').is_hidden()
            assert engine.history('events','demo')==[]
            assert engine.history('decisions','demo')==[]
            assert engine.history('blocks','demo')==[]
            print('PASS analyzer network/server/contract errors, retry recovery and no database writes')
            page.click('.sidebar nav a[href="#events-panel"]')
            expect(page.locator('.sidebar nav a[href="#events-panel"]')).to_have_attribute('aria-current','location')
            page.click('.sidebar nav a[href="#analyzer"]')
            page.locator('#analyzer-title').scroll_into_view_if_needed()
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
            page.locator('#analyzer-title').scroll_into_view_if_needed()
            assert page.locator('#analyze-submit').is_visible()
            page.screenshot(path='/tmp/fraudguard-analyzer-mobile.png',full_page=False)
            print('PASS mobile-width analyzer and preserved investigation layout')
            browser.close()
        assert not errors,errors
        assert not external,external
        print('PASS no browser JavaScript errors and no external/CDN requests')
    finally:
        server.shutdown();server.server_close();thread.join()
