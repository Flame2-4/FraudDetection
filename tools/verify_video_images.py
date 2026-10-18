"""Manual LinuxONE acceptance: compare identical cropped JPEG bytes with Kaggle.

Manifest: [{"image": "crop.jpg", "sha256": "...", "expected_score": 0.123}]
Paths are trusted local operator inputs, never an HTTP API. No model downloads.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import time

from fraudguard.video import VideoJobs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--model', default='/home/ibm-user/VideoGuard/model')
    parser.add_argument('--tolerance', type=float, default=1e-6)
    args = parser.parse_args()
    if not 0 <= args.tolerance <= .001:
        parser.error('tolerance must be within 0–0.001')
    rows = json.loads(args.manifest.read_text())
    if not rows:
        parser.error('manifest must contain reference crops')
    jobs = VideoJobs(args.model)
    differences = []
    try:
        for row in rows:
            raw = (args.manifest.parent / row['image']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('cropped-image hash mismatch')
            expected = float(row['expected_score'])
            if not 0 <= expected <= 1:
                raise ValueError('invalid expected score')
            key = jobs.submit({'duration': 1, 'frames': [{'timestamp': 0, 'image': base64.b64encode(raw).decode()}]})['job_id']
            deadline = time.monotonic()+190
            while time.monotonic() < deadline:
                result = jobs.get(key)
                if result and result['status'] == 'failed':
                    raise RuntimeError(result['error'])
                if result and result['status'] == 'complete':
                    delta = abs(result['mean_deepfake_score']-expected)
                    differences.append(delta)
                    if delta > args.tolerance:
                        raise ValueError(f'image score parity failed: difference {delta}')
                    break
                time.sleep(.2)
            else:
                raise TimeoutError('acceptance job expired')
            # Acceptance can contain more than 16 cases without retaining old results.
            with jobs.lock:
                jobs.jobs.pop(key, None)
        print(json.dumps({'matched': len(differences), 'max_absolute_difference': max(differences),
                          'tolerance': args.tolerance, 'scope': 'identical JPEG image-level parity only'}))
    finally:
        jobs.close()


if __name__ == '__main__':
    main()
