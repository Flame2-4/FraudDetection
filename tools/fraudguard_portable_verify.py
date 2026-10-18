"""FraudGuard portable PaySim model parity checker (Python standard library only).

Usage:
 python3.12 fraudguard_portable_verify.py portable_model.json reference_predictions.json

For research/demo use only. The scores are not calibrated fraud probabilities.
"""
import json
import math
import sys
from pathlib import Path

FEATURES = ('step', 'type', 'amount', 'oldbalanceOrg', 'oldbalanceDest')
THRESHOLD = 0.30


def predict(record, model):
    data = record['features']
    category = data['type']
    if not isinstance(category, str):
        raise ValueError('type must be a string')
    values = [float(data[key]) for key in ('step', 'amount', 'oldbalanceOrg', 'oldbalanceDest')]
    values.extend(float(category == name) for name in model['categories'])
    if not all(math.isfinite(v) for v in values):
        raise ValueError('Non-finite model input')
    raw = float(model['baseline_prediction'])
    for iteration in model['trees']:
        for nodes in iteration:
            index = 0
            while True:
                node = nodes[index]
                if node[9]:  # is_leaf
                    raw += node[0]  # leaf values already include learning rate
                    break
                feature_index, split_threshold = int(node[2]), float(node[3])
                value = values[feature_index]
                index = int(node[5] if value <= split_threshold else node[6])
    if raw >= 0:
        return 1.0 / (1.0 + math.exp(-raw))
    ex = math.exp(raw)
    return ex / (1.0 + ex)


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python3.12 fraudguard_portable_verify.py portable_model.json reference_predictions.json')
    model = json.loads(Path(sys.argv[1]).read_text())
    records = json.loads(Path(sys.argv[2]).read_text())
    assert len(model['categories']) == 5, 'Unexpected category count'
    assert len(records) == 100, 'Expected 100 reference cases'
    errors = []
    decision_mismatches = []
    for i, record in enumerate(records):
        actual = predict(record, model)
        expected = float(record['expected_score'])
        errors.append(abs(actual - expected))
        if (actual >= THRESHOLD) != (expected >= THRESHOLD):
            decision_mismatches.append(i)
    tolerance = 1e-6
    bad = [i for i, err in enumerate(errors) if err > tolerance]
    print(f'Cases tested: {len(records)}')
    print(f'Maximum absolute score difference: {max(errors):.3g}')
    print(f'Score mismatches (> {tolerance}): {len(bad)}')
    print(f'Threshold decision mismatches: {len(decision_mismatches)}')
    if bad or decision_mismatches:
        print('FAIL: score rows:', bad[:10], 'decision rows:', decision_mismatches[:10])
        raise SystemExit(1)
    print('PASS: all 100 reference cases match')


if __name__ == '__main__':
    main()
