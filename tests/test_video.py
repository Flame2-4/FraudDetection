"""Synthetic media only; actual model acceptance runs separately on LinuxONE."""
import base64
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from http.client import HTTPConnection

from fraudguard.api import make_server
from fraudguard.engine import Engine
from fraudguard.models import CapacityError, ValidationError
from fraudguard.video import VideoJobs, validate, decode_image, MAX_IMAGE


def fake_worker(incoming, outgoing, path):
    while True:
        payload = incoming.get()
        for _, raw in payload['frames']:
            decode_image(raw).close()
        outgoing.put({'scores': [.2] * len(payload['frames'])})


def hanging_worker(incoming, outgoing, path):
    incoming.get()
    time.sleep(30)


def payload(size=(100, 100)):
    from PIL import Image
    stream = io.BytesIO()
    Image.new('RGB', size, 'gray').save(stream, format='JPEG')
    return {'duration': 2, 'frames': [{'timestamp': .2, 'image': base64.b64encode(stream.getvalue()).decode()}]}


class VideoTests(unittest.TestCase):
    def wait(self, jobs, key):
        for _ in range(150):
            result = jobs.get(key)
            if result and result['status'] in {'complete', 'failed'}:
                return result
            time.sleep(.02)
        self.fail('job did not complete')

    def test_validation(self):
        value = payload()
        self.assertEqual(len(validate(value)['frames']), 1)
        for bad in ({}, {'duration': True, 'frames': []}, {'duration': float('nan'), 'frames': []},
                    {**value, 'duration': 61}, {**value, 'frames': value['frames'] * 9},
                    {**value, 'frames': value['frames'] * 2},
                    {**value, 'frames': [{'timestamp': 2, 'image': 'bad'}]},
                    {**value, 'frames': [{'timestamp': 1, 'image': 'a' * (MAX_IMAGE*2)}]},
                    {**value, 'frames': [{'timestamp': 1, 'image': '!!!'}]},
                    {**value, 'frames': [{'timestamp': 1, 'image': 'YWJj'}]}):
            with self.subTest(bad=str(bad)[:80]), self.assertRaises(ValidationError):
                validate(bad)

    def test_image_bounds_and_malformed_jpeg(self):
        for size in ((31, 100), (1921, 50), (1081,1081)):
            with self.assertRaises(ValueError):
                decode_image(validate(payload(size))['frames'][0][1])
        with self.assertRaises(Exception):
            decode_image(b'\xff\xd8\xffgarbage')
        decode_image(validate(payload((800,600)))['frames'][0][1]).close()

    def test_portrait_crop_keeps_native_dimensions(self):
        # A rotated HD video's padded face crop can retain portrait dimensions.
        # The old landscape-only server gate rejected this valid browser output.
        with decode_image(validate(payload((720,1280)))['frames'][0][1]) as image:
            self.assertEqual(image.size, (720,1280))

    def test_repeated_jobs_and_expiry(self):
        jobs = VideoJobs(worker=fake_worker, timeout=3, ttl=1)
        try:
            for _ in range(3):
                key = jobs.submit(payload())['job_id']
                result = self.wait(jobs, key)
                self.assertEqual(result['status'], 'complete')
                self.assertEqual(result['mean_deepfake_score'], .2)
                self.assertEqual(result['frames_analyzed'], 1)
                self.assertNotIn('classification', result)
                self.assertFalse(result['persisted'])
            time.sleep(1.05)
            self.assertIsNone(jobs.get(key))
        finally:
            jobs.close()

    def test_capacity_timeout_and_recovery(self):
        jobs = VideoJobs(worker=hanging_worker, timeout=.2)
        try:
            first = jobs.submit(payload())['job_id']
            jobs.submit(payload())
            with self.assertRaises(CapacityError):
                jobs.submit(payload())
            # A busy Torch worker must not prevent normal HTTP financial inference.
            with TemporaryDirectory() as tmp:
                server = make_server(Engine(Path(tmp)/'busy.db'), port=0, video_jobs=jobs)
                thread = Thread(target=server.serve_forever, daemon=True); thread.start()
                try:
                    conn = HTTPConnection('127.0.0.1', server.server_port, timeout=2)
                    features = {'type':'PAYMENT', 'step':1, 'amount':1, 'oldbalanceOrg':100, 'oldbalanceDest':0}
                    conn.request('POST', '/api/financial/analyze', json.dumps({'features':features}), {'Content-Type':'application/json'})
                    response = conn.getresponse()
                    self.assertEqual(response.status,200)
                    self.assertEqual(json.loads(response.read())['financial_ml']['status'],'scored')
                    conn.close()
                    self.assertEqual(self.wait(jobs, first)['status'], 'failed')
                finally:
                    server.shutdown(); server.server_close(); thread.join()
        finally:
            jobs.close()

    def test_http_isolation_limits_and_errors(self):
        with TemporaryDirectory() as tmp:
            engine = Engine(Path(tmp)/'video.db')
            jobs = VideoJobs(worker=fake_worker, timeout=3)
            server = make_server(engine, port=0, video_jobs=jobs)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def call(path, value=None):
                conn = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                body = json.dumps(value) if value is not None else None
                conn.request('POST' if body else 'GET', path, body, {'Content-Type': 'application/json'})
                response = conn.getresponse()
                raw = response.read()
                conn.close()
                return response.status, json.loads(raw)
            try:
                before = engine.history('events', 'demo')
                code, job = call('/api/video/jobs', payload())
                self.assertEqual(code, 202)
                self.wait(jobs, job['job_id'])
                code, result = call('/api/video/jobs/'+job['job_id'])
                self.assertEqual(code, 200)
                self.assertEqual(result['status'], 'complete')
                self.assertEqual(call('/api/video/jobs/unknown')[0],404)
                self.assertEqual(call('/api/video/jobs', {})[0],400)
                conn = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                conn.putrequest('POST', '/api/video/jobs')
                conn.putheader('Content-Length', str(3*1024*1024+1))
                conn.putheader('Content-Type', 'application/json')
                conn.endheaders()
                response = conn.getresponse()
                self.assertEqual(response.status, 413)
                response.read(); conn.close()
                self.assertEqual(call('/api/financial/analyze', {'junk':'a'*65536})[0],413)
                self.assertEqual(call('/api/health')[0],200)
                self.assertEqual(engine.history('events', 'demo'), before)
            finally:
                server.shutdown(); server.server_close(); thread.join()

