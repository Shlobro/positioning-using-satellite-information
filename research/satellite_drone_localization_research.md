# Satellite-Image-Based Drone Localization for Low-Altitude Quadcopters

Last updated: 2026-04-19

## Scope of this document

This document is intentionally narrow. It only covers prior work and methods that are relevant to this project:

- Platform: quadcopter / multirotor UAVs
- Camera: downward-facing or near-nadir RGB camera
- Altitude: roughly 10-100 m AGL
- Prior knowledge: the drone location is already known to within about 100 m from dead reckoning or similar means
- Compute: remote/server-side, not constrained to onboard embedded inference
- Goal: recover global position from overhead reference imagery when GNSS is denied or unreliable
- Environment: all outdoor environments, but with an honest assessment of where the method is likely to fail

I excluded ground-to-satellite geo-localization, generic visual place recognition papers with no UAV angle, and methods that mainly target fixed-wing aircraft or very high altitude flight unless they contain ideas that transfer directly to this use case.

## Executive summary

Short answer: yes, people have done closely related things before.

The main pattern in the literature is:

1. Get a coarse location estimate, either from global image retrieval or from another sensor.
2. Align the current UAV frame to a local overhead map crop.
3. Fuse the per-frame estimate over time with a particle filter, VIO/VO, or a sliding-window optimizer.

For this project, the strongest implication is that the 100 m prior changes the problem a lot. Most papers spend substantial effort on global retrieval because they do not know where the UAV is. You do. That means the most relevant technical problem is not "find the right tile anywhere in the map" but "align this downward-looking image precisely inside a small local crop."

That strongly suggests the best theoretical direction is:

- local crop around the prior
- dense or semi-dense learned matching against overhead imagery
- robust geometric fitting
- temporal filtering with dead reckoning

The literature does support this direction, but it also shows a hard limit: low-altitude matching becomes unreliable in weak-texture scenes, especially if the overhead imagery is coarse or old. In practice, 30-100 m in structured terrain looks feasible. Ten to twenty meters in homogeneous terrain remains weak in the open literature.

## The most relevant prior work

### 1. GPS-Denied UAV Localization using Pre-existing Satellite Imagery (Goforth and Lucey, ICRA 2019)

