# FraudGuard AI research bibliography

Research phase only. Checked 2026-10-18. No original research URLs were present
in the conversation or the repository's README and starter Python module.
No reference code, datasets, model weights or application dependencies were installed.

## Evidence and link-verification method

**Verified finding** below means the stated content was read in the linked
source, not experimentally reproduced. **Proposal** is a project choice;
**hypothesis** needs evaluation. Author and organizer READMEs are primary project
artifacts but are not themselves peer-reviewed papers. Publication metadata is
attributed to those artifacts; publisher full texts were not read in this run.

There was no general web-search tool. Research used author/organizer project
pages, followed bibliographies and a researcher-maintained multimodal index,
then checked actual URLs using HTTPS GET with normal certificate verification.
Every primary URL in entries R1–R15 returned HTTP 200 and substantive content.
URLs in the package evidence table also returned HTTP 200 JSON metadata. Raw
GitHub URLs are used intentionally: they are the actual documentation URLs read.
Branch-based URLs can change; retrieval date is not an immutable revision pin.
A successful page retrieval does not verify all outbound links or dataset access.

Direct attempts to access `www.asvspoof.org`, `www.isca-archive.org`, `arxiv.org`,
`openaccess.thecvf.com`, `www.robots.ox.ac.uk`,
`fraud-detection-handbook.github.io`, `www.dalpozzolo.com`, `research.google`,
`nightlies.apache.org`, `research.ibm.com`, `www.ibm.com`, and
`packaging.python.org` were denied by the environment proxy (403).
These are access limitations, not evidence that the sites are broken. Failed
candidate GitHub paths were discarded. The optional paper URLs under the entries
are discovered citations, **not verified working links** in this environment.
Do not represent this bibliography as a full systematic literature review.

## Audio deepfakes, synthetic speech and anti-spoofing

### R1. ASVspoof 2021 challenge organizers — baselines and evaluation

Verified documentation: <https://raw.githubusercontent.com/asvspoof-challenge/2021/main/README.md>

- Type: official benchmark and companion bibliography. Cites Yamagishi et al.,
  *ASVspoof 2021: Accelerating Progress in Spoofed and Deepfake Speech Detection*,
  ASVspoof Challenge Workshop, 2021, pp. 47–54, DOI 10.21437/ASVSPOOF.2021-8.
- Verified finding: baselines include CQCC-GMM, LFCC-GMM, LFCC-LCNN and RawNet2;
  the challenge distinguishes LA, PA and DF tracks (logical access, physical
  access and speech deepfake). These are distinct evaluation settings, not one
  interchangeable notion of fraud.
- Relevance/proposal: study spectral cepstral features with simple classifiers
  before costly learned waveform models. Keep synthetic/converted speech and
  acoustic replay as separate detector outputs. No benchmark scores reproduced.
- Discovered summary citation, publisher access not verified:
  <https://arxiv.org/abs/2210.02437> (Liu et al., 2022 preprint).

### R2. ASVspoof 2021 evaluation package and t-DCF

Verified documentation: <https://raw.githubusercontent.com/asvspoof-challenge/2021/main/eval-package/README.md>

- Type: official evaluation protocol; R1 also cites Kinnunen et al., *Tandem
  Assessment of Spoofing Countermeasures and Automatic Speaker Verification:
  Fundamentals*, IEEE/ACM TASLP 28, 2195–2210, 2020,
  DOI 10.1109/TASLP.2020.3009494.
- Verified finding: tools compute pooled and condition-decomposed EER and minimum
  t-DCF, use full labels/metadata, and allow different ASV scores. Metadata
  includes codec/transmission and attack conditions; PA metadata describes room,
  speaker/microphone and replay conditions.
- Relevance/proposal: report EER and condition-specific results; use t-DCF only
  with its ASV/cost assumptions stated. It is not a bank-loss metric or a
  calibrated probability. Test replay across rooms, playback devices and codecs.

### R3. Jung et al. — AASIST