class ModelWorkerContractTests(unittest.TestCase):
    def test_processor_cpu_labels_and_softmax_contract(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        import queue
        from fraudguard.video import model_worker
        incoming, outgoing = queue.Queue(), queue.Queue()
        incoming.put(validate(payload())); incoming.put(None)
        model = Mock()
        model.cpu.return_value = model
        model.eval.return_value = model
        model.config = SimpleNamespace(id2label={0:'Realism', 1:'Deepfake'}, num_labels=2)
        logits = SimpleNamespace(shape=(1,2))
        model.return_value = SimpleNamespace(logits=logits)
        processor = Mock(return_value={'pixel_values': 'processed'})
        image_loader = Mock(); image_loader.from_pretrained.return_value = processor
        model_loader = Mock(); model_loader.from_pretrained.return_value = model
        probabilities = Mock(); probabilities.__getitem__ = Mock(return_value=SimpleNamespace(item=lambda: .73))
        torch = SimpleNamespace(set_num_threads=Mock(), inference_mode=nullcontext,
                                softmax=Mock(return_value=probabilities))
        transformers = SimpleNamespace(AutoImageProcessor=image_loader, AutoModelForImageClassification=model_loader)
        with patch.dict('sys.modules', {'torch':torch, 'transformers':transformers}):
            model_worker(incoming, outgoing, '/trusted/model')
        self.assertEqual(outgoing.get_nowait()['scores'], [.73])
        image_loader.from_pretrained.assert_called_once_with('/trusted/model', local_files_only=True, trust_remote_code=False)
        model_loader.from_pretrained.assert_called_once_with('/trusted/model', local_files_only=True, trust_remote_code=False, use_safetensors=True)
        model.assert_called_once_with(pixel_values='processed')
        torch.softmax.assert_called_once_with(logits, dim=-1)
        probabilities.__getitem__.assert_called_once_with((0,1))
