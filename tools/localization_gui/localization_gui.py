"""Localization GUI — interactive demo and research tool.

Run from the repository root:

    python tools/localization_gui/localization_gui.py

The window has three regions:
- left sidebar: tile picker, input mode, query picker, prior controls, pipeline picker, run button
- center: pan/zoom satellite map with markers, search-radius circle, heatmap, query overlay
- bottom: numeric result strip with predicted lat/lon, error, runtime, and a query thumbnail
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

# Allow `from satellite_drone_localization...` imports when launched directly
# from the tools/ folder.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6 import QtCore, QtGui, QtWidgets

from localization_gui.controls_panel import ControlsPanel
from localization_gui.map_view import MapView
from localization_gui.pipeline_runner import (
    RunRequest,
    RunResult,
    execute_run_request,
    list_pipelines_for_input,
    load_calibrated_tile,
)
from localization_gui.result_panel import ResultPanel
from localization_gui.single_image_input import load_single_image_packet


WINDOW_TITLE = "Drone Localization Studio"
WINDOW_BG = "#0d0d1a"


class _LocalizationRunWorker(QtCore.QObject):
    """Execute one localization request away from the UI thread."""

    finished = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, request: RunRequest) -> None:
        super().__init__()
        self._request = request

    @QtCore.pyqtSlot()
    def run(self) -> None:
        try:
            result = execute_run_request(self._request)
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1500, 900)
        self.setStyleSheet(f"QMainWindow {{ background-color: {WINDOW_BG}; }}")

        self._georeference = None
        self._tile_path: Path | None = None
        self._single_packet = None
        self._sequence_replay_path: Path | None = None
        self._last_result: RunResult | None = None
        self._run_in_progress = False
        self._run_thread: QtCore.QThread | None = None
        self._run_worker: _LocalizationRunWorker | None = None

        self._controls = ControlsPanel()
        self._map_view = MapView()
        self._result_panel = ResultPanel()

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        outer_layout = QtWidgets.QVBoxLayout(central)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        body = QtWidgets.QWidget()
        body_layout = QtWidgets.QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(330)
        scroll.setWidget(self._controls)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        body_layout.addWidget(scroll)
        body_layout.addWidget(self._map_view, 1)

        outer_layout.addWidget(body, 1)
        outer_layout.addWidget(self._result_panel)

        status_bar = self.statusBar()
        status_bar.setStyleSheet("background-color: #0f3460; color: #eaeaea;")
        status_bar.showMessage("Pick a satellite tile to begin.")

        self._controls.tile_picked.connect(self._on_tile_picked)
        self._controls.input_mode_changed.connect(self._on_input_mode_changed)
        self._controls.query_picked.connect(self._on_query_picked)
        self._controls.prior_latlon_submitted.connect(self._on_prior_latlon_submitted)
        self._controls.radius_changed.connect(self._on_radius_changed)
        self._controls.pipeline_changed.connect(self._on_pipeline_changed)
        self._controls.run_requested.connect(self._on_run_requested)
        self._controls.heatmap_toggled.connect(self._on_heatmap_toggled)
        self._controls.query_overlay_toggled.connect(self._on_query_overlay_toggled)
        self._map_view.prior_changed.connect(self._on_prior_from_map)
        self._result_panel.frame_index_changed.connect(self._on_frame_index_changed)

        self._controls.set_pipeline_choices(list_pipelines_for_input("single"))

    def _on_tile_picked(self, path: Path) -> None:
        try:
            georeference = load_calibrated_tile(path)
        except Exception as exc:
            self._show_error(f"Could not load tile: {exc}")
            return
        self._tile_path = path
        self._georeference = georeference
        self._map_view.load_tile(path, georeference)
        self._controls.set_tile_label(
            f"{path.name}\n{georeference.image_width_px}×{georeference.image_height_px} px"
        )
        center_x = georeference.image_width_px / 2.0
        center_y = georeference.image_height_px / 2.0
        latitude_deg, longitude_deg = georeference.pixel_to_latlon(center_x, center_y)
        self._map_view.set_prior(center_x, center_y, self._controls.current_radius_m())
        self._controls.set_latlon_text(latitude_deg, longitude_deg)
        self.statusBar().showMessage(f"Loaded tile: {path.name}")
        self._refresh_run_enabled()

    def _on_input_mode_changed(self, mode: str) -> None:
        self._controls.set_pipeline_choices(list_pipelines_for_input(mode))
        self._controls.set_query_label("(no query loaded)")
        self._single_packet = None
        self._sequence_replay_path = None
        self._refresh_run_enabled()

    def _on_query_picked(self, path: Path) -> None:
        mode = self._controls.current_input_mode()
        if mode == "single":
            try:
                packet = load_single_image_packet(path)
            except Exception as exc:
                self._show_error(f"Single-image input rejected: {exc}")
                return
            self._single_packet = packet
            frame = packet.session.frames[0]
            self._controls.set_query_label(
                f"{path.name}\nlat {frame.latitude_deg:.6f}, lon {frame.longitude_deg:.6f}\n"
                f"alt {frame.altitude_m:.1f}m, hdg {frame.heading_deg:.1f}°"
            )
            self._result_panel.show_query_thumbnail(path)
            self.statusBar().showMessage(f"Loaded single-image input: {path.name}")
        else:
            try:
                from satellite_drone_localization.packet_replay import load_replay_session

                session = load_replay_session(path)
            except Exception as exc:
                self._show_error(f"Replay rejected: {exc}")
                return
            self._sequence_replay_path = path
            self._controls.set_query_label(
                f"{path.name}\n{len(session.frames)} frames"
            )
            self._result_panel.show_query_thumbnail(session.frames[0].image_path)
            self.statusBar().showMessage(f"Loaded replay: {path.name}")
        self._refresh_run_enabled()

    def _on_prior_latlon_submitted(self, latitude_deg: float, longitude_deg: float) -> None:
        if self._georeference is None:
            return
        self._map_view.set_prior_from_latlon(
            latitude_deg, longitude_deg, self._controls.current_radius_m()
        )

    def _on_prior_from_map(self, latitude_deg: float, longitude_deg: float) -> None:
        self._controls.set_latlon_text(latitude_deg, longitude_deg)

    def _on_radius_changed(self, radius_m: float) -> None:
        if self._georeference is None:
            return
        prior = self._map_view._prior  # private read; same package, intentional
        if prior is not None:
            self._map_view.set_prior(prior.pixel_x, prior.pixel_y, radius_m)

    def _on_pipeline_changed(self, _: str) -> None:
        self._refresh_run_enabled()

    def _on_run_requested(self) -> None:
        if self._run_in_progress:
            return
        if self._georeference is None:
            return
        prior = self._map_view._prior
        if prior is None:
            self._show_error("Set a prior point on the map (or via lat/lon) before running.")
            return
        prior_latitude_deg, prior_longitude_deg = self._georeference.pixel_to_latlon(
            prior.pixel_x, prior.pixel_y
        )
        radius_m = self._controls.current_radius_m()
        pipeline = self._controls.current_pipeline()
        mode = self._controls.current_input_mode()
        if mode == "single":
            if self._single_packet is None:
                self._show_error("Pick a single-image query first.")
                return
            request = RunRequest(
                input_mode="single",
                pipeline=pipeline,
                georeference=self._georeference,
                session=self._single_packet.session,
                prior_latitude_deg=prior_latitude_deg,
                prior_longitude_deg=prior_longitude_deg,
                prior_search_radius_m=radius_m,
                roma_matcher_factory=_roma_matcher_factory_or_none(),
            )
        else:
            if self._sequence_replay_path is None:
                self._show_error("Pick a replay file first.")
                return
            request = RunRequest(
                input_mode="sequence",
                pipeline=pipeline,
                georeference=self._georeference,
                replay_path=self._sequence_replay_path,
                roma_matcher_factory=_roma_matcher_factory_or_none(),
            )
        self._start_run(request)

    def _render_result_for_current_frame(self) -> None:
        frame = self._result_panel.current_frame()
        if frame is None:
            self._map_view.set_prediction(None)
            return
        self._map_view.set_prediction(frame)
        if self._last_result is not None:
            self._map_view.set_heatmap(
                self._last_result.heatmap,
                self._last_result.heatmap_origin_pixel,
                self._last_result.heatmap_pixel_size,
                self._controls.heatmap_visible(),
            )
        self._map_view.set_query_overlay(frame, self._controls.query_overlay_visible())

    def _on_frame_index_changed(self, _: int) -> None:
        self._render_result_for_current_frame()

    def _on_heatmap_toggled(self, visible: bool) -> None:
        self._map_view.set_heatmap_visible(visible)

    def _on_query_overlay_toggled(self, visible: bool) -> None:
        frame = self._result_panel.current_frame()
        self._map_view.set_query_overlay(frame, visible)

    def _refresh_run_enabled(self) -> None:
        ready = (
            not self._run_in_progress
            and
            self._georeference is not None
            and self._controls.current_pipeline() != ""
            and (
                (self._controls.current_input_mode() == "single" and self._single_packet is not None)
                or (
                    self._controls.current_input_mode() == "sequence"
                    and self._sequence_replay_path is not None
                )
            )
        )
        self._controls.set_run_enabled(ready)

    def _show_error(self, message: str) -> None:
        QtWidgets.QMessageBox.critical(self, "Error", message)

    def _start_run(self, request: RunRequest) -> None:
        pipeline = request.pipeline
        self._set_run_in_progress(True, f"Running {pipeline}…")
        self._run_thread = QtCore.QThread(self)
        self._run_worker = _LocalizationRunWorker(request)
        self._run_worker.moveToThread(self._run_thread)
        self._run_thread.started.connect(self._run_worker.run)
        self._run_worker.finished.connect(self._on_run_finished)
        self._run_worker.failed.connect(self._on_run_failed)
        self._run_worker.finished.connect(self._run_thread.quit)
        self._run_worker.failed.connect(self._run_thread.quit)
        self._run_worker.finished.connect(self._run_worker.deleteLater)
        self._run_worker.failed.connect(self._run_worker.deleteLater)
        self._run_thread.finished.connect(self._on_run_thread_finished)
        self._run_thread.finished.connect(self._run_thread.deleteLater)
        self._run_thread.start()

    def _on_run_finished(self, result: RunResult) -> None:
        self._last_result = result
        self._result_panel.show_run_result(result)
        self._render_result_for_current_frame()
        self._set_run_in_progress(False)
        if result.error_message:
            self.statusBar().showMessage(f"{result.pipeline}: {result.error_message}")
        else:
            self.statusBar().showMessage(
                f"{result.pipeline} completed in {result.runtime_seconds:.2f}s "
                f"({len(result.frames)} frame(s))"
            )

    def _on_run_failed(self, message: str) -> None:
        self._set_run_in_progress(False)
        self.statusBar().showMessage("Run failed.")
        self._show_error(f"Pipeline run failed: {message}")

    def _on_run_thread_finished(self) -> None:
        self._run_thread = None
        self._run_worker = None

    def _set_run_in_progress(self, running: bool, message: str = "") -> None:
        self._run_in_progress = running
        self._controls.set_run_in_progress(running, message)
        if running:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            self.statusBar().showMessage(message or "Running localization…")
        else:
            QtWidgets.QApplication.restoreOverrideCursor()
        self._refresh_run_enabled()


def _roma_matcher_factory_or_none():
    """Return a factory that builds a RoMa matcher, or None if RoMa is unavailable.

    The factory is invoked lazily so the GUI can launch even when romatch / torch
    are not installed; only RoMa pipelines will fail.
    """
    try:
        from satellite_drone_localization.eval.matcher_roma import RoMaRegressionMatcher
    except Exception:
        return None

    def _factory(map_image_path):
        return RoMaRegressionMatcher(map_image_path)

    return _factory


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(WINDOW_BG))
    palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor("#eaeaea"))
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor("#16213e"))
    palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor("#0f3460"))
    palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor("#eaeaea"))
    palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#0f3460"))
    palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#eaeaea"))
    palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor("#e94560"))
    palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor("#0d0d1a"))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
