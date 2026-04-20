# Existing Methods for Satellite-Image-Based Drone Localization

Focused literature and systems review for the specific use case in this project. Complements `Gemini-deep-research.txt` (which is broader and defense-oriented) with a curated, verified, low-altitude-and-server-side-compute angle.

## 1. Use-case assumptions this document is scoped to

| Parameter | Value |
|---|---|
| Platform | Quadcopter, downward-facing (nadir) camera |
| Altitude | 5-100 m AGL |
| GPS | Fully denied (adversarial or degraded) |
| Prior | ~100 m radius from dead-reckoning / IMU |
| Target accuracy | 5 m (lat, lon) |
| Output | (lat, lon) only — no heading/altitude requirement |
| Compute | Server-side (drone streams video, receives commands). Treat as "good hardware" — a workstation/GPU is available. |
| Reference imagery | Any source; pre-cached for the AO is fine |
| Drone speed | Typical quadcopter cruise (~5–15 m/s) |
| Camera | RGB, downward-facing. FOV/resolution treated as free parameters — the approach must not depend on specific values. |

The server-side compute assumption is the single biggest simplification — it means the entire body of work focused on edge inference (Jetson optimization, TinyML, quantization, FPGA acceleration) is **out of scope**. We can pick the most accurate method without a latency ceiling below a few hundred ms per frame.

The 5 m accuracy target combined with 5-100 m altitude is the **hard** constraint — see §6 for why.

---

## 2. Problem framing: three distinct sub-problems

The literature conflates three problems that behave very differently. Keep them separate:

1. **Cross-view geo-localization (CVGL)** — retrieve which tile of a large database matches the current drone view. Output: a tile ID or coarse position. Academic benchmarks (University-1652, SUES-200) operate here.
2. **Pose refinement / image registration** — given a coarse tile, compute precise (lat, lon) within that tile by pixel-accurate alignment. This is where your 5 m target is actually won or lost.
3. **Temporal filtering** — fuse noisy per-frame fixes across time with a motion model so the estimate is stable, resilient to occasional failed frames, and bounded in error.

For our use case:
- The 100 m prior **eliminates problem 1** — we already know the coarse location. We only need to search a ~200×200 m window (at worst). This is enormously simplifying; most CVGL papers solve the much harder problem of kilometer-to-continent-scale retrieval.
- Problem 2 is the core technical challenge.
- Problem 3 is where a particle filter or EKF comes in.

Any design that doesn't exploit the prior properly is wasting compute and accuracy.

---

## 3. Open-source prior art — concrete repositories

Three academic repos tackle almost exactly this problem. None are production-ready, but all are worth reading and cannibalizing.

### 3.1 WildNav — TIERS group
- **URL:** https://github.com/TIERS/wildnav
- **License:** BSD-3-Clause (permissive)
- **Stack:** SuperPoint + SuperGlue matching against a CSV-annotated georeferenced tile directory.
- **Reported accuracy:** MAE of 15.8 m (Dataset 1, 62% of frames localized) and 26.6 m (Dataset 2, 56%). Targets high-altitude non-urban flights.
- **Maintenance:** ~260 stars, last release Oct 2022. Effectively unmaintained.
- **Verdict:** Good architectural reference. Accuracy (15–26 m) does **not** meet our 5 m target. Would need upgraded matcher (RoMa/LoFTR) and a particle filter on top.

### 3.2 VisionUAV-Navigation — sidharthmohannair
- **URL:** https://github.com/sidharthmohannair/VisionUAV-Navigation
- **License:** GPL-3.0 (viral — contamination risk for commercial product)
- **Stack:** Classical — SIFT/ORB/AKAZE/BRISK + RANSAC. No deep matcher.
- **Reported accuracy:** Self-reports "<1% of flight height" and ">95% success" with no released datasets, weights, or peer review. Only 3 commits, ~43 stars.
- **Verdict:** Unverified claims, immature, GPL-3 is problematic if this becomes a product. Skip.

### 3.3 visual_localization — TerboucheHacene
- **URL:** https://github.com/TerboucheHacene/visual_localization
- **License:** MIT (most permissive of the three)
- **Stack:** SuperPoint + SuperGlue; includes a satellite tile downloader and full pipeline scaffold.
- **Maintenance:** Prototype stage, single contributor, no quantitative results published. TODO list suggests incomplete.
- **Verdict:** Best starting scaffold for a POC due to MIT license and tile downloader. But inherits SuperGlue's **non-commercial weight restriction** (see §4).

