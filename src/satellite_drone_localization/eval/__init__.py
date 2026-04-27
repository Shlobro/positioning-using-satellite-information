"""Offline evaluation helpers for sequence-localization experiments."""

from .sequence_search import (
    SequenceScenarioReport,
    SequenceSearchArtifacts,
    SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER,
    SCENARIO_RECURSIVE_ORACLE_ESTIMATE,
    SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER,
    build_sequence_search_artifacts,
    write_sequence_search_debug_svg,
    write_sequence_search_summary,
)

__all__ = [
    "SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER",
    "SCENARIO_RECURSIVE_ORACLE_ESTIMATE",
    "SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER",
    "SequenceScenarioReport",
    "SequenceSearchArtifacts",
    "build_sequence_search_artifacts",
    "write_sequence_search_debug_svg",
    "write_sequence_search_summary",
]
