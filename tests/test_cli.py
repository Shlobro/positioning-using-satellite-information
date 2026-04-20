from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from satellite_drone_localization import cli


def make_repo_root() -> Path:
    base_dir = Path.cwd() / "artifacts" / "test-temp"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def test_cli_main_creates_run(monkeypatch, capsys) -> None:
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
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr("sys.argv", ["run_smoke", "--config", "configs/eval/run_000.json"])

        exit_code = cli.main()
        captured = capsys.readouterr()

        assert exit_code == 0
        assert "Created RUN-000" in captured.out
        assert (repo_root / "artifacts" / "runs" / "RUN-000" / "metrics.json").exists()
    finally:
        shutil.rmtree(repo_root, ignore_errors=True)