Verified author documentation: <https://raw.githubusercontent.com/clovaai/aasist/main/README.md>

- Type: author companion to *AASIST: Audio Anti-Spoofing using Integrated
  Spectro-Temporal Graph Attention Networks*. The README cites the 2021 preprint:
  <https://arxiv.org/abs/2110.01200> (not directly verified here).
- Verified finding: documents spectro-temporal graph attention, AASIST/AASIST-L,
  ASVspoof 2019 LA evaluation, and author-reported EER/min t-DCF. Its stated
  training environment uses PyTorch 1.6, CUDA and a V100 GPU.
- Relevance/proposal: learned spectral/temporal representations are research
  candidates. Author-reported benchmark success does not establish robustness
  to unseen generators, real calls, replay or s390x/Python 3.12 compatibility.
  Do not copy its implementation or adopt its old runtime requirements.

### R4. Tak et al. — wav2vec 2.0 and data augmentation for anti-spoofing

Verified author documentation: <https://raw.githubusercontent.com/TakHemlata/SSL_Anti-spoofing/main/README.md>

- Type: companion to *Automatic speaker verification spoofing and deepfake
  detection using wav2vec 2.0 and data augmentation*, Speaker Odyssey, 2022.
  Discovered preprint: <https://arxiv.org/abs/2202.12233> (not directly verified).
- Verified finding: trains on 2019 LA and evaluates 2021 LA/DF; uses learned
  wav2vec representations and augmentation. The documented stack uses Python
  3.7, CUDA-specific PyTorch 1.8.1 and an older fairseq revision.
- Relevance/hypothesis: pretrained embeddings may help generalize across channels;
  verify with unseen speakers/generators and compression. This is not an MVP
  dependency or evidence of deployability on LinuxONE.

### R5. Eyben, Wöllmer and Schuller — openSMILE

Verified maintainer documentation: <https://raw.githubusercontent.com/audeering/opensmile/master/README.md>

- Type: established feature-extraction toolkit; cites *openSMILE — The Munich
  Versatile and Fast Open-Source Audio Feature Extractor*, ACM Multimedia, 2010,
  pp. 1459–1462.
- Verified finding: toolkit is C++, provides x64 prebuilt binaries and a native
  build route, and distinguishes research/educational use from commercial
  licensing. A Python wrapper does not make the underlying engine pure Python.
- Relevance/proposal: investigate prosodic features (pitch variation, energy
  contours, duration, pause rhythm, jitter/shimmer where measurable) alongside
  spectral features. Their value for fraud is a hypothesis, not a conclusion of
  this toolkit documentation. Accent, disability, stress and codecs confound
  these measures; do not infer deception or intent from prosody. License and
  s390x build feasibility must be reviewed before adoption.

## Video manipulation and audiovisual consistency

### R6. Rössler et al. — FaceForensics++

Verified author documentation: <https://raw.githubusercontent.com/ondyari/FaceForensics/master/README.md>

Verified dataset documentation: <https://raw.githubusercontent.com/ondyari/FaceForensics/master/dataset/README.md>

- Type: established benchmark companion to *FaceForensics++: Learning to Detect
  Manipulated Facial Images*, ICCV, 2019.
- Verified finding: original benchmark has 1,000 source sequences and four
  manipulation methods: Deepfakes, Face2Face, FaceSwap and NeuralTextures.
  Documents compression variants, masks, and an access/terms process.
- Relevance/proposal: evaluate spatial artifacts such as blending boundaries,
  texture/frequency anomalies and face-region inconsistencies. Split by source
  video, never by neighboring frames. Test compression and unseen methods;
  these curated faces are not representative of all banking video calls.
- Discovered paper: <https://arxiv.org/abs/1901.08971> (not directly verified).

### R7. Haliassos et al. — LipForensics

Verified author documentation: <https://raw.githubusercontent.com/ahaliassos/LipForensics/main/README.md>

- Type: companion to *Lips Don't Lie: A Generalisable and Robust Approach to
  Face Forgery Detection*, CVPR, 2021, pp. 5039–5049.
