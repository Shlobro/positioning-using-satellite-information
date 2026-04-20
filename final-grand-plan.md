# Final Grand Plan: Satellite-Drone Localization

Created: 2026-04-20
Supersedes: `claude-plan.txt`, `codex-plan.txt`

## 1. Objective

Build a GNSS-denied localization system for a downward-facing drone camera using:

- one RGB frame per packet
- altitude
- heading
- an approximate prior position within about 100 m

Output per packet:

- estimated latitude and longitude
- confidence radius
- match quality
- localization status

Primary target:

- about 5 m accuracy in prioritized conditions
- honest operating envelope instead of a fake universal guarantee

Prioritized conditions:

- 30-100 m AGL
- urban, suburban, industrial, and agricultural structure
- recent overhead imagery
- server-side inference

Non-goals for the first serious prototype:

- full-map global retrieval on every frame
- direct end-to-end lat/lng regression from raw pixels
- onboard embedded optimization
- autonomous flight control

## 2. Core Decisions

1. Treat this as a bounded local alignment problem, not a global retrieval problem.
The 100 m prior is a major simplification and must be exploited aggressively.

2. Use nadir-first frame normalization, not full orthorectification as the default.
For v1, use scale plus rotation normalization under a flat-ground assumption. Keep perspective warping behind a config flag for later only if real data proves it is needed.

3. Benchmark a pretrained dense matcher before training anything custom.
The first neural signal should be zero-shot RoMa. EfficientLoFTR is the fallback if speed is a problem.

4. Keep a classical baseline alive throughout the project.
ORB, AKAZE, and NCC are not optional. They are the sanity check against bad preprocessing and bad labels.

5. Local data overrides public-data conclusions.
Public datasets are for reproducible scaffolding and early benchmark signal. Once real local flights exist, local held-out results become the only decision-making gates.

6. Integrate replay and a minimal live packet path early.
Do not wait until the end to discover that packet parsing, timing, and image transport are broken.

7. No phase is complete without recorded artifacts.
Every milestone must leave behind metrics, visualizations, and a clear change log entry.

## 3. System Overview

Per packet:

1. Receive `{frame, altitude_m, heading_deg, prior_lat, prior_lng, session_id, timestamp_ms}`.
2. Normalize the drone frame using altitude plus FOV for scale and heading for north-up alignment.
3. Crop a local reference window around the prior with margin.
4. Run a localizer inside that window.
5. Convert pixel offset to global position.
6. Calibrate confidence into an error estimate.
7. Fuse over time with a particle filter.
8. Return `{lat, lng, confidence_m, match_score, localization_status, fps}`.

Default model order:

- classical matcher baseline
- zero-shot RoMa
- EfficientLoFTR if RoMa is too slow or unstable
- conditional trained path:
  - fine-tune matcher first if zero-shot is close to useful
  - train a crop-conditioned heatmap localizer first if zero-shot is clearly inadequate and geometry is already sound
  - keep a two-stage coarse-to-fine system only if it materially wins on both accuracy and latency-adjusted value

## 4. Required Project Discipline

### 4.1 Tracking files

`experiments/experiment-log.csv`

- one row per run
- minimum fields:
  - run_id
  - date
  - git_commit
  - phase
  - dataset_version
  - model_name
  - config_path
  - search_radius_m
  - area_type
  - altitude_band
  - train_split
  - val_split
  - test_split
  - primary_metric
  - primary_metric_value
  - notes

`experiments/change-log.md`

- every significant code or config change must be recorded before results are known
- minimum fields:
  - date
  - owner
  - files changed
  - intent
  - linked run_ids
  - actual result

### 4.2 Run artifacts

Every run must write:

- `artifacts/runs/<run_id>/config_snapshot.yaml`
- `artifacts/runs/<run_id>/metrics.json`
- `artifacts/runs/<run_id>/predictions.csv`
- `artifacts/runs/<run_id>/plots/`
- `artifacts/runs/<run_id>/overlays/`
- `artifacts/runs/<run_id>/run.log`

### 4.3 Rules

1. Every milestone must be runnable from a command line entry point.
2. Every comparison must use recorded runs, not memory.
3. Every dataset version must be named and reproducible.
4. No training starts before dataset QA and `label_audit.py` sign-off.
5. No milestone is done without at least one human-inspectable artifact.

## 5. Metrics and Gates

### 5.1 Frame metrics

