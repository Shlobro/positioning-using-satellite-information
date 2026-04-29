"""Offline evaluation helpers for sequence-localization experiments."""

from .sequence_search import (
    SCENARIO_RECURSIVE_CLASSICAL_MATCHER,
    SequenceScenarioReport,
    SequenceSearchArtifacts,
    SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER,
    SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER,
    SCENARIO_RECURSIVE_ORACLE_ESTIMATE,
    SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER,
    SCENARIO_RECURSIVE_ROMA_MATCHER,
    SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER,
    SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER,
    build_sequence_search_artifacts,
    write_sequence_search_debug_svg,
    write_sequence_search_summary,
)
from .reports.sequence_comparison import (
    DEFAULT_BASELINE_SCENARIO,
    DEFAULT_CANDIDATE_SCENARIO,
    SequenceScenarioComparison,
    ScenarioMetricSnapshot,
    compare_sequence_summary,
    write_sequence_comparison,
    write_sequence_comparison_csv,
)

__all__ = [
    "DEFAULT_BASELINE_SCENARIO",
    "DEFAULT_CANDIDATE_SCENARIO",
    "SCENARIO_RECURSIVE_CLASSICAL_MATCHER",
    "SCENARIO_RECURSIVE_IMAGE_BASELINE_MATCHER",
    "SCENARIO_RECURSIVE_IMAGE_MAP_CONSTRAINED_MATCHER",
    "SCENARIO_RECURSIVE_ORACLE_ESTIMATE",
    "SCENARIO_RECURSIVE_PLACEHOLDER_MATCHER",
    "SCENARIO_RECURSIVE_ROMA_MATCHER",
    "SCENARIO_RECURSIVE_ROMA_MAP_CONSTRAINED_MATCHER",
    "SCENARIO_RECURSIVE_ROMA_VELOCITY_LIKELIHOOD_MATCHER",
    "ScenarioMetricSnapshot",
    "SequenceScenarioComparison",
    "SequenceScenarioReport",
    "SequenceSearchArtifacts",
    "build_sequence_search_artifacts",
    "compare_sequence_summary",
    "write_sequence_comparison",
    "write_sequence_comparison_csv",
    "write_sequence_search_debug_svg",
    "write_sequence_search_summary",
]