### 3.4 Datasets worth pulling

- **UAV-VisLoc** (IntelliSensing) — 6,742 drone images at 0.1–0.2 m/px GSD, cross-referenced against 11 orthorectified reference maps. Provides GPS, altitude, heading. **Directly relevant**. https://github.com/IntelliSensing/UAV-VisLoc
- **AnyVisLoc** (arXiv 2503.10692) — 18,000+ images at diverse low altitudes/viewpoints with 2.5D reference maps. Baseline gets 74.1% within 5 m.
- **University-1652 / SUES-200** — popular CVGL benchmarks, but shoot at **150–300 m AGL** in retrieval (not metric) setup. **Wrong regime** for our 5–100 m use case. Don't train on these and expect them to transfer down.

---

## 4. Matching methods — what to actually use

### 4.1 Classical (baseline, not state-of-the-art)

- **SIFT**: scale-invariant, still competitive for aerial, but slow and its descriptors have been beaten by learned methods in cross-seasonal scenarios.
- **ORB** / **AKAZE**: fast, binary descriptors. AKAZE reportedly hits sub-meter alignment in favorable conditions (well-lit, same-season, textured urban). Brittle against illumination / seasonal / temporal gaps.
- **Normalized cross-correlation (NCC)** template matching: viable fallback when there are no keypoints (forest canopies, asphalt). Slow over large search windows but our 100 m prior makes the search tractable.

Classical methods **should be implemented as a baseline** — they are fast and sometimes surprisingly competitive in good conditions. They fail against season change, temporal drift, and low-texture terrain.

### 4.2 Deep sparse matching

The dominant academic and industry stack:

- **SuperPoint + SuperGlue** (MagicLeap). De facto reference. SuperGlue is a Graph Neural Network that solves matching as optimal transport via the Sinkhorn algorithm — contextually aware, robust to repetitive patterns.
  - **Licensing trap:** SuperPoint weights are **non-commercial** (MagicLeap research license). SuperGlue is **non-commercial**. Fine for academic POC; **not OK** for a commercial product without retraining.
- **LightGlue** (CVG, Apache-2.0 code). Faster, more accurate than SuperGlue, but the **official released weights are trained with SuperPoint** — transitively non-commercial.
  - **Commercial-clean combo:** `LightGlue + DISK` or `LightGlue + ALIKED`. All Apache/MIT-compatible. Use this if the project becomes a product.
- https://github.com/cvg/LightGlue, https://github.com/cvg/glue-factory (finetuning)

### 4.3 Deep dense ("detector-free") matching — most relevant here

Detector-free matchers skip keypoint detection entirely and compute dense correspondences directly. They **dominate** for cross-domain, cross-season, low-texture aerial — exactly our case.

- **LoFTR** (ZJU3DV). Transformer-based, established baseline.
- **EfficientLoFTR** (CVPR 2024). Best latency/accuracy sweet spot. Apache-2.0. https://zju3dv.github.io/efficientloftr/
- **DKM** (CVPR 2023). Dense kernelized feature matching.
- **RoMa** (CVPR 2024) and **RoMa v2** (Nov 2025). **Current SOTA** on extreme illumination/season/viewpoint changes (WxBS benchmark). The matcher to beat for our cross-seasonal scenario. https://github.com/Parskatt/RoMa

**Recommendation:** RoMa as the primary matcher given server-side compute. EfficientLoFTR as a faster fallback. The 2025 Aerial Image Matching benchmark (IEEE DataPort) shows RoMa leading on robustness across aerial/season conditions.

### 4.4 Emerging: multi-modal and geometry-aware

- **MINIMA** (CVPR 2025): modality-invariant matching — useful if we extend to thermal or SAR.
- **AerialMegaDepth** (CVPR 2025): pseudo-synthetic aerial views from Google Earth meshes, with MASt3R/DUSt3R finetuned for aerial. Lifted aerial-ground matching from <5% to ~56% within 5°. https://aerial-megadepth.github.io/
- **MASt3R / DUSt3R** in general: foundation 3D matching models that handle extreme viewpoint change. Overkill for nadir-vs-nadir but interesting if the gimbal fails and we need to match oblique views.

### 4.5 NeRF / view-synthesis approaches — mostly not applicable

Sat2Density, Sat2Vid, Sat2Scene, "Seeing through Satellite Images at Street Views" synthesize **ground-level** views from satellite imagery. Wrong viewpoint — we have a nadir camera matching against nadir orthophotos already. Skip.