- mean positional error
- median positional error
- p90 positional error
- p95 positional error
- recall at 1 m, 3 m, 5 m, 10 m
- failure rate below confidence threshold

### 5.2 Tracking metrics

- track median error
- drift over 10 seconds
- estimate jitter while hovering
- relocalization time after failure

### 5.3 Runtime metrics

- end-to-end latency
- preprocessing latency
- matching latency
- filter latency
- throughput fps

### 5.4 Confidence metrics

- expected calibration error
- confidence versus true error correlation
- calibration curve

### 5.5 Subgroup metrics

- altitude band
- area type
- seen-area versus unseen-area
- map age
- lighting or weather if available

### 5.6 Gate policy

Public-data gates are provisional.

- Do not lock hard numeric targets before the first public baseline exists.
- After `RUN-001`, set public-dataset gates using observed baseline numbers.

Local-data gates supersede public-data gates.

- Once real local flight data exists, local held-out geographic areas become the only true model-selection gate.
- Public datasets remain useful only as secondary benchmarks.

Initial working thresholds:

- zero-shot matcher gate:
  - Recall@5m improves by at least 0.10 absolute over the best classical baseline
  - or Recall@10m reaches at least 0.50
- first trained model gate:
  - Recall@5m improves by at least 0.05 absolute over the best earlier baseline
  - and p90 improves by at least 10 percent
- sequence gate:
  - track median error improves by at least 15 percent over frame-only mode
  - jitter improves by at least 25 percent on hover or low-speed segments
- readiness target in prioritized conditions:
  - Recall@5m at least 0.60
  - p90 at most 15 m
  - failure rate at most 0.15
  - confidence calibration acceptable if confidence feeds the filter
  - latency recorded on the actual target machine

## 6. Dataset Strategy

### 6.1 Public data

Use a public low-altitude UAV dataset first for reproducible early work.

Preferred order:

1. UAV-VisLoc
2. DenseUAV
3. other public benchmark data only if needed

Purpose:

- validate the scaffold
- produce first baselines
- benchmark zero-shot pretrained matching before local collection is mature

### 6.2 Local data

Collect local real flights as soon as the scaffold and replay path work.

Required metadata per frame or packet:

- timestamp
- latitude and longitude
- altitude
- heading
- GPS fix quality if available
- camera intrinsics or FOV if known
- map source and map date
- area type

### 6.3 Split policy

Never split by frame only.

Required split hierarchy:

1. hold out at least one geographic area entirely for test
2. split remaining data by session or flight
3. report seen-area and unseen-area metrics separately

### 6.4 Label quality policy

Standard GPS may be enough for baseline evaluation, but not automatically good enough for fine localization training at low altitude.

Requirements:

- run `label_audit.py` before any serious local training
- flag weak-fix or suspicious samples as `LABEL_UNCERTAIN`
- do not silently discard uncertain data
- record all exclusions and reasons in `change-log.md`
- if low-altitude label noise appears to cap performance, prioritize better ground truth before more model complexity

## 7. Recommended Repo Shape

```
src/
  ingest/
  geo/
  models/
  tracking/
  eval/
  server/
scripts/
configs/
  datasets/
  train/
  eval/
artifacts/
experiments/
data/
docs/
```

Important modules to land early:

- `src/geo/frame_normalizer.py`
- `src/geo/crop_generator.py`
- `src/eval/run_manager.py`
- `src/eval/metrics.py`
- `scripts/eval.py`
- `scripts/visualize.py`
- `scripts/label_audit.py`
- `src/server/receiver.py`
- `src/server/localizer.py`

## 8. Execution Plan

### Phase 0. Skeleton, Smoke Test, and Tracking

Goal:
Create the minimal runnable scaffold before model work.

AI agent responsibilities:

- create the repo structure
- implement run management
- implement metric writing and prediction writing
- create placeholder configs
- create a fake-data smoke test

Human responsibilities:

- confirm environment and dependency policy
- verify the repo runs on the machine

Runnable output:

- one command produces `RUN-000`
- metrics file exists
- predictions file exists
- one overlay plot exists

Exit gate:

- fake-data smoke test completes without manual edits

### Phase 1. Geometry, Crop Generation, Replay, and Minimal Live Stub

Goal:
Build the preprocessing stack and prove packet flow before model training.

Key design choice:

- use scale plus rotation normalization first
- log geometry sensitivity instead of pretending inputs are perfect