Paper: [CMU publication page](https://publications.ri.cmu.edu/gps-denied-uav-localization-using-pre-existing-satellite-imagery)  
Code: [hmgoforth/gps-denied-uav-localization](https://github.com/hmgoforth/gps-denied-uav-localization)

Why it matters:

- This is one of the most directly relevant early papers for your setup.
- It assumes a downward-facing monocular RGB camera and pre-existing satellite imagery.
- It uses learned CNN features to reduce the appearance gap between UAV and satellite imagery.
- It improves localization by jointly optimizing alignment to the satellite map and consistency between adjacent UAV frames.

Reported result:

- The CMU page reports average localization error below 8 m for a 0.2 km altitude flight over 0.85 km.

Relevance to your use case:

- High. The core idea, frame-to-map alignment plus temporal consistency, is still relevant.
- The weakness is that the method is old and uses an older deep alignment stack.
- It was demonstrated at about 200 m altitude, so it does not answer the hardest 10-30 m regime directly.

Takeaway:

- Architecturally important.
- Not the best matcher by current standards.
- Still worth reading because it matches your problem formulation more closely than many newer retrieval papers.

### 2. Robust GNSS Denied Localization for UAV Using Particle Filter and Visual Odometry (Jurevicius et al., 2019)

Paper: [arXiv](https://arxiv.org/abs/1910.12121)

Why it matters:

- It is an explicit particle-filter-based map-relative localization paper.
- The abstract states a downward-facing optical camera mounted on the aircraft.
- It focuses on how image similarity should be converted into measurement likelihood inside the particle filter.

Relevance to your use case:

- High conceptually.
- The paper uses simulated aerial imagery rather than a modern large real benchmark.
- The value here is less the feature extractor and more the filtering formulation.

Takeaway:

- Good reference for measurement models and likelihood weighting.
- Strong support for using a particle filter on top of image matching, especially because you already have a local prior.

### 3. GNSS-denied geolocalization of UAVs by visual matching of onboard camera images with orthophotos (Kinnari et al., 2021)

Paper summary: [Aalto research portal](https://research.aalto.fi/en/publications/gnss-denied-geolocalization-of-uavs-by-visual-matching-of-onboard)

Why it matters:

- It explicitly frames the classical UAV-to-orthophoto localization problem.
- It uses Monte Carlo localization with inertial measurements and an orthoimage map.
- It relaxes the requirement for a strictly downward camera by orthorectifying the UAV image under a local planarity assumption.

Relevance to your use case:

- High for filtering and map matching logic.
- Your camera is already downward-facing, which makes your case easier than theirs.

Takeaway:

- Strong evidence that particle filtering plus orthoimage matching is a sensible design.
- Since your camera is nadir-facing and you already have a 100 m prior, your online problem is narrower and easier than the one they solve.

### 4. Season-Invariant GNSS-Denied Visual Localization for UAVs (Kinnari, Verdoja, Kyrki, RA-L 2022)

Paper: [Aalto research portal](https://research.aalto.fi/en/publications/season-invariant-gnss-denied-visual-localization-for-uavs/)  
Code: [aalto-intelligent-robotics/sivl](https://github.com/aalto-intelligent-robotics/sivl)

Why it matters:

- It directly targets seasonal appearance change between UAV images and overhead maps.
- It uses a trained CNN similarity model for matching UAV images to georeferenced orthophotos.
- It is one of the clearest examples of a UAV-specific map-matching system rather than a generic cross-view benchmark.

Important public-code note:

- The code is public, but the repository states that the pretrained checkpoint was removed on 2025-09-18 and is no longer available for download.

Relevance to your use case:

- High for training strategy and seasonal robustness.
- Less useful as a drop-in system because the pretrained checkpoint is unavailable.

Takeaway:

- Strong reference for how to train season-invariant overhead/UAV similarity.
- Public code exists, but expect to retrain.

### 5. LSVL: Large-scale season-invariant visual localization for UAVs (2023)

Paper: [arXiv](https://arxiv.org/abs/2212.03581)

Why it matters:

- It scales the same research line to global localization on maps up to 100 km^2.
- It reports 12.6-18.7 m lateral translation error from uninformed initialization.
- It predicts heading, latitude, and longitude from orthoprojected UAV imagery matched to satellite imagery using learned season-invariant descriptors.

Relevance to your use case:

- Medium.
- It is valuable because it proves seasonal descriptor learning can work on large maps.
- It is less directly aligned with your problem because your 100 m prior makes global search much less important.

Takeaway:

- Good evidence that learned descriptors and filtering can handle large uncertainty.
- Your project should reuse the descriptor robustness ideas, not the full large-scale search setup.

### 6. Vision-based GNSS-Free Localization for UAVs in the Wild / WildNav (2022-2023)

Paper: [arXiv](https://arxiv.org/abs/2210.09727)  
Code: [TIERS/wildnav](https://github.com/TIERS/wildnav)

Why it matters:

- Public code and dataset are available.
- The paper targets UAV-to-satellite localization in the wild using georeferenced open-source satellite images.
- The repo uses SuperPoint plus SuperGlue for matching.

What it actually solves:

- Long-distance, high-altitude, non-urban localization.
- The paper abstract explicitly says it is designed for long-distance, high-altitude flights.

Relevance to your use case:

- Medium.
- It is a useful code scaffold for a proof of concept.
- It is not a good answer to the 10-100 m multirotor regime, especially not the 10-30 m edge cases.

Takeaway:

- Good starting point if you want a working open pipeline quickly.
- Replace the matcher and do not assume its reported accuracy transfers to low-altitude quadcopters.

### 7. FoundLoc: Vision-based Onboard Aerial Localization in the Wild (CMU, 2023)

Paper: [arXiv](https://arxiv.org/abs/2310.16299)  
Project page: [AirLab page](https://theairlab.org/foundloc/)

Why it matters:

- It uses a nadir-facing camera, an IMU, VIO, and pre-existing satellite imagery.
- The abstract says it uses both VIO and visual place recognition with a foundation model.
- It reports average localization accuracy within 20 m, with minimum error below 1 m, without assuming known initial position.

Public code status:

- I found a paper and project pages.
- I did not find a usable public research repository for the localization algorithm itself.

Relevance to your use case:

- High conceptually.
- Especially relevant because it combines a strong absolute correction method with VIO, which is close to what you would want operationally.

Takeaway:

- A strong modern reference for "VIO plus overhead-image localization."
- Useful as a design target, but not currently a convenient codebase to start from.

### 8. Vision-Based UAV Self-Positioning in Low-Altitude Urban Environments / DenseUAV (TIP 2024)

Paper: [arXiv](https://arxiv.org/abs/2201.09201)  
Code and dataset: [Dmmm1997/DenseUAV](https://github.com/Dmmm1997/DenseUAV)

Why it matters:

- It is a genuine low-altitude UAV-to-satellite benchmark with public code and data.
- The paper states DenseUAV is a public dataset for UAV self-positioning in low-altitude urban settings.
- It contains over 27K UAV-view and satellite-view images from 14 university campuses.

What it mainly studies:

- Retrieval and representation learning.
- The reported metrics are retrieval-style metrics such as Recall@1 and SDM@1.

Relevance to your use case:

- Medium.
- Very useful for learning good global or semi-global descriptors.
- Less useful as a complete localization answer because your real problem is precise metric registration inside a small prior window, not only retrieval.

Takeaway:

- Good training and benchmarking resource for coarse localization.
- Not enough by itself for precise frame-to-map alignment.

### 9. UAV-VisLoc: A Large-scale Dataset for UAV Visual Localization (2024)

Paper: [arXiv](https://arxiv.org/abs/2405.11936)  
Dataset repo: [IntelliSensing/UAV-VisLoc](https://github.com/IntelliSensing/UAV-VisLoc)

Why it matters:

- It is explicitly about matching ground-down UAV images to ortho satellite maps.
- The dataset includes 6,742 drone images and 11 satellite maps.
- It includes metadata such as latitude, longitude, altitude, and capture date.

Relevance to your use case:

- High.
- It is one of the best directly relevant public datasets because it is ground-down and UAV-specific.
- It is a dataset, not a mature open localization system.

Takeaway:

- Strong candidate for initial evaluation and fine-tuning.
- Especially useful if you want to test map registration on real nadir imagery.

### 10. Leveraging Map Retrieval and Alignment for Robust UAV Visual Geo-Localization (IEEE TIM 2024)

Paper summary: [CoLab metadata page](https://colab.ws/articles/10.1109%2Ftim.2024.3418097)  
Code: [hmf21/UAVLocalization](https://github.com/hmf21/UAVLocalization)

Why it matters:

- This paper is very close to the standard modern pipeline: deep-feature retrieval for initialization, then image registration for sequential localization, plus relocalization when tracking fails.
- The public repo describes exactly that retrieval-plus-alignment workflow.

Public-code note:

- The repo is public, but the README says only the main files are provided and that related files will be released later.
- In practice, treat it as partially open rather than a complete drop-in system.

Relevance to your use case:

- High architecturally.
- Since you already have a 100 m prior, you would likely keep the alignment part and make the retrieval part a fallback or recovery mode.

Takeaway:

- One of the better public references for how to structure a robust sequential system.
- More useful for architecture than for immediate reproduction.

### 11. AerialVL: A Dataset, Baseline and Algorithm Framework for Aerial-Based Visual Localization With Reference Map (RA-L 2024)

Paper summary: [UDel open-access metadata page](https://udspace.udel.edu/items/338c0b7c-993b-476c-a095-6820c6f1c031)  
Dataset repo: [hmf21/AerialVL](https://github.com/hmf21/AerialVL)

Why it matters:

- It is a public aerial visual localization dataset and framework built around reference maps.
- The dataset repo describes sequence-based localization data and visual place recognition data.
- It includes 11 image sequences over about 70 km of flight trajectories, plus map tiles and training data.

Relevance to your use case:

- Medium to high.
- Useful for sequential evaluation and for a modular pipeline mindset.
- Less directly matched than UAV-VisLoc and AnyVisLoc because it mixes broader aerial-localization settings.

Takeaway:

- Good dataset and framework reference.
- Useful as a bridge between map retrieval and sequential alignment.

### 12. GNSS-denied geolocalization of UAVs using terrain-weighted constraint optimization (2024)

Paper: [ScienceDirect page](https://www.sciencedirect.com/science/article/pii/S1569843224006332)  
Code: [YFS90/GNSS-Denied-UAV-Geolocalization](https://github.com/YFS90/GNSS-Denied-UAV-Geolocalization)

Why it matters:

- It combines image matching, visual odometry, DEM/terrain constraints, and optimization.
- It is one of the stronger public examples of a system-level localization stack rather than a single matching paper.

Important mismatch with your use case:

- The abstract explicitly says it handles 150-1500 m scenarios and does not require a top-down camera.
- That makes it more general, but also less directly representative of 10-100 m downward-looking quadcopters.

Takeaway:

- The terrain-constraint idea is useful if you later add DEM or DSM data.
- The altitude regime is too different to treat it as your main reference.

### 13. Exploring the best way for UAV visual localization under Low-altitude Multi-view Observation Condition: a Benchmark / AnyVisLoc (2025, updated 2026)

Paper: [arXiv](https://arxiv.org/abs/2503.10692)  
Code and demo: [UAV-AVL/Benchmark](https://github.com/UAV-AVL/Benchmark)

Why it matters:

- This is the closest recent public benchmark to your regime.
- The paper states the AnyVisLoc dataset contains 18,000 images with aerial photogrammetry maps and historical satellite maps.
- The benchmark baseline achieves 74.1% localization accuracy within 5 m under low-altitude, multi-view conditions.
- The repo describes a baseline using CAMP for image retrieval and RoMa for pixel-level matching.

Important nuance:

- The repo describes the benchmark as low-altitude, but its released dataset description says 30-300 m altitude and 20-90 degree pitch angles.
- That means it is close to your 10-100 m range, but not a perfect match to the lowest part of your envelope and not strictly nadir-only.

Why this still matters for you:

- Their setup is harder than yours in one key way: they solve stronger viewpoint changes and often weaker priors.
- Their setup is easier than yours in one key way: some sequences operate above your hardest 10-20 m regime.

Takeaway:

- Probably the single most important current public benchmark to read first.
- It strongly supports using modern matching methods rather than older handcrafted pipelines.
- Since you have a 100 m prior and a downward-facing camera, you can simplify their architecture.

### 14. A Hierarchical Absolute Visual Localization System for Low-Altitude Drones in GNSS-Denied Environments (2025)

Paper: [MDPI / Remote Sensing](https://www.mdpi.com/2072-4292/17/20/3470)

Why it matters:

- It explicitly proposes a hierarchical coarse-to-fine localization framework.
- It combines retrieval, registration, IMU-based correction, and sliding-window map updates.
- The paper argues that after initialization, later frames should no longer perform global retrieval and should instead localize inside a constrained local sub-map.

Important mismatch:

- Their own dataset section uses 350 m and 500 m flight altitudes.
- So the architecture is relevant, but the operating regime is not.

Takeaway:

- Strong support for the exact systems idea you likely want.
- Do not over-trust its quantitative results for 10-100 m flight.

### 15. Beyond Matching to Tiles: Bridging Unaligned Aerial and Satellite Views for Vision-Only UAV Navigation / Bearing-UAV (2026)

Paper page: [Hugging Face summary with arXiv link](https://huggingface.co/papers/2603.22153)

Why it matters:

- It attacks a real weakness of many retrieval methods: the tile-matching formulation itself.
- The claimed direction is to jointly predict location and heading from neighboring map features rather than selecting one discrete tile.

Public-code status:

- The paper says code and dataset will be made public.
- I did not verify a stable, mature public code release yet.

Relevance to your use case:

- Medium as a forward-looking direction.
- High conceptual value because your 100 m prior also argues against treating localization as a pure "retrieve the correct tile from a huge gallery" problem.

Takeaway:

- A good pointer to where the field is going.
- Not yet the safest base to build on.

## Public code and datasets worth using immediately

If the goal is to build a serious prototype rather than just read papers, these are the most useful public assets.

### Best public datasets for this use case

| Dataset | Why it matters | Fit to your use case |
|---|---|---|
| [UAV-VisLoc](https://github.com/IntelliSensing/UAV-VisLoc) | Ground-down UAV images matched to overhead maps; includes altitude and location metadata | High |
| [AnyVisLoc / UAV-AVL Benchmark](https://github.com/UAV-AVL/Benchmark) | Closest recent benchmark for low-altitude UAV AVL; modern baseline with CAMP + RoMa | High |
| [DenseUAV](https://github.com/Dmmm1997/DenseUAV) | Low-altitude urban UAV-to-satellite dataset with strong retrieval baselines | Medium |
| [AerialVL](https://github.com/hmf21/AerialVL) | Sequence-based aerial localization dataset plus map database | Medium |

### Best public codebases for full or partial pipelines

| Repo | What it gives you | Notes |
|---|---|---|
| [hmgoforth/gps-denied-uav-localization](https://github.com/hmgoforth/gps-denied-uav-localization) | Older but directly relevant frame-to-map alignment pipeline | Good conceptual baseline |
| [TIERS/wildnav](https://github.com/TIERS/wildnav) | End-to-end UAV-to-satellite matching with georeferenced map tiles | Best as a scaffold, not as final matcher |
| [TerboucheHacene/visual_localization](https://github.com/TerboucheHacene/visual_localization) | Cleaner scaffold around the WildNav-style pipeline with tile downloading and query processing | Promising scaffold, but not a benchmarked final system |
| [hmf21/UAVLocalization](https://github.com/hmf21/UAVLocalization) | Retrieval plus sequential alignment plus relocalization architecture | Public but appears partial |
| [UAV-AVL/Benchmark](https://github.com/UAV-AVL/Benchmark) | Low-altitude benchmark pipeline with CAMP + RoMa baseline | Very relevant; dataset release is still partial |
| [aalto-intelligent-robotics/sivl](https://github.com/aalto-intelligent-robotics/sivl) | Season-invariant matching code | Checkpoint unavailable, retraining needed |
| [YFS90/GNSS-Denied-UAV-Geolocalization](https://github.com/YFS90/GNSS-Denied-UAV-Geolocalization) | System-level VO plus terrain constraints | Altitude regime is not a close match |

### Best public building blocks

| Repo | Use |
|---|---|
| [RoMa](https://github.com/Parskatt/RoMa) | Dense matcher for robust local registration |
| [EfficientLoFTR](https://github.com/zju3dv/efficientloftr) | Faster dense/semi-dense matcher |
| [LightGlue](https://github.com/cvg/LightGlue) | Fast sparse matching backend |
| [Glue Factory](https://github.com/cvg/glue-factory) | Training and fine-tuning local feature pipelines |
| [Hierarchical-Localization](https://github.com/cvg/Hierarchical-Localization) | General retrieval plus matching toolbox |

### Important code caveats

- `WildNav` and `visual_localization` are useful, but both are built around the SuperPoint plus SuperGlue family. The official Magic Leap SuperPoint and SuperGlue releases are for non-commercial research use only, so those repos are fine for research prototypes but not automatically clean for product use.
- `sivl` has public training code, but its pretrained checkpoint is no longer available. Plan on retraining if you want to borrow that approach.
- `UAVLocalization` is public, but the authors state that only the main files are released. Treat it as a reference implementation, not as a finished production base.
- `UAV-AVL/Benchmark` is highly relevant, but the repo itself says the demo and a partial dataset release came first and that full release is staged. It is excellent for studying the pipeline, but not yet the complete benchmark package one would want in a mature research stack.

## What existing systems actually do

Across papers and codebases, the field has largely converged on four reusable ideas.

### A. Retrieval first, then registration

This is the default pattern when the UAV may be anywhere in a large map:

- compute a global descriptor from the UAV image
- retrieve a handful of candidate map tiles
- run local matching or registration only on those tiles
- use geometry to recover the final pose

Examples:

- DenseUAV and DRL for the retrieval side
- UAVLocalization for retrieval plus alignment
- AnyVisLoc baseline with CAMP plus RoMa

Why you should only partly copy this:

- You already have a 100 m prior.
- That means global retrieval should be a recovery mode, not the normal per-frame path.

### B. Direct image registration inside a local map crop

This is the part of the literature that is most relevant for you.

Examples:

- Goforth and Lucey 2019
- WildNav
- UAVLocalization alignment stage
- AnyVisLoc matching stage

Why this fits:

- If the search area is already small, it is better to spend compute on precise alignment than on global retrieval.
- Server-side compute makes dense matching feasible.

### C. Temporal filtering and motion fusion

Examples:

- Particle filter or Monte Carlo localization in the Aalto work and in Jurevicius et al.
- VIO plus absolute corrections in FoundLoc
- Sliding-window optimization in the terrain-weighted and hierarchical systems

Why this matters:

- Absolute image matches will fail intermittently.
- Dead reckoning drifts.
- Combining the two is not optional if the system is meant to run continuously.

### D. Robustness tricks

The recurring tricks are:

- seasonal or temporal invariance in descriptors
- IMU-based rotation correction
- map updates inside a sliding window
- semantics or structural priors to prefer stable map features
- using DEM/DSM when terrain matters

## Methods that are most likely best for your exact use case

### Best theoretical main path: local dense registration plus temporal filtering

This is the strongest fit to your assumptions.

Recommended online pipeline:

1. Use dead reckoning to crop a local overhead region around the predicted position.
2. Build a small multi-scale set of candidate crops around the predicted GSD.
3. Match the current UAV frame against those crops using a dense matcher.
4. Use robust geometry fitting to estimate a 2D transform or homography.
5. Convert the transform to a geolocation estimate and uncertainty.
6. Fuse that estimate over time with a particle filter or factor graph.
7. Only trigger a wider retrieval step if confidence collapses or tracking is lost.

Why this is the best fit:

- Your 100 m prior removes most of the global-search burden.
- Your downward-facing camera reduces viewpoint complexity.
- Remote compute lets you use heavier dense matchers.

### Best matcher family: dense or semi-dense learned matchers

My ranking for your use case:

1. [RoMa](https://github.com/Parskatt/RoMa)
2. [EfficientLoFTR](https://github.com/zju3dv/efficientloftr)
3. [LightGlue](https://github.com/cvg/LightGlue) plus a commercially safe detector such as DISK or ALIKED

Why dense matching is attractive here:

- Low-altitude frames often contain large textureless regions, where keypoint-only methods can fail.
- Satellite/UAV domain shift is hard.
- Server-side inference can absorb the runtime cost.

Why sparse matching is still useful:

- It is faster.
- It is easier to debug.
- It can be a fallback when dense matching becomes too expensive.

### Best temporal estimator: particle filter first, factor graph later

Start with a particle filter.

Why:

- It naturally handles uncertainty in the 100 m prior.
- It can use match score, inlier count, and geometric residual as measurement likelihood.
- It handles ambiguous scenes better than a single Gaussian estimate.

Later, once the perception stack is stable, a factor graph or tightly coupled VIO plus absolute corrections can outperform it in long flights. But for the first serious prototype, particle filtering is the simpler and more honest design.

### Best map source: high-resolution orthophotos if possible, true satellite imagery only if high quality

This is the most important practical point in the whole document.

Many papers casually say "satellite imagery" when what really matters is overhead image resolution and recency. For 10-100 m quadcopter flight, image GSD dominates.

Practical ranking:

1. recent high-resolution orthophotos or aerial imagery
2. very high resolution commercial satellite or map imagery
3. medium-resolution satellite imagery

Why:

- At 10-20 m AGL, the UAV frame covers a very small ground footprint.
- If the overhead map is too coarse, the local image simply will not contain enough stable structure at matching scale.

This is also consistent with the AnyVisLoc benchmark design, which explicitly includes both aerial photogrammetry maps and satellite maps and treats aerial maps as the higher-accuracy option.

### Best use of retrieval: fallback, recovery, and initialization only

Because you already have a 100 m prior, a full retrieval stack should not be the default per-frame path.

Recommended use:

- first frame, if the dead-reckoning prior is weak
- recovery after tracking failure
- periodic sanity check over a wider area

Good retrieval candidates:

- DenseUAV-style learned descriptors
- DINOv2 or AnyLoc-style features
- CAMP, if you want to stay close to the AnyVisLoc benchmark

## What I would not recommend as the main method

### 1. Pure global retrieval without geometric refinement

Why not:

- It gives coarse tile-level localization, not precise metric positioning.
- It wastes compute because you already have a local prior.

### 2. End-to-end coordinate regression

Why not:

- Hard to trust.
- Hard to debug.
- Usually brittle to map updates, seasonal changes, and camera changes.

### 3. Classical ORB/SIFT-only pipelines as the main solution

Why not:

- They are still useful baselines.
- But the literature and recent benchmarks strongly favor learned matchers in the presence of season, viewpoint, and modality gaps.

Use them as:

- sanity-check baselines
- lightweight fallback
- geometric consistency checks

### 4. Overhead-only retrieval benchmarks as the main research guide

Examples:

- University-1652
- FSRA-style UAV-view geo-localization benchmarks

Why not:

- They are useful for coarse retrieval research.
- They do not directly answer the question of precise alignment inside a 100 m prior window at 10-100 m altitude.

## Honest feasibility assessment for your operating envelope

### Where the literature suggests this is feasible

- 30-100 m altitude
- urban or suburban scenes
- agricultural areas with clear field boundaries, roads, irrigation patterns, or buildings
- recent overhead imagery
- known camera intrinsics or at least stable FOV and altitude estimates

### Where the literature suggests this is still weak

- 10-20 m altitude over homogeneous terrain
- forest canopy
- water
- sand or desert with weak persistent features
- heavy seasonal mismatch
- snow/no-snow mismatch
- very outdated overhead imagery

### "All cameras should work" is not realistic without qualification

A robust system can support many cameras, but not literally arbitrary cameras with no adaptation.

To generalize across cameras, the system should know or estimate:

- camera intrinsics
- approximate FOV
- image resolution
- altitude or GSD range

Without that, the scale ambiguity becomes much harder, especially at low altitude.

## Most useful concrete recommendation for this project

If I had to choose one technical direction for a first serious prototype for this project, it would be this:

1. Use [UAV-VisLoc](https://github.com/IntelliSensing/UAV-VisLoc) and [AnyVisLoc / UAV-AVL Benchmark](https://github.com/UAV-AVL/Benchmark) as the first two public evaluation datasets.
2. Build around [RoMa](https://github.com/Parskatt/RoMa) or [EfficientLoFTR](https://github.com/zju3dv/efficientloftr) for local frame-to-map matching.
3. Use the 100 m dead-reckoning prior to crop a local search window and avoid full-map retrieval in the normal path.
4. Add a particle filter over time, with dead reckoning as the motion model and alignment score as the observation model.
5. Keep a wider retrieval module only for startup and failure recovery.
6. If possible, use the highest-resolution overhead imagery available and maintain multiple dates per area.

This recommendation is not just "what sounds good." It is the point where the most relevant threads in the literature overlap:

- Goforth: local alignment matters
- Jurevicius / Kinnari: particle filtering is natural for map-relative localization
- FoundLoc: VIO plus absolute correction is operationally sensible
- UAVLocalization / AerialVL: retrieval plus sequential alignment is a good system architecture
- AnyVisLoc: modern low-altitude pipelines are built from strong matching modules, and RoMa is a serious reference point

## Practical research priorities if you continue after this document

### Priority 1: confirm the imagery assumptions

The largest hidden variable is not the network, it is the map quality:

- overhead image GSD
- recency
- seasonal mismatch
- whether you truly mean satellite imagery only, or any overhead orthorectified reference imagery

### Priority 2: test the floor of the altitude range early

Do not wait to discover later that 10-20 m is the hard regime. Test it early.

### Priority 3: benchmark on both structured and weak-texture scenes

You asked for all environments. The open literature does not support one method working equally well across all of them. Measure:

- urban
- suburban
- farmland
- mountain
- forest canopy
- water

### Priority 4: quantify when retrieval is unnecessary

Because your prior is strong, an important engineering question is:

- how often does local alignment inside the prior window work by itself?

If the answer is "most frames," then the whole system gets simpler.

## Short answers to your original questions

### Has anyone done anything like this before?

Yes. Multiple papers since at least 2019 match UAV imagery to overhead maps for GNSS-denied localization. The closest lines of work are Goforth and Lucey 2019, the Aalto season-invariant localization papers, WildNav, FoundLoc, UAVLocalization, and AnyVisLoc.

### How did they do it?

Usually with some combination of:

- retrieval or prior-based map crop selection
- UAV-to-map image matching or registration
- geometry fitting
- temporal filtering with VO, VIO, particle filters, or sliding-window optimization

### Is any code public?

Yes, but the public-code situation is mixed:

- strong public code: WildNav, DenseUAV, DRL, UAV-AVL Benchmark, RoMa, EfficientLoFTR, LightGlue, SIVL
- partial or incomplete public code: UAVLocalization
- paper/project page but no clearly usable algorithm repo found by me: FoundLoc
- public code but weak project maturity for product use: VisionUAV-Navigation

### What would be the best theoretical methods for this use case?

Best answer:

- local overhead crop from the 100 m prior
- dense learned frame-to-map matching
- robust geometric pose fit
- temporal fusion with a particle filter or factor graph
- retrieval only as initialization and recovery

## Source list

### Papers and project pages

- [GPS-Denied UAV Localization using Pre-existing Satellite Imagery](https://publications.ri.cmu.edu/gps-denied-uav-localization-using-pre-existing-satellite-imagery)
- [Robust GNSS Denied Localization for UAV Using Particle Filter and Visual Odometry](https://arxiv.org/abs/1910.12121)
- [GNSS-denied geolocalization of UAVs by visual matching of onboard camera images with orthophotos](https://research.aalto.fi/en/publications/gnss-denied-geolocalization-of-uavs-by-visual-matching-of-onboard)
- [Season-Invariant GNSS-Denied Visual Localization for UAVs](https://research.aalto.fi/en/publications/season-invariant-gnss-denied-visual-localization-for-uavs/)
- [LSVL: Large-scale season-invariant visual localization for UAVs](https://arxiv.org/abs/2212.03581)
- [Vision-based GNSS-Free Localization for UAVs in the Wild](https://arxiv.org/abs/2210.09727)
- [FoundLoc: Vision-based Onboard Aerial Localization in the Wild](https://arxiv.org/abs/2310.16299)
- [Vision-Based UAV Self-Positioning in Low-Altitude Urban Environments](https://arxiv.org/abs/2201.09201)
- [UAV-VisLoc: A Large-scale Dataset for UAV Visual Localization](https://arxiv.org/abs/2405.11936)
- [Leveraging Map Retrieval and Alignment for Robust UAV Visual Geo-Localization](https://colab.ws/articles/10.1109%2Ftim.2024.3418097)
- [AerialVL: A Dataset, Baseline and Algorithm Framework for Aerial-Based Visual Localization With Reference Map](https://udspace.udel.edu/items/338c0b7c-993b-476c-a095-6820c6f1c031)
- [GNSS-denied geolocalization of UAVs using terrain-weighted constraint optimization](https://www.sciencedirect.com/science/article/pii/S1569843224006332)
- [Exploring the best way for UAV visual localization under Low-altitude Multi-view Observation Condition: a Benchmark](https://arxiv.org/abs/2503.10692)
- [A Hierarchical Absolute Visual Localization System for Low-Altitude Drones in GNSS-Denied Environments](https://www.mdpi.com/2072-4292/17/20/3470)
- [Beyond Matching to Tiles: Bridging Unaligned Aerial and Satellite Views for Vision-Only UAV Navigation](https://huggingface.co/papers/2603.22153)

### Public code and datasets

- [hmgoforth/gps-denied-uav-localization](https://github.com/hmgoforth/gps-denied-uav-localization)
- [TIERS/wildnav](https://github.com/TIERS/wildnav)
- [TerboucheHacene/visual_localization](https://github.com/TerboucheHacene/visual_localization)
- [aalto-intelligent-robotics/sivl](https://github.com/aalto-intelligent-robotics/sivl)
- [Dmmm1997/DenseUAV](https://github.com/Dmmm1997/DenseUAV)
- [Dmmm1997/DRL](https://github.com/Dmmm1997/DRL)
- [IntelliSensing/UAV-VisLoc](https://github.com/IntelliSensing/UAV-VisLoc)
- [hmf21/UAVLocalization](https://github.com/hmf21/UAVLocalization)
- [hmf21/AerialVL](https://github.com/hmf21/AerialVL)
- [YFS90/GNSS-Denied-UAV-Geolocalization](https://github.com/YFS90/GNSS-Denied-UAV-Geolocalization)
- [UAV-AVL/Benchmark](https://github.com/UAV-AVL/Benchmark)
- [Parskatt/RoMa](https://github.com/Parskatt/RoMa)
- [zju3dv/efficientloftr](https://github.com/zju3dv/efficientloftr)
- [cvg/LightGlue](https://github.com/cvg/LightGlue)
- [cvg/glue-factory](https://github.com/cvg/glue-factory)
- [cvg/Hierarchical-Localization](https://github.com/cvg/Hierarchical-Localization)