Exception: "Unsupervised Multi-view UAV Image Geo-localization via Iterative Rendering" (arXiv 2411.14816) — uses rendering for oblique multi-view UAV-to-satellite. Only relevant if our camera isn't actually straight down.

---

## 5. Temporal filtering — how to get from noisy fixes to a stable 5 m estimate

A single-frame match giving ±10 m error is unlikely to hit 5 m consistently. A filter over multiple frames will.

### 5.1 Particle filter / Monte Carlo localization (recommended)

Particle filters are the natural fit for our problem because:
- We have a 100 m prior → seed N particles uniformly within that radius.
- Per-frame match likelihood (match score, inlier count, photometric residual) becomes the particle weight.
- The drone motion model (even rough IMU dead-reckoning) propagates particles between frames.
- After a few frames, the particle cloud collapses to a tight distribution.

Key references:
- **Couturier & Akhloufi (2019)** — "Robust GNSS-Denied Localization for UAV Using Particle Filter and Visual Odometry." Canonical paper for exactly this problem. arXiv 1910.12121.
- **SWA-PF (Sep 2025)** — Semantic-Weighted Adaptive Particle Filter. Uses semantic segmentation + satellite matching. Reports <10 m global error, 4-DoF. Most current reference design. arXiv 2509.13795.
- **Viswanathan et al. (IROS 2015, CMU)** — foundational ground-to-satellite PF.

### 5.2 EKF fusion with VIO

Extended Kalman Filter fusing:
- **Visual-Inertial Odometry** (high-frequency, drifts ~1–4% of distance traveled) — provides smooth relative state at 100 Hz+.
- **CVGL absolute fix** (low-frequency, noisy but drift-free) — provides periodic global anchor.

