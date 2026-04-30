"""Interactive satellite-tile map view for the localization GUI.

Wraps `pyqtgraph` to provide:

- pan / zoom on a large satellite tile
- a movable "prior" marker (also driven from a lat/lon textbox)
- a search-radius circle in pixel space (sized in meters via georeference)
- a predicted-location marker
- an optional confidence heatmap
- an optional warped query-image overlay at the prediction
- optional truth marker (when running on georeferenced ground truth)

Coordinate convention:

- pyqtgraph's ImageItem is set to display in image-pixel coordinates with the
  Y-axis inverted so visual appearance matches the satellite tile.
- `latlon_to_pixel` from `MapGeoreference` is the only path between map clicks
  and lat/lon. Heatmap coordinates are also expressed in image pixels.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PIL import Image
from PyQt6 import QtCore, QtGui, QtWidgets

from satellite_drone_localization.crop import meters_offset_between
from satellite_drone_localization.map_georeference import MapGeoreference

from .pipeline_runner import FramePrediction


PRIOR_COLOR = QtGui.QColor("#e94560")
PREDICTION_COLOR = QtGui.QColor("#4caf82")
TRUTH_COLOR = QtGui.QColor("#f6c453")
RADIUS_COLOR = QtGui.QColor(233, 69, 96, 70)
RADIUS_OUTLINE = QtGui.QColor("#e94560")
HEATMAP_COLORMAP_NAME = "viridis"
QUERY_OVERLAY_OPACITY = 0.55


@dataclass
class PriorState:
    pixel_x: float
    pixel_y: float
    radius_m: float


class MapView(QtWidgets.QWidget):
    """Pan/zoom satellite tile with localization overlays."""

    prior_changed = QtCore.pyqtSignal(float, float)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("#0d0d1a")
        self._plot_widget.setAspectLocked(True)
        self._plot_widget.setMenuEnabled(False)
        self._plot_widget.hideAxis("bottom")
        self._plot_widget.hideAxis("left")
        layout.addWidget(self._plot_widget)

        self._view_box: pg.ViewBox = self._plot_widget.getViewBox()
        self._view_box.invertY(True)

        self._image_item = pg.ImageItem(axisOrder="row-major")
        self._view_box.addItem(self._image_item)

        self._heatmap_item = pg.ImageItem(axisOrder="row-major")
        self._heatmap_item.setOpacity(0.55)
        self._heatmap_item.setVisible(False)
        self._view_box.addItem(self._heatmap_item)

        self._query_overlay_item = pg.ImageItem(axisOrder="row-major")
        self._query_overlay_item.setOpacity(QUERY_OVERLAY_OPACITY)
        self._query_overlay_item.setVisible(False)
        self._view_box.addItem(self._query_overlay_item)

        self._radius_circle = QtWidgets.QGraphicsEllipseItem()
        pen = pg.mkPen(RADIUS_OUTLINE, width=2)
        brush = pg.mkBrush(RADIUS_COLOR)
        self._radius_circle.setPen(pen)
        self._radius_circle.setBrush(brush)
        self._radius_circle.setVisible(False)
        self._view_box.addItem(self._radius_circle)

        self._prior_marker = self._make_marker(PRIOR_COLOR)
        self._prediction_marker = self._make_marker(PREDICTION_COLOR)
        self._truth_marker = self._make_marker(TRUTH_COLOR)
        self._view_box.addItem(self._prior_marker)
        self._view_box.addItem(self._prediction_marker)
        self._view_box.addItem(self._truth_marker)

        self._georeference: MapGeoreference | None = None
        self._prior: PriorState | None = None
        self._image_array: np.ndarray | None = None

        self._plot_widget.scene().sigMouseClicked.connect(self._on_mouse_clicked)

    def _make_marker(self, color: QtGui.QColor) -> pg.ScatterPlotItem:
        marker = pg.ScatterPlotItem(
            size=18,
            pen=pg.mkPen(color, width=3),
            brush=pg.mkBrush(0, 0, 0, 0),
            symbol="+",
        )
        marker.setVisible(False)
        return marker

    def load_tile(self, image_path: Path, georeference: MapGeoreference) -> None:
        """Load a satellite tile and reset overlays."""
        image_array = _read_image_as_rgb_array(image_path)
        self._image_array = image_array
        self._image_item.setImage(image_array, autoLevels=False)
        self._image_item.setRect(
            QtCore.QRectF(0.0, 0.0, float(image_array.shape[1]), float(image_array.shape[0]))
        )
        self._view_box.autoRange()
        self._georeference = georeference
        self.clear_results()

    def set_prior(self, pixel_x: float, pixel_y: float, radius_m: float) -> None:
        """Set the prior marker and search radius."""
        if self._georeference is None:
            return
        self._prior = PriorState(pixel_x=pixel_x, pixel_y=pixel_y, radius_m=radius_m)
        self._prior_marker.setData([pixel_x], [pixel_y])
        self._prior_marker.setVisible(True)
        self._update_radius_circle()
        latitude_deg, longitude_deg = self._georeference.pixel_to_latlon(pixel_x, pixel_y)
        self.prior_changed.emit(latitude_deg, longitude_deg)

    def set_prior_from_latlon(
        self, latitude_deg: float, longitude_deg: float, radius_m: float
    ) -> None:
        if self._georeference is None:
            return
        pixel_x, pixel_y = self._georeference.latlon_to_pixel(latitude_deg, longitude_deg)
        self.set_prior(pixel_x, pixel_y, radius_m)

    def set_prediction(self, prediction: FramePrediction | None) -> None:
        """Show or clear the prediction marker and truth marker."""
        if prediction is None:
            self._prediction_marker.setVisible(False)
            self._truth_marker.setVisible(False)
            return
        self._prediction_marker.setData([prediction.predicted_pixel_x], [prediction.predicted_pixel_y])
        self._prediction_marker.setVisible(True)
        if prediction.truth_pixel_x is not None and prediction.truth_pixel_y is not None:
            self._truth_marker.setData([prediction.truth_pixel_x], [prediction.truth_pixel_y])
            self._truth_marker.setVisible(True)
        else:
            self._truth_marker.setVisible(False)

    def set_heatmap(
        self,
        grid: np.ndarray | None,
        origin_pixel: tuple[float, float] | None,
        pixel_size: tuple[float, float] | None,
        visible: bool,
    ) -> None:
        if grid is None or origin_pixel is None or pixel_size is None:
            self._heatmap_item.setVisible(False)
            return
        normalized = _normalize_heatmap(grid)
        colored = _apply_colormap(normalized)
        self._heatmap_item.setImage(colored, autoLevels=False)
        height, width = grid.shape
        x0 = origin_pixel[0] - (pixel_size[0] * width) / 2.0
        y0 = origin_pixel[1] - (pixel_size[1] * height) / 2.0
        self._heatmap_item.setRect(
            QtCore.QRectF(x0, y0, pixel_size[0] * width, pixel_size[1] * height)
        )
        self._heatmap_item.setVisible(visible)

    def set_heatmap_visible(self, visible: bool) -> None:
        self._heatmap_item.setVisible(visible and self._heatmap_item.image is not None)

    def set_query_overlay(
        self,
        prediction: FramePrediction | None,
        visible: bool,
    ) -> None:
        if prediction is None or self._georeference is None or not visible:
            self._query_overlay_item.setVisible(False)
            return
        try:
            overlay_array, top_left_pixel, size_px = _build_query_overlay(
                prediction=prediction, georeference=self._georeference
            )
        except Exception:
            self._query_overlay_item.setVisible(False)
            return
        self._query_overlay_item.setImage(overlay_array, autoLevels=False)
        self._query_overlay_item.setRect(
            QtCore.QRectF(top_left_pixel[0], top_left_pixel[1], size_px[0], size_px[1])
        )
        self._query_overlay_item.setVisible(True)

    def clear_results(self) -> None:
        self._prediction_marker.setVisible(False)
        self._truth_marker.setVisible(False)
        self._heatmap_item.setVisible(False)
        self._query_overlay_item.setVisible(False)

    def _update_radius_circle(self) -> None:
        if self._prior is None or self._georeference is None:
            self._radius_circle.setVisible(False)
            return
        meters_per_pixel = self._estimate_meters_per_pixel()
        if meters_per_pixel is None or meters_per_pixel <= 0.0:
            self._radius_circle.setVisible(False)
            return
        radius_px = self._prior.radius_m / meters_per_pixel
        self._radius_circle.setRect(
            self._prior.pixel_x - radius_px,
            self._prior.pixel_y - radius_px,
            2.0 * radius_px,
            2.0 * radius_px,
        )
        self._radius_circle.setVisible(True)

    def _estimate_meters_per_pixel(self) -> float | None:
        if self._georeference is None or self._prior is None:
            return None
        center_lat, center_lon = self._georeference.pixel_to_latlon(
            self._prior.pixel_x, self._prior.pixel_y
        )
        offset_lat, offset_lon = self._georeference.pixel_to_latlon(
            self._prior.pixel_x + 1.0, self._prior.pixel_y
        )
        east_m, north_m = meters_offset_between(
            origin_latitude_deg=center_lat,
            origin_longitude_deg=center_lon,
            target_latitude_deg=offset_lat,
            target_longitude_deg=offset_lon,
        )
        per_pixel_x = (east_m * east_m + north_m * north_m) ** 0.5

        offset_lat_y, offset_lon_y = self._georeference.pixel_to_latlon(
            self._prior.pixel_x, self._prior.pixel_y + 1.0
        )
        east_m_y, north_m_y = meters_offset_between(
            origin_latitude_deg=center_lat,
            origin_longitude_deg=center_lon,
            target_latitude_deg=offset_lat_y,
            target_longitude_deg=offset_lon_y,
        )
        per_pixel_y = (east_m_y * east_m_y + north_m_y * north_m_y) ** 0.5
        if per_pixel_x <= 0.0 or per_pixel_y <= 0.0:
            return None
        return (per_pixel_x + per_pixel_y) / 2.0

    def _on_mouse_clicked(self, event) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        if self._georeference is None or self._image_array is None:
            return
        scene_pos = event.scenePos()
        if not self._image_item.sceneBoundingRect().contains(scene_pos):
            return
        view_pos = self._view_box.mapSceneToView(scene_pos)
        pixel_x = float(view_pos.x())
        pixel_y = float(view_pos.y())
        if not (0.0 <= pixel_x <= self._image_array.shape[1]):
            return
        if not (0.0 <= pixel_y <= self._image_array.shape[0]):
            return
        radius_m = self._prior.radius_m if self._prior is not None else 25.0
        self.set_prior(pixel_x, pixel_y, radius_m)


def _read_image_as_rgb_array(image_path: Path) -> np.ndarray:
    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        return np.array(rgb, dtype=np.uint8)


def _normalize_heatmap(grid: np.ndarray) -> np.ndarray:
    flat = grid.astype(np.float32)
    minimum = float(np.min(flat))
    maximum = float(np.max(flat))
    if maximum - minimum < 1e-9:
        return np.zeros_like(flat)
    return (flat - minimum) / (maximum - minimum)


def _apply_colormap(normalized: np.ndarray) -> np.ndarray:
    colormap = pg.colormap.get(HEATMAP_COLORMAP_NAME)
    lookup = colormap.getLookupTable(start=0.0, stop=1.0, nPts=256, alpha=True)
    indices = np.clip((normalized * 255.0).astype(np.int32), 0, 255)
    rgba = lookup[indices]
    rgba[..., 3] = (normalized * 200.0).astype(np.uint8)
    return rgba


def _build_query_overlay(
    *,
    prediction: FramePrediction,
    georeference: MapGeoreference,
) -> tuple[np.ndarray, tuple[float, float], tuple[float, float]]:
    """Build a north-up rotated, footprint-sized query overlay around the prediction."""
    with Image.open(prediction.image_path) as image:
        rgba = image.convert("RGBA")
        normalization_rotation_deg = (-prediction.heading_deg) % 360.0
        rotated = rgba.rotate(
            normalization_rotation_deg,
            resample=Image.Resampling.BILINEAR,
            expand=True,
        )
        center_lat, center_lon = georeference.pixel_to_latlon(
            prediction.predicted_pixel_x, prediction.predicted_pixel_y
        )
        east_lat, east_lon = georeference.pixel_to_latlon(
            prediction.predicted_pixel_x + 1.0, prediction.predicted_pixel_y
        )
        east_m, north_m = meters_offset_between(
            origin_latitude_deg=center_lat,
            origin_longitude_deg=center_lon,
            target_latitude_deg=east_lat,
            target_longitude_deg=east_lon,
        )
        meters_per_pixel = max(1e-6, (east_m * east_m + north_m * north_m) ** 0.5)
        target_w_px = max(8, int(round(prediction.ground_width_m / meters_per_pixel)))
        target_h_px = max(8, int(round(prediction.ground_height_m / meters_per_pixel)))
        resized = rotated.resize((target_w_px, target_h_px), resample=Image.Resampling.BILINEAR)
        rgba_array = np.array(resized, dtype=np.uint8)
        # bake the requested overall opacity into the alpha channel for visibility
        rgba_array[..., 3] = (rgba_array[..., 3].astype(np.float32) * QUERY_OVERLAY_OPACITY).astype(
            np.uint8
        )
        top_left = (
            prediction.predicted_pixel_x - target_w_px / 2.0,
            prediction.predicted_pixel_y - target_h_px / 2.0,
        )
        return rgba_array, top_left, (float(target_w_px), float(target_h_px))
