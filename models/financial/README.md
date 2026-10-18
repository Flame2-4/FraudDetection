# Portable financial model

`portable_model.json` is the exact user-supplied JSON artifact (uploaded as
`portable_model (1).json`), not a retrained or re-exported model.

SHA-256: `4bb42e763b1f698818a33ae10f8891b0a6c60a5514ea93e62219a112553d0e24`.
The runtime pins this hash. It establishes byte identity, not independent proof
of origin or a cryptographic signature from the trainer.

The user reports training on PaySim and successful s390x verification of all 100
supplied reference cases. The same artifact/verifier/reference triple was checked
here on CPython 3.12.14/x86_64: maximum error 1.11e-16, zero score mismatches at
1e-6 tolerance and zero threshold-classification mismatches. Full integrated
backend testing on LinuxONE remains to be run by the user; no deployment occurred.

The portable data contains 10 boosting iterations, one tree each, 610 total nodes,
five ordered one-hot categories, baseline and informational learning rate 0.08.
Leaf values already include learning rate. No multiplication by 0.08 is applied
at inference. Numerical inputs are step, amount, oldbalanceOrg, oldbalanceDest;
category inputs are CASH_IN, CASH_OUT, DEBIT, PAYMENT, TRANSFER, in artifact order.
Positive class is 1; classification uses score >= 0.30. The score is uncalibrated.

`tools/fraudguard_portable_verify.py` preserves the reviewed user-supplied verifier
unchanged. It is an offline parity utility, not imported by the server. Reference
cases in `tests/fixtures/financial_reference_predictions.json` are supplied PaySim
synthetic fixtures. No customer financial data or joblib/pickle artifact is added.
The inference implementation is original project code matching the supplied
export contract, with bounded loading, hash and graph validation.

Python, NumPy, pandas and scikit-learn version strings in earlier training
metadata describe training, not runtime dependencies of this JSON evaluator.
No training script, complete training split manifest or dataset license evidence
was supplied here; parity alone does not establish accuracy, calibration, data
independence or production authorization. Review data/model licensing before any
use beyond this synthetic research/demo application.