The EKF gives bounded error over arbitrarily long trajectories. This is the mainstream approach in defense systems (Honeywell HANA, Collins VNS01, UAV Navigation's VECTOR line).

### 5.3 Choice

For our server-side, POC-stage setup: **start with a particle filter**. It's easier to debug, handles multi-modal posteriors (when the matcher returns two plausible locations), and directly consumes the match score as a likelihood. Graduate to EKF + VIO only once the core CVGL pipeline works.

---

## 6. The low-altitude problem — read this carefully

This is the single biggest risk in the project. **The 5 m lower altitude bound is brutal.**

At 5 m AGL with a typical 90° FOV camera, the ground patch visible is roughly **10 × 10 m**. Implications:

1. **Scale mismatch.** Typical "satellite" tiles (Sentinel-2 at 10 m/px, Google/Bing at ~1 m/px) are at a completely different GSD than a 5 m AGL drone frame (which has sub-cm/px resolution). A deep matcher cannot magically bridge a 100× scale gap.
2. **Feature scarcity.** A 10×10 m grass patch, asphalt segment, or forest canopy has almost no distinctive structure. There is nothing to match against.
3. **Altitude dependence of viability.** Cross-view matching gets increasingly reliable as altitude grows — at 100 m AGL you see ~200×200 m of ground, which almost always contains something distinctive (a road intersection, a building corner, a field boundary). At 5 m, you're staring at a patch of lawn.

### 6.1 Mitigations

- **Use high-resolution orthophotos, not traditional satellite imagery.** NAIP (US, annual, ~1 m/px), local government orthophoto programs (often 10–20 cm/px), or Bing Maps (down to 15 cm in some areas). The scale gap from ortho to 5 m AGL is tractable where it is hopeless from Sentinel.
- **Seasonal/temporal matching across a library.** Maintain multiple reference tiles per area from different dates/seasons; match against each and take the best. Absolutely worth doing.
- **Bias toward persistent features.** Train or select methods that weight roads, building edges, water boundaries over vegetation and transient objects. The 2chADCNN and LSVL papers explicitly do this.
- **Lean on VIO/IMU between fixes.** At very low altitude, match fixes will fail often. The system has to survive gaps. This is where §5 (filtering) becomes essential rather than optional.

### 6.2 Blunt assessment

At 5–15 m AGL over **featureless terrain** (open grass, dense forest canopy, water, desert), **no satellite-matching method currently works reliably**, and this is not a matter of picking a better algorithm. The mitigation is operational: either the mission profile keeps the drone above ~30 m when possible, or the system accepts degraded mode at low altitude and relies on VIO + periodic ascents for re-localization.

Above ~30 m AGL with any urban/suburban/agricultural structure in frame, the problem is tractable with modern dense matchers + a particle filter.

### 6.3 Directly relevant low-altitude papers

- **"Exploring the best way for UAV visual localization under Low-altitude Multi-view Observation Condition"** — AnyVisLoc paper, baseline 74.1% within 5 m. arXiv 2503.10692.
- **"Hierarchical AVL System for Low-Altitude Drones"** — Remote Sensing 2025. https://www.mdpi.com/2072-4292/17/20/3470
- **"Beyond Matching to Tiles: Bridging Unaligned Aerial and Satellite Views"** — arXiv 2603.22153.

---

## 7. Seasonal / temporal robustness

The reference imagery will almost certainly be from a different date and possibly season than the live feed. Concrete mitigations, in priority order:

1. **Multiple reference tiles per area.** Store 2–4 versions from different seasons. Match against all; take best. Cheap and effective.
2. **RoMa / robust dense matchers.** Empirically season-robust on WxBS.
3. **Season-invariant descriptors (LSVL).** Robotics and Autonomous Systems 2023. Trained explicitly on cross-season pairs. 12.6–18.7 m lateral error over 100 km². arXiv 2110.01967.
4. **2chADCNN** — template-matching network for season-changing UAV vs satellite (MDPI Drones 2023).
5. **MINIMA (CVPR 2025)** — modality-invariant if we ever need thermal or SAR references.
6. **GAN-based augmentation** during training — synthesize fog, rain, snow, night, seasonal shifts.

Unsolved: **heavy snow cover**. All current methods degrade severely when ground is occluded by snow. No clean solution exists beyond "maintain a snow-covered reference tile and match to it."

---

## 8. Recommended pipeline for this project

A concrete, opinionated starting architecture:

```
Drone video stream (server ingests)
    │
    ▼
[Per-frame: preprocess — rectify for camera intrinsics]
    │
    ▼
[Coarse prior: 100 m radius from dead-reckoning]
    │
    ▼
[Crop reference map to prior window + buffer (e.g. 300 m)]
    │
    ▼
[Dense matching: RoMa (primary) or EfficientLoFTR (speed)]
    │       ├─ match score
    │       └─ estimated (lat, lon) + uncertainty
    ▼
[Particle filter update]
    │   particles weighted by match likelihood
    │   propagated by IMU / VIO motion model
    ▼
[Output: filtered (lat, lon) at target accuracy]
```

### Key design decisions

1. **Reference imagery: high-resolution orthophoto tiles**, stored as MBTiles or a simple tiled directory. Server-side, disk is cheap — keep multiple seasonal versions per area.
2. **Matcher: RoMa (v2 if available).** Server-side latency is fine; accuracy wins.
3. **Prior window exploitation.** Don't retrieve globally — always crop to the 100 m prior window. This makes the matching problem ~1000× easier than the academic CVGL setup.
4. **Particle filter on top.** 500–2000 particles is plenty. Seed uniformly in the prior, propagate by IMU, weight by match score.
5. **Multiple reference tiles per area (seasonal).** Match against each; use best score.
6. **VIO as backup.** When matching fails (low altitude, featureless terrain), fall back to VIO for up to N seconds before declaring lost.
7. **Altitude-aware confidence.** Trust match scores less when altitude < 30 m. Widen uncertainty accordingly.

### Likely failure modes to budget for

- Below ~20 m AGL over featureless terrain: no match. System must survive on VIO.
- Heavy cloud shadow / extreme sun angle: match score drops; filter should downweight.
- Snow-covered ground vs snow-free reference (or vice versa): near-total failure.
- Rapid yaw rotation: matcher is rotation-invariant in principle, but motion blur and frame tearing are real issues.
- Drone crosses into an area without reference tile coverage: the system must detect this and hold on VIO until coverage resumes.

---

## 9. Commercial systems (for sanity-checking what's possible)

All server-side or on-drone, but useful as upper-bound reality checks:

- **Honeywell HANA (Vision Aided Navigation + HCINS)** — vision-only GPS fallback, demonstrated during active jamming. Deep IMU fusion.
- **Collins Aerospace VNS01** — visual odometry with pattern-recognition anchoring against internal maps.
- **UAV Navigation VECTOR-400/600 + GNSS-Denied Kit** — tactical-grade IMU + visual TRN.
- **Oksi.ai OMNInav** — AI feature matching trained on multi-year satellite imagery for terrain-change robustness. Claims <5 W onboard.
- **Skydio X10D** — VIO-centric, manual anchor-drag UX for GPS-denied operation. Not fully autonomous cross-view.

**Takeaway:** Pixel-accurate (sub-5m) vision-only localization at low altitude is an **unsolved problem in the open literature**. Defense vendors claim it but don't publish the details. Our POC goal of 5 m with a 100 m prior is realistic *when conditions are favorable* (>30 m altitude, structured terrain, recent reference imagery) and unrealistic as a hard guarantee across all conditions.

---

## 10. Immediate next steps

1. **Pick a pilot area and acquire high-res orthophoto tiles.** NAIP or equivalent.
2. **Acquire the UAV-VisLoc dataset** as a first evaluation testbed — it's the closest open dataset to our scenario.
3. **Stand up the visual_localization scaffold** (MIT-licensed) and swap SuperGlue → RoMa.
4. **Benchmark on UAV-VisLoc:** measure error distribution as a function of altitude. This tells us empirically where the 5 m target is achievable and where it isn't.
5. **Add a particle filter** once per-frame matching works. Measure error reduction.
6. **Only after the above:** test on our own drone footage, tune, iterate.

### Camera-agnostic design at POC stage

The pipeline should treat camera intrinsics (FOV, resolution, focal length) as runtime inputs rather than baked-in constants:
- Scale/perspective normalization is driven by altitude + intrinsics, not assumed.
- The matcher itself (RoMa / EfficientLoFTR) is scale- and rotation-tolerant enough that moderate FOV/resolution differences don't affect the architecture.
- Particle filter weights depend on match scores, not raw pixel counts.

Staying camera-agnostic means swapping cameras later (different FOV, resolution, rolling vs global shutter) doesn't invalidate the approach.

---

## Appendix A — License summary for pickable components

| Component | License | Commercial-safe |
|---|---|---|
| SuperPoint weights | MagicLeap research (NC) | No |
| SuperGlue | Research (NC) | No |
| LightGlue code | Apache-2.0 | Yes |
| LightGlue + SuperPoint weights | transitively NC | No |
| LightGlue + DISK | Apache/MIT | Yes |
| LightGlue + ALIKED | Apache/MIT | Yes |
| LoFTR / EfficientLoFTR | Apache-2.0 | Yes |
| RoMa | MIT | Yes |
| DKM | MIT | Yes |
| MASt3R / DUSt3R | CC-BY-NC (check current) | No (as of writing) |
| WildNav | BSD-3 | Yes |
| VisionUAV-Navigation | GPL-3.0 | No (viral) |
| visual_localization (TerboucheHacene) | MIT | Yes |

If this becomes a product, the commercially clean matching stack is: **RoMa** or **EfficientLoFTR** (dense) or **LightGlue + DISK/ALIKED** (sparse).

---

## Appendix B — Primary source index

### Papers
- [Couturier & Akhloufi — Robust GNSS-Denied Localization (PF + VO)](https://arxiv.org/abs/1910.12121)
- [SWA-PF — Semantic-Weighted Adaptive Particle Filter (2025)](https://arxiv.org/html/2509.13795v1)
- [LSVL — season-invariant descriptors](https://arxiv.org/abs/2110.01967)
- [AnyVisLoc — low-altitude multi-view benchmark](https://arxiv.org/html/2503.10692v1)
- [Hierarchical AVL for Low-Altitude Drones (MDPI 2025)](https://www.mdpi.com/2072-4292/17/20/3470)
- [Beyond Matching to Tiles](https://arxiv.org/html/2603.22153v2)
- [AerialMegaDepth](https://aerial-megadepth.github.io/)
- [STHN — thermal-satellite homography](https://arxiv.org/html/2405.20470v3)
- [Cross-View Geo-Localization survey](https://arxiv.org/html/2406.09722v1)

### Repositories
- [WildNav](https://github.com/TIERS/wildnav)
- [VisionUAV-Navigation](https://github.com/sidharthmohannair/VisionUAV-Navigation)
- [visual_localization](https://github.com/TerboucheHacene/visual_localization)
- [LightGlue](https://github.com/cvg/LightGlue)
- [RoMa](https://github.com/Parskatt/RoMa)
- [EfficientLoFTR](https://zju3dv.github.io/efficientloftr/)
- [UAV-VisLoc](https://github.com/IntelliSensing/UAV-VisLoc)
- [glue-factory (for finetuning)](https://github.com/cvg/glue-factory)