- Verified finding: uses cropped mouth sequences and reports cross-dataset
  evaluations on CelebDF-v2, DFDC, FaceShifter and DeeperForensics. Documented
  test runtime is Python 3.8/PyTorch; dataset access may require forms.
- Relevance/proposal: compare temporal mouth-motion consistency with frame-level
  artifacts; keep source and identity splits separate. Reported cross-dataset
  variation cautions against assuming universal performance. No model executed.
- Discovered paper: <https://arxiv.org/abs/2012.07657> (not directly verified).

### R8. Chung and Zisserman — SyncNet

Verified author documentation: <https://raw.githubusercontent.com/joonson/syncnet_python/master/README.md>

- Type: companion to *Out of time: automated lip sync in the wild*, ACCV Workshop
  on Multi-view Lip-reading, 2016.
- Verified finding: estimates audio/video temporal lag and identifies speaking
  faces; documentation includes CPU fallback and synchronization outputs.
- Relevance/hypothesis: abnormal audio/lip alignment could support an anomaly
  signal. SyncNet is a synchronization approach, not proof of a deepfake.
  Benign dubbing, frame drops and network delay can produce mismatches; a synced
  forgery can evade it. CPU fallback does not prove s390x support.

## Financial fraud and streaming analytics

### R9. Le Borgne, Siblini, Lebichot and Bontempi — fraud handbook

Verified author documentation: <https://raw.githubusercontent.com/Fraud-Detection-Handbook/fraud-detection-handbook/main/README.md>

Verified methodology: <https://raw.githubusercontent.com/Fraud-Detection-Handbook/fraud-detection-handbook/main/Chapter_5_ModelValidationAndSelection/ValidationStrategies.ipynb>

Verified synthetic-data description: <https://raw.githubusercontent.com/Fraud-Detection-Handbook/fraud-detection-handbook/main/Chapter_3_GettingStarted/SimulatedDataset.ipynb>

- Type: *Reproducible Machine Learning for Credit Card Fraud Detection — Practical
  Handbook*, ULB, 2022; researcher/practitioner technical book, not a journal
  paper. Notebook prose read; notebook code was not executed or copied.
- Verified finding: temporal validation accounts for delayed fraud labels and
  concept drift. Examples compare ROC AUC, average precision and card precision
  at a review budget. Simulation supports reproducible experiments.
- Relevance/proposal: compare amount/velocity rules, robust per-customer anomaly
  baselines and supervised logistic/tree models when labels exist. Evaluate
  precision-recall, recall at a fixed false-positive/review budget, expected
  costs and calibration with forward splits. An anomaly is not proof of fraud.
  Unsupervised isolation-style methods are candidates, not validated choices.
  Simulated data tests mechanics, not real financial efficacy.
- Reuse restriction: notebook code is GPLv3 and prose CC BY-SA per the README;
  this bibliography summarizes concepts in original prose and copies no code.

### R10. Padhi et al. / IBM — TabFormer

Verified author documentation: <https://raw.githubusercontent.com/IBM/TabFormer/main/README.md>

- Type: companion to *Tabular Transformers for Modeling Multivariate Time
  Series*, ICASSP, 2021, pp. 3565–3569.
- Verified finding: hierarchical tabular sequence models and a synthetic credit
  card dataset (README describes 24 million records, 12 fields). Historical
  stack is Python 3.7/PyTorch 1.6; data delivery uses LFS or an alternate link.
- Relevance/proposal: synthetic transaction structure can inform later original
  telemetry scenarios; sequence learning is a future comparison. Data licensing,
  schema and labels must be inspected before use. No download or license grant
  is implied by an accessible README. Not a cross-channel labeled fraud dataset.

### R11. Apache Flink — event timestamps and watermarks

Verified official source documentation: <https://raw.githubusercontent.com/apache/flink/master/docs/content/docs/dev/datastream/event-time/generating_watermarks.md>

