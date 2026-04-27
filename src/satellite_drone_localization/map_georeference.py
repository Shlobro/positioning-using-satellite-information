"""Map-image georeferencing from pixel control points."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class CalibrationPoint:
    """One pixel-to-geographic ground control point."""

    pixel_x: float
    pixel_y: float
    latitude_deg: float
    longitude_deg: float


@dataclass(frozen=True)
class LocalMetersPoint:
    """One control point expressed in local tangent-plane meters."""

    pixel_x: float
    pixel_y: float
    east_m: float
    north_m: float


@dataclass(frozen=True)
class AffineCoefficients:
    """Affine coefficients mapping image pixels to one output axis."""

    x_scale: float
    y_scale: float
    offset: float

    def apply(self, pixel_x: float, pixel_y: float) -> float:
        return self.x_scale * pixel_x + self.y_scale * pixel_y + self.offset


@dataclass(frozen=True)
class GeoreferenceResidual:
    """Fit residual for one control point."""

    pixel_x: float
    pixel_y: float
    east_error_m: float
    north_error_m: float
    planar_error_m: float


@dataclass(frozen=True)
class MapGeoreference:
    """Affine map-image transform tied to a local geographic origin."""

    image_path: Path
    image_width_px: int
    image_height_px: int
    reference_latitude_deg: float
    reference_longitude_deg: float
    meters_per_degree_lat: float
    meters_per_degree_lon: float
    east_coefficients: AffineCoefficients
    north_coefficients: AffineCoefficients
    residuals: list[GeoreferenceResidual]

    def pixel_to_local_meters(self, pixel_x: float, pixel_y: float) -> tuple[float, float]:
        """Convert image pixels to east/north offsets from the reference origin."""
        east_m = self.east_coefficients.apply(pixel_x, pixel_y)
        north_m = self.north_coefficients.apply(pixel_x, pixel_y)
        return east_m, north_m

    def pixel_to_latlon(self, pixel_x: float, pixel_y: float) -> tuple[float, float]:
        """Convert image pixels to latitude and longitude."""
        east_m, north_m = self.pixel_to_local_meters(pixel_x, pixel_y)
        latitude_deg = self.reference_latitude_deg + (north_m / self.meters_per_degree_lat)
        longitude_deg = self.reference_longitude_deg + (east_m / self.meters_per_degree_lon)
        return latitude_deg, longitude_deg

    def latlon_to_pixel(self, latitude_deg: float, longitude_deg: float) -> tuple[float, float]:
        """Convert latitude and longitude back into image pixels."""
        east_m = (longitude_deg - self.reference_longitude_deg) * self.meters_per_degree_lon
        north_m = (latitude_deg - self.reference_latitude_deg) * self.meters_per_degree_lat

        determinant = (
            self.east_coefficients.x_scale * self.north_coefficients.y_scale
            - self.east_coefficients.y_scale * self.north_coefficients.x_scale
        )
        if math.isclose(determinant, 0.0, abs_tol=1e-12):
            raise ValueError("georeference transform is singular and cannot be inverted")

        east_rhs = east_m - self.east_coefficients.offset
        north_rhs = north_m - self.north_coefficients.offset

        pixel_x = (
            east_rhs * self.north_coefficients.y_scale - self.east_coefficients.y_scale * north_rhs
        ) / determinant
        pixel_y = (
            self.east_coefficients.x_scale * north_rhs - east_rhs * self.north_coefficients.x_scale
        ) / determinant
        return pixel_x, pixel_y

    @property
    def max_residual_m(self) -> float:
        """Largest planar control-point residual in meters."""
        return max((residual.planar_error_m for residual in self.residuals), default=0.0)


def load_map_georeference(calibration_path: Path) -> MapGeoreference:
    """Load a calibration JSON and fit an affine pixel-to-geographic transform."""
    resolved_path = calibration_path.resolve()
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))

    image_path_value = payload.get("image")
    if not isinstance(image_path_value, str) or not image_path_value.strip():
        raise ValueError("calibration file requires a non-empty 'image' path")
    image_path = Path(image_path_value).resolve()
    image_width_px, image_height_px = resolve_image_size(payload, image_path)

    raw_points = payload.get("calibration_points")
    if not isinstance(raw_points, list) or len(raw_points) < 3:
        raise ValueError("calibration file requires at least three calibration_points")

    points = [parse_calibration_point(raw_point) for raw_point in raw_points]
    reference_latitude_deg = sum(point.latitude_deg for point in points) / len(points)
    reference_longitude_deg = sum(point.longitude_deg for point in points) / len(points)
    meters_per_degree_lat, meters_per_degree_lon = meters_per_degree(reference_latitude_deg)

    local_points = [
        LocalMetersPoint(
            pixel_x=point.pixel_x,
            pixel_y=point.pixel_y,
            east_m=(point.longitude_deg - reference_longitude_deg) * meters_per_degree_lon,
            north_m=(point.latitude_deg - reference_latitude_deg) * meters_per_degree_lat,
        )
        for point in points
    ]

    east_coefficients = fit_affine_axis(
        [(point.pixel_x, point.pixel_y, point.east_m) for point in local_points]
    )
    north_coefficients = fit_affine_axis(
        [(point.pixel_x, point.pixel_y, point.north_m) for point in local_points]
    )

    residuals = [
        build_residual(point, east_coefficients, north_coefficients)
        for point in local_points
    ]

    return MapGeoreference(
        image_path=image_path,
        image_width_px=image_width_px,
        image_height_px=image_height_px,
        reference_latitude_deg=reference_latitude_deg,
        reference_longitude_deg=reference_longitude_deg,
        meters_per_degree_lat=meters_per_degree_lat,
        meters_per_degree_lon=meters_per_degree_lon,
        east_coefficients=east_coefficients,
        north_coefficients=north_coefficients,
        residuals=residuals,
    )


def parse_calibration_point(payload: object) -> CalibrationPoint:
    """Validate one calibration point payload."""
    if not isinstance(payload, dict):
        raise ValueError("calibration point must be an object")

    pixel = payload.get("pixel")
    if not isinstance(pixel, list) or len(pixel) != 2:
        raise ValueError("calibration point requires a two-element pixel array")
    pixel_x = _coerce_float(pixel[0], "pixel[0]")
    pixel_y = _coerce_float(pixel[1], "pixel[1]")

    gps = payload.get("gps")
    if not isinstance(gps, dict):
        raise ValueError("calibration point requires a gps object")
    latitude_deg = _coerce_float(gps.get("lat"), "gps.lat")
    longitude_deg = _coerce_float(gps.get("lng"), "gps.lng")

    if not (-90.0 <= latitude_deg <= 90.0):
        raise ValueError("gps.lat must be within [-90, 90]")
    if not (-180.0 <= longitude_deg <= 180.0):
        raise ValueError("gps.lng must be within [-180, 180]")

    return CalibrationPoint(
        pixel_x=pixel_x,
        pixel_y=pixel_y,
        latitude_deg=latitude_deg,
        longitude_deg=longitude_deg,
    )


def meters_per_degree(latitude_deg: float) -> tuple[float, float]:
    """Approximate meters per degree of latitude and longitude."""
    latitude_rad = math.radians(latitude_deg)
    meters_lat = (
        111132.92
        - 559.82 * math.cos(2.0 * latitude_rad)
        + 1.175 * math.cos(4.0 * latitude_rad)
        - 0.0023 * math.cos(6.0 * latitude_rad)
    )
    meters_lon = (
        111412.84 * math.cos(latitude_rad)
        - 93.5 * math.cos(3.0 * latitude_rad)
        + 0.118 * math.cos(5.0 * latitude_rad)
    )
    return meters_lat, meters_lon


def resolve_image_size(payload: dict[str, object], image_path: Path) -> tuple[int, int]:
    """Resolve image width and height from calibration JSON or a PNG header."""
    image_size_value = payload.get("image_size_px")
    if image_size_value is not None:
        if not isinstance(image_size_value, list) or len(image_size_value) != 2:
            raise ValueError("image_size_px must be a two-element array when provided")
        width_px = _coerce_int(image_size_value[0], "image_size_px[0]")
        height_px = _coerce_int(image_size_value[1], "image_size_px[1]")
        return width_px, height_px
    return read_png_image_size(image_path)


def read_png_image_size(image_path: Path) -> tuple[int, int]:
    """Read width and height from a PNG header using only the standard library."""
    with image_path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("image_size_px is required for non-PNG calibration images")
    width_px = int.from_bytes(header[16:20], byteorder="big", signed=False)
    height_px = int.from_bytes(header[20:24], byteorder="big", signed=False)
    if width_px <= 0 or height_px <= 0:
        raise ValueError("PNG image dimensions must be positive")
    return width_px, height_px


def fit_affine_axis(samples: list[tuple[float, float, float]]) -> AffineCoefficients:
    """Fit one affine output axis from pixel x/y using normal equations."""
    xx = xy = x_sum = yy = y_sum = sample_count = 0.0
    xz = yz = z1 = 0.0
    for pixel_x, pixel_y, value in samples:
        xx += pixel_x * pixel_x
        xy += pixel_x * pixel_y
        x_sum += pixel_x
        yy += pixel_y * pixel_y
        y_sum += pixel_y
        xz += pixel_x * value
        yz += pixel_y * value
        z1 += value
        sample_count += 1.0

    matrix = [
        [xx, xy, x_sum],
        [xy, yy, y_sum],
        [x_sum, y_sum, sample_count],
    ]
    rhs = [xz, yz, z1]
    solution = solve_3x3(matrix, rhs)
    return AffineCoefficients(
        x_scale=solution[0],
        y_scale=solution[1],
        offset=solution[2],
    )


def build_residual(
    point: LocalMetersPoint,
    east_coefficients: AffineCoefficients,
    north_coefficients: AffineCoefficients,
) -> GeoreferenceResidual:
    """Build the fit residual for one local-meter control point."""
    predicted_east_m = east_coefficients.apply(point.pixel_x, point.pixel_y)
    predicted_north_m = north_coefficients.apply(point.pixel_x, point.pixel_y)
    east_error_m = predicted_east_m - point.east_m
    north_error_m = predicted_north_m - point.north_m
    return GeoreferenceResidual(
        pixel_x=point.pixel_x,
        pixel_y=point.pixel_y,
        east_error_m=east_error_m,
        north_error_m=north_error_m,
        planar_error_m=math.hypot(east_error_m, north_error_m),
    )


def solve_3x3(matrix: list[list[float]], rhs: list[float]) -> tuple[float, float, float]:
    """Solve a 3x3 linear system with Gaussian elimination."""
    rows = [matrix_row[:] + [rhs_value] for matrix_row, rhs_value in zip(matrix, rhs, strict=True)]
    size = 3

    for pivot_index in range(size):
        pivot_row = max(range(pivot_index, size), key=lambda row_index: abs(rows[row_index][pivot_index]))
        pivot_value = rows[pivot_row][pivot_index]
        if math.isclose(pivot_value, 0.0, abs_tol=1e-12):
            raise ValueError("calibration points do not produce an invertible affine fit")
        if pivot_row != pivot_index:
            rows[pivot_index], rows[pivot_row] = rows[pivot_row], rows[pivot_index]

        normalized_pivot = rows[pivot_index][pivot_index]
        for column_index in range(pivot_index, size + 1):
            rows[pivot_index][column_index] /= normalized_pivot

        for row_index in range(size):
            if row_index == pivot_index:
                continue
            factor = rows[row_index][pivot_index]
            if math.isclose(factor, 0.0, abs_tol=1e-12):
                continue
            for column_index in range(pivot_index, size + 1):
                rows[row_index][column_index] -= factor * rows[pivot_index][column_index]

    return rows[0][3], rows[1][3], rows[2][3]


def _coerce_float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    return float(value)


def _coerce_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value
