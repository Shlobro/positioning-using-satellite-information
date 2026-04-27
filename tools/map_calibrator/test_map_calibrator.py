"""Tests for map_calibrator — headless, no display required."""

import importlib
import sys
import types
import json
import tempfile
from pathlib import Path

# ── stub tkinter and PIL so tests run without a display or Pillow ─────────────

def _stub_tkinter():
    tk_mod = types.ModuleType("tkinter")
    tk_mod.Tk = object
    tk_mod.Frame = object
    tk_mod.Canvas = object
    tk_mod.Label = object
    tk_mod.Button = object
    tk_mod.Entry = object
    tk_mod.Toplevel = object
    tk_mod.StringVar = object
    tk_mod.PhotoImage = object
    tk_mod.N = tk_mod.S = tk_mod.E = tk_mod.W = ""
    tk_mod.NW = tk_mod.NE = ""
    tk_mod.LEFT = tk_mod.RIGHT = tk_mod.TOP = tk_mod.BOTTOM = ""
    tk_mod.X = tk_mod.Y = tk_mod.BOTH = ""
    tk_mod.NORMAL = tk_mod.DISABLED = ""
    tk_mod.FLAT = tk_mod.RIDGE = ""

    fd_mod = types.ModuleType("tkinter.filedialog")
    fd_mod.askopenfilename = lambda **_: ""
    fd_mod.asksaveasfilename = lambda **_: ""
    tk_mod.filedialog = fd_mod
    sys.modules["tkinter.filedialog"] = fd_mod

    mb_mod = types.ModuleType("tkinter.messagebox")
    mb_mod.showinfo = lambda *_, **__: None
    mb_mod.showerror = lambda *_, **__: None
    tk_mod.messagebox = mb_mod
    sys.modules["tkinter.messagebox"] = mb_mod

    sys.modules["tkinter"] = tk_mod


def _stub_pil():
    pil_mod = types.ModuleType("PIL")
    img_mod = types.ModuleType("PIL.Image")
    img_mod.Image = object
    img_mod.LANCZOS = None
    pil_mod.Image = img_mod
    sys.modules["PIL"] = pil_mod
    sys.modules["PIL.Image"] = img_mod

    imgtk_mod = types.ModuleType("PIL.ImageTk")

    class _FakePhotoImage:
        def __init__(self, *a, **kw):
            pass

    imgtk_mod.PhotoImage = _FakePhotoImage
    sys.modules["PIL.ImageTk"] = imgtk_mod


_stub_tkinter()
_stub_pil()

# now safe to import the module's pure functions
sys.path.insert(0, str(Path(__file__).parent))
from map_calibrator import parse_gps, MapCalibratorApp  # noqa: E402


# ── parse_gps tests ───────────────────────────────────────────────────────────

def test_parse_degrees_symbol():
    # input order is lng, lat
    result = parse_gps("31.767811°, 35.194956°")
    assert result is not None
    lat, lng = result
    assert abs(lat - 35.194956) < 1e-6
    assert abs(lng - 31.767811) < 1e-6


def test_parse_no_symbol():
    result = parse_gps("31.767811, 35.194956")
    assert result is not None
    lat, lng = result
    assert abs(lat - 35.194956) < 1e-6


def test_parse_negative():
    # lng=151.2093, lat=-33.8688
    result = parse_gps("151.2093°, -33.8688°")
    assert result is not None
    lat, lng = result
    assert lat < 0
    assert lng > 0


def test_parse_whitespace_tolerance():
    result = parse_gps("  31.767811° ,  35.194956°  ")
    assert result is not None


def test_parse_rejects_out_of_range_lat():
    # first value is lng, second is lat — lat=91 is invalid
    assert parse_gps("10.0, 91.0") is None


def test_parse_rejects_out_of_range_lng():
    # first value is lng=181, invalid
    assert parse_gps("181.0, 10.0") is None


def test_parse_rejects_garbage():
    assert parse_gps("not a coordinate") is None


def test_parse_rejects_one_value():
    assert parse_gps("35.194956") is None


def test_parse_rejects_empty():
    assert parse_gps("") is None


def test_parse_rejects_three_values():
    assert parse_gps("35.0, 31.0, 100.0") is None


# ── _build_payload tests ──────────────────────────────────────────────────────

def _make_app_with_points(image_path: str, points: list[dict]):
    """Construct MapCalibratorApp without a display by bypassing __init__."""
    app = object.__new__(MapCalibratorApp)
    app.image_path = image_path
    app.points = points
    return app


def test_build_payload_structure():
    pts = [
        {"pixel": [10, 20], "gps": {"lat": 35.1, "lng": 31.7}},
        {"pixel": [100, 200], "gps": {"lat": 35.2, "lng": 31.8}},
        {"pixel": [300, 400], "gps": {"lat": 35.3, "lng": 31.9}},
        {"pixel": [50, 60], "gps": {"lat": 35.4, "lng": 32.0}},
    ]
    app = _make_app_with_points("/some/image.jpg", pts)
    payload = app._build_payload()
    assert payload["image"] == "/some/image.jpg"
    assert len(payload["calibration_points"]) == 4
    assert payload["calibration_points"][0]["pixel"] == [10, 20]
    assert payload["calibration_points"][0]["gps"]["lat"] == 35.1


def test_build_payload_is_json_serialisable():
    pts = [
        {"pixel": [0, 0], "gps": {"lat": 0.0, "lng": 0.0}},
    ]
    app = _make_app_with_points("/img.png", pts)
    payload = app._build_payload()
    serialised = json.dumps(payload)
    assert '"calibration_points"' in serialised


# ── save / write tests ────────────────────────────────────────────────────────

def test_write_creates_file():
    pts = [
        {"pixel": [10, 20], "gps": {"lat": 35.1, "lng": 31.7}},
        {"pixel": [100, 200], "gps": {"lat": 35.2, "lng": 31.8}},
        {"pixel": [300, 400], "gps": {"lat": 35.3, "lng": 31.9}},
        {"pixel": [50, 60], "gps": {"lat": 35.4, "lng": 32.0}},
    ]
    app = _make_app_with_points("/some/image.jpg", pts)

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "calib.json"
        app._write(out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["image"] == "/some/image.jpg"
        assert len(data["calibration_points"]) == 4


def test_write_json_roundtrip():
    pts = [
        {"pixel": [1, 2], "gps": {"lat": 31.123456, "lng": 34.987654}},
    ]
    app = _make_app_with_points("/map.tif", pts)
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "out.json"
        app._write(out)
        loaded = json.loads(out.read_text())
        assert abs(loaded["calibration_points"][0]["gps"]["lat"] - 31.123456) < 1e-9


# ── run tests directly when executed as a script ──────────────────────────────

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