AI agent responsibilities:

- implement packet schema and packet reader
- implement frame normalization using altitude, FOV, and heading
- implement `geometry_sensitivity_report()`
- implement crop generation around the prior
- implement debug overlays for footprint, prior, and crop
- implement packet replay tool
- implement minimal live receiver stub that accepts one dev-format packet and returns parsed metadata

Human responsibilities:

- provide camera specs if known
- provide one small mapped test area
- verify whether altitude is really AGL or only approximate above takeoff
- inspect debug overlays for gross geometric mismatch

Runnable output:

- given a stored packet, the system produces a normalized frame, a local crop, and a debug visualization
- replay works on stored packets
- a single-session dev packet can be parsed by the minimal live receiver

Exit gate:

- geometry outputs look reasonable across several altitudes
- replay works
- minimal live path has been exercised

### Phase 2. Classical Baseline on Public Data

Goal:
Create the benchmark every learned stage must beat.

AI agent responsibilities:

- implement ORB baseline
- implement AKAZE baseline
- implement NCC fallback for low-texture cases
- implement geometric verification and confidence heuristics
- adapt one public dataset into project format
- run evaluation and save failure galleries

Human responsibilities:

- download the public dataset if login or manual steps are required
- review failure galleries
- verify that failures are not dominated by obviously broken normalization

Runs:

- `RUN-001`: ORB baseline
- `RUN-002`: AKAZE and or NCC baseline

Exit gate:

- first real baseline metrics are recorded
- public provisional gates are set based on observed results

### Phase 3. Zero-Shot Pretrained Matcher Benchmark

Goal:
Get the fastest honest neural signal before custom training.

Primary model:

- RoMa

Fallback:

- EfficientLoFTR if RoMa is too slow or unstable for the intended machine

AI agent responsibilities:

- integrate RoMa for local crop matching
- log latency breakdowns
- generate correspondence and failure visualizations
- produce calibration curves
- compare zero-shot results directly against the classical baseline

Human responsibilities:

- run the benchmark on the actual machine
- review match overlays and runtime behavior

Runs:

- `RUN-003`: RoMa zero-shot
- `RUN-004`: EfficientLoFTR zero-shot only if RoMa is not viable

Decision gate:

- if zero-shot matcher is close to useful, fine-tune matcher first
- if zero-shot matcher is clearly inadequate and geometry is already sound, train a crop-conditioned localizer first
- if neither path is justified, stay in geometry and data investigation instead of pretending progress

Exit gate:

- a go or no-go decision is written to `change-log.md` before training code expands

### Phase 4. Local Dataset Builder and QA

Goal:
Create the local supervised dataset and protect the project from noisy labels.

AI agent responsibilities:

- implement local dataset export from frames plus telemetry
- create manifests with all metadata and uncertainty flags
- implement split generation by geographic area and by session
- implement `label_audit.py`
- implement dataset QA outputs:
  - sample gallery
  - metadata summary
  - coverage histograms
  - leakage checks
  - map-age summary

Human responsibilities:

- collect the first local flights
- review `label_audit.py` output
- explicitly sign off before training starts

Runnable output:

- dataset build command produces versioned train, val, and test manifests
- QA report exists for the dataset version

Exit gate:

- `label_audit.py` passes
- held-out geographic split exists
- human sign-off is recorded in `change-log.md`

### Phase 5. First Trained Model, But Only If Justified

Goal:
Train only the simplest justified learned path.

Recommended order:

1. fine-tune the best pretrained matcher if zero-shot is close to useful
2. train a crop-conditioned heatmap localizer if zero-shot matcher is not good enough and geometry is already trustworthy
3. keep a two-stage localizer plus matcher system only if it materially wins

Matcher fine-tuning default:

- frozen backbone first
- small localization head first
- unfreeze only if the frozen path is promising but insufficient

Crop-conditioned localizer default:

- dual encoder plus correlation or heatmap head
- small enough to train and iterate quickly

AI agent responsibilities:

- implement the chosen training path
- add checkpointing, evaluation, and overlay tooling
- benchmark against classical and zero-shot baselines

Human responsibilities:

- run long training jobs if needed
- review whether accuracy gain justifies latency and complexity

Runs:

- `RUN-005`: best Phase 3 model on local real data without local fine-tuning
- `RUN-006`: first fine-tuned local model if `RUN-005` misses the local gate
- `RUN-007`: ablation or alternate trained path