- Type: official streaming-system documentation, not empirical fraud research.
- Verified finding: timestamps and watermarks handle event-time progression and
  bounded out-of-order arrivals; idle partitions can stall progress; alignment
  limits skew and excess buffering across sources.
- Relevance/proposal: adopt explicit event/ingest times, lateness and idle-source
  policies in a small original Python correlator. Kafka/Flink infrastructure is
  optional future scale work, not required for the mock-stream MVP. Documentation
  examples do not verify PyFlink on Python 3.12/s390x.

## Multimodal fusion, correlation and explainability

### R12. Liang et al. — MultiBench and MultiZoo

Verified author documentation: <https://raw.githubusercontent.com/pliang279/MultiBench/main/README.md>

- Type: companion to *MultiBench: Multiscale Benchmarks for Multimodal
  Representation Learning*, NeurIPS Datasets and Benchmarks, 2021, and
  *MultiZoo & MultiBench*, JMLR 24, 2023 (citation block).
- Verified finding: compares early/late fusion and other multimodal methods;
  explicitly includes noisy/missing modalities, generalization and computational
  complexity. Its finance examples are stocks tasks, not banking fraud.
- Relevance/proposal: start with interpretable late fusion of versioned detector
  outputs. Compare with early-feature fusion only when aligned labeled data
  exists. Do ablations, missing-channel and adversarial-noise tests. There is no
  verified evidence here that fraud fusion improves recall or lowers false alerts.

### R13. Paul Pu Liang — multimodal research index

Verified researcher-maintained index: <https://raw.githubusercontent.com/pliang279/awesome-multimodal-ml/master/README.md>

- Type: discovery aid, not peer-reviewed evidence. Contains survey, alignment,
  fusion, missing-modality, fairness and human-review references.
- Verified finding: links *Multimodal Machine Learning: A Survey and Taxonomy*
  (TPAMI, 2019) and *Foundations and Trends in Multimodal Machine Learning*.
- Relevance: use the taxonomy to separate alignment from fusion and uncertainty.
  Discovered survey URLs <https://arxiv.org/abs/1705.09406> and
  <https://arxiv.org/abs/2209.03430> were not directly verified/read here.
  A listed paper is not treated as proof of cross-channel fraud efficacy.

### R14. Lundberg and Lee / SHAP maintainers — feature attribution

Verified maintainer documentation: <https://raw.githubusercontent.com/shap/shap/master/README.md>

- Type: established model-explanation project documentation.
- Verified finding: additive feature attributions connect model outputs with
  Shapley values; tree implementations include native C++ code.
- Relevance/proposal: MVP reason codes and exact rule contributions come first;
  model-specific attribution is future work. Attribution explains a model's
  output, not causality, intent, or guilt. Native dependencies require a separate
  compatibility gate; SHAP is not selected or installed in this phase.

## IBM Z and packaging evidence

### R15. IBM fraud example, Linux on IBM Z guides, and PyPA tags

Verified official example: <https://raw.githubusercontent.com/IBM/ai-on-z-fraud-detection/main/README.md>

Verified community guide entry: <https://raw.githubusercontent.com/linux-on-ibm-z/docs/master/README.md>

Verified packaging specification source: <https://raw.githubusercontent.com/pypa/packaging.python.org/main/source/specifications/platform-compatibility-tags.rst>

- Type: IBM example, platform guidance, and official Python packaging specification.
- Verified finding: IBM's example lists s390x, Python 3.6.9, TensorFlow 2.1 and
  recurrent models using sequences of seven transactions. This is historical
  evidence only; it does not verify our Python 3.12 dependency set. PyPA defines
  Python/ABI/platform tags, universal wheels and manylinux (including s390x for
  manylinux2014). A supported tag does not mean a project publishes that wheel.
- Relevance/proposal: prefer CPU and a minimal standard-library fusion core.
  Consult IBM Z instructions for the actual distribution; independently verify
  builds, endianness, shared libraries and complete dependency resolution.

