from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import tempfile

from satellite_drone_localization.smoke_pipeline import run_smoke


def make_repo_root() -> Path:
    base_dir = Path.cwd() / "artifacts" / "test-temp"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def test_run_smoke_writes_required_artifacts() -> None:
    repo_root = make_repo_root()
    config_dir = repo_root / "configs" / "eval"
    try:
        config_dir.mkdir(parents=True)
        config_path = config_dir / "run_000.json"
        config_path.write_text(
            json.dumps(
                {
                    "run_id": "RUN-000",
                    "phase": "phase-0",
                    "dataset_version": "synthetic-smoke-v1",
                    "model_name": "deterministic-smoke-baseline",
                    "search_radius_m": 100,
                    "area_type": "synthetic",
                    "altitude_band": "50-60m",
                }
            ),
            encoding="utf-8",
        )

        result = run_smoke(config_path=config_path, repo_root=repo_root)

        assert result.run_directory == repo_root / "artifacts" / "runs" / "RUN-000"
        assert result.metrics_path.exists()
        assert result.predictions_path.exists()
        assert result.overlay_path.exists()
        assert (result.run_directory / "plots").is_dir()
        assert (result.run_directory / "overlays").is_dir()

        metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))
        assert metrics["run_status"] == "success"
        assert metrics["predictions_count"] == 1

        with result.predictions_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert rows[0]["localization_status"] == "ok"
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)


def test_run_smoke_writes_yaml_snapshot() -> None:
    repo_root = make_repo_root()
    config_dir = repo_root / "configs" / "eval"
    try:
        config_dir.mkdir(parents=True)
        config_path = config_dir / "run_000.json"
        config_path.write_text(
            '{"run_id": "RUN-000", "phase": "phase-0", "dataset_version": "synthetic-smoke-v1", "model_name": "deterministic-smoke-baseline"}',
            encoding="utf-8",
        )

        run_smoke(config_path=config_path, repo_root=repo_root)

        snapshot = (repo_root / "artifacts" / "runs" / "RUN-000" / "config_snapshot.yaml").read_text(encoding="utf-8")
        assert 'run_id: "RUN-000"' in snapshot
        assert 'phase: "phase-0"' in snapshot
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
