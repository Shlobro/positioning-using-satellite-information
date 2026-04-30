"""Result panel: shows numeric outcome and a small query preview."""

from __future__ import annotations

from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from .pipeline_runner import RunResult, FramePrediction


PANEL_BG = "#16213e"
ACCENT = "#0f3460"
HIGHLIGHT = "#e94560"
SUCCESS = "#4caf82"
TEXT = "#eaeaea"
TEXT_DIM = "#7a7a9a"


class ResultPanel(QtWidgets.QWidget):
    """Bottom result strip with predicted lat/lon, error, runtime, and a thumbnail."""

    frame_index_changed = QtCore.pyqtSignal(int)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: {PANEL_BG};
                color: {TEXT};
                font-family: 'Segoe UI', sans-serif;
            }}
            QLabel.heading {{
                color: {HIGHLIGHT};
                font-weight: 700;
                font-size: 11pt;
            }}
            QLabel.value {{
                color: {TEXT};
                font-family: Consolas, monospace;
                font-size: 11pt;
            }}
            QLabel.dim {{
                color: {TEXT_DIM};
                font-family: Consolas, monospace;
                font-size: 9pt;
            }}
            """
        )
        self._result: RunResult | None = None
        self._frame_index = 0

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(20)

        self._thumbnail = QtWidgets.QLabel()
        self._thumbnail.setFixedSize(160, 120)
        self._thumbnail.setStyleSheet(f"background-color: {ACCENT}; border-radius: 4px;")
        self._thumbnail.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._thumbnail.setText("(no query loaded)")
        layout.addWidget(self._thumbnail)

        details_layout = QtWidgets.QGridLayout()
        details_layout.setVerticalSpacing(4)
        details_layout.setHorizontalSpacing(14)
        layout.addLayout(details_layout, 1)

        self._labels: dict[str, QtWidgets.QLabel] = {}
        rows = [
            ("Pipeline", "pipeline"),
            ("Result", "outcome"),
            ("Predicted lat", "pred_lat"),
            ("Predicted lon", "pred_lon"),
            ("Error vs truth", "error"),
            ("Match score", "score"),
            ("Runtime", "runtime"),
            ("Frame", "frame"),
        ]
        for row_index, (heading, key) in enumerate(rows):
            heading_label = QtWidgets.QLabel(heading)
            heading_label.setProperty("class", "heading")
            heading_label.setStyleSheet(f"color: {HIGHLIGHT}; font-weight: 700;")
            value_label = QtWidgets.QLabel("—")
            value_label.setProperty("class", "value")
            value_label.setStyleSheet(f"color: {TEXT}; font-family: Consolas, monospace;")
            details_layout.addWidget(heading_label, row_index, 0)
            details_layout.addWidget(value_label, row_index, 1)
            self._labels[key] = value_label

        nav_layout = QtWidgets.QVBoxLayout()
        nav_layout.setSpacing(4)
        layout.addLayout(nav_layout)
        self._prev_button = QtWidgets.QPushButton("◀ prev")
        self._next_button = QtWidgets.QPushButton("next ▶")
        for button in (self._prev_button, self._next_button):
            button.setEnabled(False)
            button.setStyleSheet(
                f"background-color: {ACCENT}; color: {TEXT}; border: none; padding: 5px 10px;"
            )
        self._prev_button.clicked.connect(lambda: self._move_frame(-1))
        self._next_button.clicked.connect(lambda: self._move_frame(1))
        nav_layout.addWidget(self._prev_button)
        nav_layout.addWidget(self._next_button)

    def show_query_thumbnail(self, image_path: Path | None) -> None:
        if image_path is None or not Path(image_path).is_file():
            self._thumbnail.setText("(no query loaded)")
            self._thumbnail.setPixmap(QtGui.QPixmap())
            return
        pixmap = QtGui.QPixmap(str(image_path))
        if pixmap.isNull():
            self._thumbnail.setText("(unreadable image)")
            return
        scaled = pixmap.scaled(
            self._thumbnail.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self._thumbnail.setPixmap(scaled)

    def show_run_result(self, result: RunResult) -> None:
        self._result = result
        self._frame_index = 0
        if result.error_message:
            self._labels["pipeline"].setText(result.pipeline)
            self._labels["outcome"].setText(result.error_message)
            for key in ("pred_lat", "pred_lon", "error", "score", "runtime", "frame"):
                self._labels[key].setText("—")
            self._prev_button.setEnabled(False)
            self._next_button.setEnabled(False)
            return
        self._labels["pipeline"].setText(result.pipeline)
        self._labels["runtime"].setText(f"{result.runtime_seconds:.2f} s")
        self._update_frame_view()
        multi = len(result.frames) > 1
        self._prev_button.setEnabled(multi)
        self._next_button.setEnabled(multi)

    def current_frame(self) -> FramePrediction | None:
        if self._result is None or not self._result.frames:
            return None
        return self._result.frames[self._frame_index]

    def _move_frame(self, delta: int) -> None:
        if self._result is None or not self._result.frames:
            return
        self._frame_index = (self._frame_index + delta) % len(self._result.frames)
        self._update_frame_view()
        self.frame_index_changed.emit(self._frame_index)

    def _update_frame_view(self) -> None:
        if self._result is None or not self._result.frames:
            return
        frame = self._result.frames[self._frame_index]
        outcome = (
            f"ACCEPTED  ({frame.estimate_source})"
            if frame.accepted
            else f"FALLBACK  ({frame.estimate_source})"
        )
        outcome_color = SUCCESS if frame.accepted else HIGHLIGHT
        self._labels["outcome"].setText(outcome)
        self._labels["outcome"].setStyleSheet(
            f"color: {outcome_color}; font-family: Consolas, monospace;"
        )
        self._labels["pred_lat"].setText(f"{frame.predicted_latitude_deg:.6f}°")
        self._labels["pred_lon"].setText(f"{frame.predicted_longitude_deg:.6f}°")
        if frame.error_m is not None:
            self._labels["error"].setText(f"{frame.error_m:.2f} m")
        else:
            self._labels["error"].setText("—")
        if frame.match_score is not None:
            text = f"{frame.match_score:.3f}"
            if frame.runner_up_match_score is not None:
                text += f"  (runner-up {frame.runner_up_match_score:.3f})"
            self._labels["score"].setText(text)
        else:
            self._labels["score"].setText("—")
        if self._result is not None:
            self._labels["frame"].setText(
                f"{self._frame_index + 1} / {len(self._result.frames)}  ({frame.image_name})"
            )
        self.show_query_thumbnail(frame.image_path)