### Package artifact observations (not an installation or compatibility test)

Each URL below is a verified HTTP 200 registry metadata endpoint. Observations
apply only to that response's latest release `urls` list, not all historical
releases, vendor channels or source-build feasibility. All listed
`Requires-Python` ranges admit 3.12; that is metadata, not execution evidence.
Versions below are observations, **not approved pins**.

| Package / metadata URL | Observed version | Requires-Python | Distribution evidence and risk |
| --- | --- | --- | --- |
| [NumPy](https://pypi.org/pypi/numpy/json) | 2.5.4 | >=3.12 | Native; no s390x wheel listed. Numerical/BLAS build review needed. |
| [SciPy](https://pypi.org/pypi/scipy/json) | 1.18.1 | >=3.12 | Native; no s390x wheel listed. C/C++/Fortran and BLAS/LAPACK build risks. |
| [scikit-learn](https://pypi.org/pypi/scikit-learn/json) | 1.9.1 | >=3.11 | Native; no s390x wheel listed. NumPy/SciPy and compiler/OpenMP compatibility. |
| [pandas](https://pypi.org/pypi/pandas/json) | 3.0.6 | >=3.11 | Native; no s390x wheel listed. NumPy ABI and build requirements. |
| [PyTorch](https://pypi.org/pypi/torch/json) | 2.14.1 | >=3.10 | Native; no s390x wheel listed. CPU operators, compiler and vendor build gate. |
| [ONNX Runtime](https://pypi.org/pypi/onnxruntime/json) | 1.31.0 | >=3.11 | Native; no s390x wheel listed. Model format portability is not runtime portability. |
| [OpenCV Python](https://pypi.org/pypi/opencv-python/json) | 5.0.0.93 | >=3.6 | Native; no s390x wheel listed. Codec, image, compiler and ABI dependencies. |
| [SoundFile](https://pypi.org/pypi/soundfile/json) | 0.14.0 | >=3.10 | Universal wheel listed, but CFFI/libsndfile/native NumPy remain requirements. Not a pure-Python runtime stack. |
| [River](https://pypi.org/pypi/river/json) | 0.26.1 | >=3.11 | No universal or s390x wheel listed. Do not assume an online-learning package is pure Python. |
| [NetworkX](https://pypi.org/pypi/networkx/json) | 3.7 | !=3.14.1,>=3.12 | `py3-none-any` wheel listed; pure-Python graph candidate. Optional numerical integrations need separate checks. |
| [Streamlit](https://pypi.org/pypi/streamlit/json) | 1.66.0 | >=3.11 | `py3-none-any` wheel listed; native transitive dependencies include NumPy, pandas, Pillow and PyArrow. Dashboard phase only. |
| [PyArrow](https://pypi.org/pypi/pyarrow/json) | 26.0.0 | >=3.11 | Native; no s390x wheel listed. Arrow C++/build dependencies can block Streamlit installation. |

## Synthesis and open research questions

**Verified across the sources:** distinct audio attack settings need distinct
protocols; learned detectors have historical runtime assumptions; video
benchmarks expose domain variation; fraud validation needs time/label discipline;
streaming joins need lateness policies; multimodal evaluation must include
missing/noisy channels. None establishes this project's production accuracy.

**Proposed decisions:** original CPU-first late fusion; explicit confidence,
provenance and missingness; deterministic mock events; explainable rules before
learned fusion; reviewable simulated intervention. See [architecture](ARCHITECTURE.md).

**Hypotheses to test later:** independent channels improve detection at a fixed
review budget; reliability-aware fusion beats naive sums; temporal patterns add
value over transaction-only baselines; prosody helps beyond spectral features.
Require a consented, licensed, aligned dataset, leakage-safe splits, ablations,
calibration and subgroup analysis. No verified source here supplies a complete
transaction/audio/video/device/identity fraud ground-truth dataset. Joining
unrelated datasets does not create real cross-channel labels. Synthetic outcomes
can validate logic only. Obtain data governance approval before real-data work.
