"""Sidebar controls for the localization GUI.

Holds:
- satellite tile picker (file dialog)
- input mode (single image / sequence)
- query input picker (image with sidecar, or replay packet)
- prior input (clicked from map *or* lat/lon entry)
- radius slider
- pipeline picker (depends on input mode)
- run button + heatmap/overlay toggles
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets


PANEL_BG = "#16213e"
ACCENT = "#0f3460"
HIGHLIGHT = "#e94560"
TEXT = "#eaeaea"
TEXT_DIM = "#7a7a9a"
SUCCESS = "#4caf82"


@dataclass
class ControlsState:
    tile_path: Path | None = None
    input_mode: str = "single"  # "single" or "sequence"
    query_path: Path | None = None
    prior_latitude_deg: float | None = None
    prior_longitude_deg: float | None = None
    prior_radius_m: float = 25.0
    pipeline: str = ""
    show_heatmap: bool = True
    show_query_overlay: bool = True


class ControlsPanel(QtWidgets.QWidget):
    """Sidebar widget that emits typed signals for the main window to act on."""

    tile_picked = QtCore.pyqtSignal(Path)
    input_mode_changed = QtCore.pyqtSignal(str)
    query_picked = QtCore.pyqtSignal(Path)
    prior_latlon_submitted = QtCore.pyqtSignal(float, float)
    radius_changed = QtCore.pyqtSignal(float)
    pipeline_changed = QtCore.pyqtSignal(str)
    run_requested = QtCore.pyqtSignal()
    heatmap_toggled = QtCore.pyqtSignal(bool)
    query_overlay_toggled = QtCore.pyqtSignal(bool)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: {PANEL_BG};
                color: {TEXT};
                font-family: 'Segoe UI', sans-serif;
                font-size: 11pt;
            }}
            QLabel.section {{
                color: {HIGHLIGHT};
                font-weight: 700;
                font-size: 11pt;
                padding-top: 12px;
            }}
            QLabel.dim {{
                color: {TEXT_DIM};
                font-size: 9pt;
            }}
            QPushButton {{
                background-color: {ACCENT};
                color: {TEXT};
                border: none;
                padding: 6px 10px;
                border-radius: 3px;
            }}
            QPushButton:hover {{
                background-color: {HIGHLIGHT};
            }}
            QPushButton#run {{
                background-color: {SUCCESS};
                font-weight: 700;
                padding: 8px 12px;
            }}
            QPushButton#run:disabled {{
                background-color: #2a4a3a;
                color: {TEXT_DIM};
            }}
            QLineEdit, QDoubleSpinBox, QComboBox {{
                background-color: {ACCENT};
                color: {TEXT};
                padding: 4px 6px;
                border: 1px solid {TEXT_DIM};
                border-radius: 3px;
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {ACCENT};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {HIGHLIGHT};
                width: 14px;
                margin: -6px 0;
                border-radius: 7px;
            }}
            """
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)

        title = QtWidgets.QLabel("Drone Localization")
        title.setStyleSheet(f"color: {HIGHLIGHT}; font-size: 16pt; font-weight: 800;")
        layout.addWidget(title)

        layout.addWidget(self._section_label("Satellite tile"))
        self._tile_button = QtWidgets.QPushButton("Pick satellite tile…")
        self._tile_button.clicked.connect(self._pick_tile)
        layout.addWidget(self._tile_button)
        self._tile_label = self._dim_label("(no tile loaded)")
        layout.addWidget(self._tile_label)

        layout.addWidget(self._section_label("Input mode"))
        self._single_radio = QtWidgets.QRadioButton("Single image")
        self._sequence_radio = QtWidgets.QRadioButton("Sequence (replay packet)")
        self._single_radio.setChecked(True)
        self._single_radio.toggled.connect(self._on_input_mode_toggled)
        layout.addWidget(self._single_radio)
        layout.addWidget(self._sequence_radio)

        layout.addWidget(self._section_label("Query input"))
        self._query_button = QtWidgets.QPushButton("Pick image / replay…")
        self._query_button.clicked.connect(self._pick_query)
        layout.addWidget(self._query_button)
        self._query_label = self._dim_label("(no query loaded)")
        layout.addWidget(self._query_label)

        layout.addWidget(self._section_label("Prior (click map or enter lat/lon)"))
        self._lat_edit = QtWidgets.QLineEdit()
        self._lat_edit.setPlaceholderText("latitude (deg)")
        self._lon_edit = QtWidgets.QLineEdit()
        self._lon_edit.setPlaceholderText("longitude (deg)")
        latlon_row = QtWidgets.QHBoxLayout()
        latlon_row.addWidget(self._lat_edit)
        latlon_row.addWidget(self._lon_edit)
        layout.addLayout(latlon_row)
        self._submit_latlon = QtWidgets.QPushButton("Apply lat/lon")
        self._submit_latlon.clicked.connect(self._on_submit_latlon)
        layout.addWidget(self._submit_latlon)

        layout.addWidget(self._section_label("Search radius"))
        radius_row = QtWidgets.QHBoxLayout()
        self._radius_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._radius_slider.setMinimum(5)
        self._radius_slider.setMaximum(500)
        self._radius_slider.setValue(25)
        self._radius_slider.valueChanged.connect(self._on_radius_changed)
        self._radius_value = QtWidgets.QLabel("25 m")
        radius_row.addWidget(self._radius_slider)
        radius_row.addWidget(self._radius_value)
        layout.addLayout(radius_row)

        layout.addWidget(self._section_label("Pipeline"))
        self._pipeline_combo = QtWidgets.QComboBox()
        self._pipeline_combo.currentTextChanged.connect(self._on_pipeline_changed)
        layout.addWidget(self._pipeline_combo)

        layout.addWidget(self._section_label("Display"))
        self._heatmap_check = QtWidgets.QCheckBox("Show confidence heatmap")
        self._heatmap_check.setChecked(True)
        self._heatmap_check.toggled.connect(self.heatmap_toggled.emit)
        self._overlay_check = QtWidgets.QCheckBox("Show warped query overlay")
        self._overlay_check.setChecked(True)
        self._overlay_check.toggled.connect(self.query_overlay_toggled.emit)
        layout.addWidget(self._heatmap_check)
        layout.addWidget(self._overlay_check)

        self._progress_label = self._dim_label("")
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)

        self._progress_bar = QtWidgets.QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setVisible(False)
        self._progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {ACCENT};
                border: 1px solid {TEXT_DIM};
                border-radius: 3px;
                min-height: 12px;
            }}
            QProgressBar::chunk {{
                background-color: {HIGHLIGHT};
                border-radius: 3px;
            }}
            """
        )
        layout.addWidget(self._progress_bar)

        layout.addStretch(1)

        self._run_button = QtWidgets.QPushButton("Run localization")
        self._run_button.setObjectName("run")
        self._run_button.setEnabled(False)
        self._run_button.clicked.connect(self.run_requested.emit)
        layout.addWidget(self._run_button)

        self._interactive_widgets = (
            self._tile_button,
            self._single_radio,
            self._sequence_radio,
            self._query_button,
            self._lat_edit,
            self._lon_edit,
            self._submit_latlon,
            self._radius_slider,
            self._pipeline_combo,
            self._heatmap_check,
            self._overlay_check,
        )

    def set_pipeline_choices(self, choices: list[str]) -> None:
        self._pipeline_combo.blockSignals(True)
        self._pipeline_combo.clear()
        self._pipeline_combo.addItems(choices)
        self._pipeline_combo.blockSignals(False)
        if choices:
            self.pipeline_changed.emit(choices[0])

    def set_tile_label(self, text: str) -> None:
        self._tile_label.setText(text)

    def set_query_label(self, text: str) -> None:
        self._query_label.setText(text)

    def set_run_enabled(self, enabled: bool) -> None:
        self._run_button.setEnabled(enabled)

    def set_run_in_progress(self, running: bool, message: str = "") -> None:
        for widget in self._interactive_widgets:
            widget.setEnabled(not running)
        self._run_button.setEnabled(not running)
        self._run_button.setText("Running…" if running else "Run localization")
        self._progress_label.setVisible(running)
        self._progress_bar.setVisible(running)
        if running:
            self._progress_label.setText(message or "Running localization…")
        else:
            self._progress_label.setText("")

    def set_latlon_text(self, latitude_deg: float, longitude_deg: float) -> None:
        self._lat_edit.setText(f"{latitude_deg:.6f}")
        self._lon_edit.setText(f"{longitude_deg:.6f}")

    def current_radius_m(self) -> float:
        return float(self._radius_slider.value())

    def current_pipeline(self) -> str:
        return self._pipeline_combo.currentText()

    def current_input_mode(self) -> str:
        return "single" if self._single_radio.isChecked() else "sequence"

    def heatmap_visible(self) -> bool:
        return self._heatmap_check.isChecked()

    def query_overlay_visible(self) -> bool:
        return self._overlay_check.isChecked()

    def _pick_tile(self) -> None:
        default_dir = str(
            Path(
                "data/DEV-SESSION-20260427T112451Z/Frame from satellite/GIS system roof next to labs in college.png"
            ).resolve().parent
        )
        path_str, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Pick satellite tile",
            default_dir,
            "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp)",
        )
        if path_str:
            self.tile_picked.emit(Path(path_str))

    def _pick_query(self) -> None:
        if self.current_input_mode() == "single":
            path_str, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Pick a drone image (must have a *_packet.json sidecar)",
                "",
                "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp)",
            )
        else:
            path_str, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Pick a dev-packet-v1 replay file",
                "",
                "JSON Lines (*.jsonl);;All files (*.*)",
            )
        if path_str:
            self.query_picked.emit(Path(path_str))

    def _on_input_mode_toggled(self, _: bool) -> None:
        self.input_mode_changed.emit(self.current_input_mode())

    def _on_radius_changed(self, value: int) -> None:
        self._radius_value.setText(f"{value} m")
        self.radius_changed.emit(float(value))

    def _on_pipeline_changed(self, value: str) -> None:
        self.pipeline_changed.emit(value)

    def _on_submit_latlon(self) -> None:
        try:
            latitude_deg = float(self._lat_edit.text().strip())
            longitude_deg = float(self._lon_edit.text().strip())
        except ValueError:
            return
        self.prior_latlon_submitted.emit(latitude_deg, longitude_deg)

    def _section_label(self, text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setProperty("class", "section")
        label.setStyleSheet(f"color: {HIGHLIGHT}; font-weight: 700; padding-top: 10px;")
        return label

    def _dim_label(self, text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setStyleSheet(f"color: {TEXT_DIM}; font-size: 9pt;")
        label.setWordWrap(True)
        return label
