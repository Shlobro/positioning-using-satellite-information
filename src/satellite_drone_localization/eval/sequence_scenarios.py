"""Scenario metadata for sequence-search reports."""

from __future__ import annotations


def describe_scenario(scenario_name: str) -> str:
    """Return the human-readable scenario description."""
    if scenario_name == "seed_only":
        return "Use frame-0 truth as the only seed and grow the search radius over total elapsed time."
    if scenario_name == "oracle_previous_truth":
        return "Upper-bound ceiling that recenters on the previous frame truth and grows radius only over per-frame delta time."
    if scenario_name == "recursive_oracle_estimate":
        return (
            "Stateful prior loop that recenters on the previous accepted estimate "
            "(oracle stand-in uses hidden truth) and carries a configurable post-update confidence radius."
        )
    if scenario_name == "recursive_placeholder_matcher":
        return (
            "Stateful prior loop that feeds back a deterministic truth-anchored placeholder "
            "measurement instead of a perfect oracle update, so drift can be measured before a real matcher exists."
        )
    if scenario_name == "recursive_image_baseline_matcher":
        return (
            "Stateful prior loop that feeds back a simple real image-template baseline "
            "measured inside the calibrated satellite crop, so recursive tracking can be compared against placeholder and oracle scenarios."
        )
    if scenario_name == "recursive_image_map_constrained_matcher":
        return (
            "Stateful image-baseline loop that shifts the search center back into the calibrated map bounds when possible, "
            "so map-boundary persistence can be measured without changing the original raster baseline."
        )
    if scenario_name == "recursive_classical_matcher":
        return (
            "Stateful prior loop that feeds back a classical local-feature matcher "
            "inside the calibrated satellite crop, so a stronger non-neural baseline can be compared against the raster baseline and oracle ceilings."
        )
    if scenario_name == "recursive_roma_matcher":
        return (
            "Stateful prior loop that feeds back a pretrained RoMa matcher "
            "inside the calibrated satellite crop, so the first neural baseline can be compared directly against the classical and raster baselines."
        )
    if scenario_name == "recursive_roma_map_constrained_matcher":
        return (
            "Stateful RoMa loop that shifts the search center back into the calibrated map bounds when possible, "
            "so the neural benchmark can test whether boundary-aware bootstrap policy improves persistence."
        )
    if scenario_name == "recursive_roma_velocity_likelihood_matcher":
        return (
            "Stateful RoMa loop that predicts the next prior from the previous accepted velocity and rejects accepted "
            "updates with low combined motion and matcher-evidence likelihood."
        )
    if scenario_name == "recursive_loftr_map_constrained_matcher":
        return (
            "Stateful EfficientLoFTR-style loop that reuses the map-constrained crop policy and temporal gate, "
            "so a non-RoMa dense matcher family can be measured against the current neural baseline."
        )
    raise ValueError(f"unsupported scenario_name '{scenario_name}'")