Exit gate:

- either the trained model beats the best earlier baseline on the agreed gates
- or the trained path is explicitly rejected with recorded evidence

### Phase 6. Particle Filter and Sequence Localization

Goal:
Fuse per-frame estimates over time and make failures visible instead of silent.

Default sequence estimator:

- particle filter first
- factor graph only later if the perception stack becomes stable enough to justify it

AI agent responsibilities:

- implement particle filter
- convert confidence into measurement likelihood
- add coasting behavior when confidence is too low
- add sequence evaluation tools and plots
- compare raw versus calibrated confidence inside the filter

Human responsibilities:

- provide or validate short flight sequences
- review stability, lag, and relocalization behavior

Run:

- `RUN-008`: held-out sequence evaluation with particle filter

Exit gate:

- sequence mode is measurably better than frame-only mode
- relocalization time and jitter are recorded

### Phase 7. Real Streaming Loop and Hardening

Goal:
Run the actual loop on replay and then on real streams, then harden failure behavior.

AI agent responsibilities:

- integrate inference and filtering into a live loop
- implement buffering and timestamp handling
- add fail-safe states:
  - `ok`
  - `uncertain`
  - `lost`
  - `stale`
- add robustness sweeps for:
  - low texture
  - map age mismatch
  - heading uncertainty
  - altitude uncertainty

Human responsibilities:

- provide replay captures or real packet captures
- run local network tests
- perform at least one live field test
- review logs to confirm graceful degradation

Runs:

- `RUN-009+`: robustness sweeps and hard-condition evaluations

Exit gate:

- live or replayed end-to-end demo works
- hard cases are evaluated explicitly
- fallback behavior is confirmed by logs and review

### Phase 8. Packaging, Monitoring, and Readiness Gate

Goal:
Package the system cleanly and make an honest go or no-go decision.

AI agent responsibilities:

- containerize the service
- add metrics endpoint
- add a minimal monitoring dashboard if useful
- write the operational envelope document
- create final benchmark and threshold sweep reports

Human responsibilities:

- deploy and stress test the packaged service
- review the operational envelope against field experience
- decide whether to continue research, field testing, or integration

Exit gate:

- reproducible packaged service exists
- final report shows best model, best filter, latency, calibration, and failure modes
- go or no-go decision is explicit

## 9. Decision Summary

Use this rule set without improvising:

1. If geometry looks wrong, stop model work and fix geometry first.
2. If classical baselines fail completely, do not trust any neural gain until preprocessing and labels are checked.
3. If zero-shot RoMa is close to useful, fine-tune matcher before building a scratch localizer.
4. If zero-shot RoMa is weak and geometry plus labels are already sound, train a crop-conditioned localizer.
5. If local transfer without fine-tuning is already good enough, skip unnecessary training.
6. If the particle filter does not improve stability, recalibrate confidence before adding more estimator complexity.
7. If map age or terrain dominates failures, collect better data before building a larger model.

## 10. First Three Deliveries

Deliver these before any ambitious training push:

1. project skeleton plus `RUN-000` smoke test
2. geometry, crop generation, replay, and minimal live receiver
3. classical baseline plus public benchmark failure gallery

These three deliveries answer the most important early question:
is the problem actually tractable with your map source, geometry assumptions, and data quality?

## 11. Main Risks and Planned Mitigations

Weak texture at low altitude:

- keep NCC fallback
- report subgroup metrics
- do not average away failure regimes

Bad or stale reference imagery:

- log map source and map date every run
- report metrics by map age
- prefer better orthophotos when available

Noisy labels:

- require `label_audit.py`
- keep uncertain labels visible
- improve ground truth before scaling model complexity

Leakage and fake generalization:

- hold out full geographic areas
- report seen-area versus unseen-area separately

Latency creep:

- record runtime from the start
- only keep added model complexity if the gain is real

Process drift:

- mandatory `experiment-log.csv`
- mandatory `change-log.md`
- per-run artifacts

## 12. Definition of Done

The project is only done when all of the following are true:

- a replayed or live packet stream runs end to end
- the system outputs global position, confidence, and status continuously
- results are measured on held-out local data, not just anecdotes
- sequence mode is better than frame-only mode
- failure modes are documented by condition
- the best model and configuration are reproducible from versioned code and config
- the operational envelope says clearly where the system works and where it should not be trusted

