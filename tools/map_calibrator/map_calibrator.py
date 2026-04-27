"""
Map Calibrator — interactive pixel-to-GPS ground control point collector.

Usage:
    python tools/map_calibrator/map_calibrator.py [image_path]

If image_path is omitted a file-open dialog appears on launch.
"""

import json
import math
import os
import re
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

try:
    from PIL import Image, ImageTk
except ImportError:
    print("Pillow is required: pip install Pillow")
    sys.exit(1)

# ── palette ──────────────────────────────────────────────────────────────────
BG         = "#1a1a2e"
PANEL_BG   = "#16213e"
ACCENT     = "#0f3460"
HIGHLIGHT  = "#e94560"
TEXT       = "#eaeaea"
TEXT_DIM   = "#7a7a9a"
SUCCESS    = "#4caf82"
POINT_CLR  = "#e94560"
POINT_DONE = "#4caf82"
FONT_MAIN  = ("Segoe UI", 10)
FONT_BOLD  = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 13, "bold")
FONT_MONO  = ("Consolas", 9)

REQUIRED_POINTS = 4
CROSSHAIR_R = 10  # crosshair arm length in canvas pixels


# ── coordinate parser ────────────────────────────────────────────────────────

def parse_gps(text: str) -> tuple[float, float] | None:
    """
    Input order is lng, lat (as copied from most web maps).
    Accept formats like:
        31.767811°, 35.194956°
        31.767811, 35.194956
        31.767811°, -35.194956
    Returns (lat, lng) or None on parse failure.
    """
    cleaned = text.replace("°", "").replace(" ", "")
    parts = cleaned.split(",")
    if len(parts) != 2:
        return None
    try:
        lng = float(parts[0])
        lat = float(parts[1])
    except ValueError:
        return None
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return None
    return lat, lng


# ── main application ─────────────────────────────────────────────────────────

class MapCalibratorApp:
    def __init__(self, root: tk.Tk, image_path: str | None = None):
        self.root = root
        self.root.title("Map Calibrator")
        self.root.configure(bg=BG)
        self.root.minsize(900, 620)

        self.points: list[dict] = []      # {"pixel": [x,y], "gps": {"lat":…,"lng":…}}
        self.image_path: str | None = None
        self.pil_image: Image.Image | None = None

        # viewport state
        self._zoom = 1.0
        self._offset_x = 0.0   # canvas pixels from image origin
        self._offset_y = 0.0
        self._drag_start: tuple[int, int] | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._pending_click: tuple[int, int] | None = None  # image pixel coords

        # performance: debounce high-quality re-render after interaction ends
        self._settle_job: str | None = None  # tkinter after() handle
        self._interacting = False            # True while dragging/scrolling

        self._build_ui()
        self._bind_events()

        if image_path and Path(image_path).is_file():
            self._load_image(image_path)
        else:
            self._prompt_open()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # top bar
        top = tk.Frame(self.root, bg=PANEL_BG, height=48)
        top.pack(fill=tk.X, side=tk.TOP)
        top.pack_propagate(False)

        tk.Label(top, text="Map Calibrator", font=FONT_TITLE,
                 fg=HIGHLIGHT, bg=PANEL_BG).pack(side=tk.LEFT, padx=16, pady=8)

        self._open_btn = self._make_btn(top, "Open Image", self._prompt_open,
                                        color=ACCENT)
        self._open_btn.pack(side=tk.LEFT, padx=4, pady=8)

        self._save_btn = self._make_btn(top, "Save", self._save,
                                        color=SUCCESS, state=tk.DISABLED)
        self._save_btn.pack(side=tk.RIGHT, padx=4, pady=8)

        self._saveas_btn = self._make_btn(top, "Save As…", self._save_as,
                                          color=SUCCESS, state=tk.DISABLED)
        self._saveas_btn.pack(side=tk.RIGHT, padx=4, pady=8)

        self._reset_btn = self._make_btn(top, "Reset Points", self._reset_points,
                                         color=HIGHLIGHT, state=tk.DISABLED)
        self._reset_btn.pack(side=tk.RIGHT, padx=4, pady=8)

        # main area: canvas + sidebar
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(main, bg="#0d0d1a", cursor="crosshair",
                                highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        self._sidebar = tk.Frame(main, bg=PANEL_BG, width=220)
        self._sidebar.pack(fill=tk.Y, side=tk.RIGHT)
        self._sidebar.pack_propagate(False)
        self._build_sidebar()

        # status bar
        self._status_var = tk.StringVar(value="Open an image to begin.")
        status = tk.Label(self.root, textvariable=self._status_var,
                          font=FONT_MONO, fg=TEXT_DIM, bg=ACCENT,
                          anchor=tk.W, padx=10)
        status.pack(fill=tk.X, side=tk.BOTTOM)

    def _build_sidebar(self):
        sb = self._sidebar
        tk.Label(sb, text="Ground Control Points", font=FONT_BOLD,
                 fg=HIGHLIGHT, bg=PANEL_BG).pack(pady=(16, 4), padx=12, anchor=tk.W)

        self._progress_var = tk.StringVar(value="0 / 4 points")
        tk.Label(sb, textvariable=self._progress_var, font=FONT_MAIN,
                 fg=TEXT_DIM, bg=PANEL_BG).pack(padx=12, anchor=tk.W)

        # progress bar canvas
        self._prog_canvas = tk.Canvas(sb, bg=ACCENT, height=6,
                                      highlightthickness=0)
        self._prog_canvas.pack(fill=tk.X, padx=12, pady=(4, 12))
        self._prog_bar = self._prog_canvas.create_rectangle(
            0, 0, 0, 6, fill=HIGHLIGHT, outline="")

        # point list frames
        self._point_frames: list[tk.Frame] = []
        for i in range(REQUIRED_POINTS):
            f = tk.Frame(sb, bg=ACCENT, bd=0, relief=tk.FLAT)
            f.pack(fill=tk.X, padx=12, pady=3)
            num = tk.Label(f, text=f"{i+1}", font=FONT_BOLD,
                           fg=TEXT_DIM, bg=ACCENT, width=2)
            num.pack(side=tk.LEFT, padx=(8, 4), pady=8)
            info = tk.Label(f, text="—", font=FONT_MONO,
                            fg=TEXT_DIM, bg=ACCENT, anchor=tk.W, justify=tk.LEFT)
            info.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4, pady=8)
            f._num_label = num
            f._info_label = info
            self._point_frames.append(f)

        tk.Label(sb, text="Scroll: zoom  |  Right-drag: pan",
                 font=("Segoe UI", 8), fg=TEXT_DIM, bg=PANEL_BG,
                 wraplength=190, justify=tk.LEFT).pack(
            padx=12, pady=(16, 4), anchor=tk.W)
        tk.Label(sb, text="Left-click: place point",
                 font=("Segoe UI", 8), fg=TEXT_DIM, bg=PANEL_BG).pack(
            padx=12, anchor=tk.W)

    def _make_btn(self, parent, text, cmd, color=ACCENT, state=tk.NORMAL):
        btn = tk.Button(parent, text=text, command=cmd,
                        font=FONT_BOLD, fg=TEXT, bg=color,
                        activebackground=HIGHLIGHT, activeforeground=TEXT,
                        relief=tk.FLAT, padx=12, pady=4,
                        cursor="hand2", state=state, bd=0)
        btn.bind("<Enter>", lambda e, b=btn, c=color: b.configure(bg=HIGHLIGHT))
        btn.bind("<Leave>", lambda e, b=btn, c=color: b.configure(bg=c))
        return btn

    # ── event binding ─────────────────────────────────────────────────────────

    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>",   self._on_left_click)
        self.canvas.bind("<ButtonPress-3>",   self._on_right_press)
        self.canvas.bind("<B3-Motion>",       self._on_right_drag)
        self.canvas.bind("<ButtonRelease-3>", self._on_right_release)
        self.canvas.bind("<MouseWheel>",      self._on_scroll)       # Windows
        self.canvas.bind("<Button-4>",        self._on_scroll)       # Linux up
        self.canvas.bind("<Button-5>",        self._on_scroll)       # Linux down
        self.canvas.bind("<Configure>",       self._on_canvas_resize)

    # ── image loading ─────────────────────────────────────────────────────────

    def _prompt_open(self):
        path = filedialog.askopenfilename(
            title="Select a map image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
                       ("All files", "*.*")])
        if path:
            self._load_image(path)

    def _load_image(self, path: str):
        try:
            img = Image.open(path)
            img.load()
        except Exception as exc:
            messagebox.showerror("Error", f"Cannot open image:\n{exc}")
            return

        self.image_path = path
        self.pil_image = img
        self.points.clear()
        self._reset_view()
        self._refresh_sidebar()
        self._render()
        self._set_status(f"Loaded: {Path(path).name}  "
                         f"({img.width} × {img.height} px)")

    def _reset_view(self):
        if self.pil_image is None:
            return
        cw = self.canvas.winfo_width()  or 700
        ch = self.canvas.winfo_height() or 500
        iw, ih = self.pil_image.size
        self._zoom = min(cw / iw, ch / ih) * 0.92
        self._offset_x = (cw - iw * self._zoom) / 2
        self._offset_y = (ch - ih * self._zoom) / 2

    # ── rendering ─────────────────────────────────────────────────────────────

    def _render(self, fast: bool = False):
        """
        Render the visible portion of the image onto the canvas.

        fast=True  — NEAREST resampling, used during drag/scroll (instant).
        fast=False — BILINEAR resampling, used for the settled final frame.

        Only the canvas-visible slice of the source image is resampled, so
        zooming in heavily never processes pixels outside the viewport.
        """
        if self.pil_image is None:
            return

        cw = self.canvas.winfo_width()  or 700
        ch = self.canvas.winfo_height() or 500
        iw, ih = self.pil_image.size

        # source rectangle in image-pixel space that maps onto the canvas
        src_x0 = max(0.0, -self._offset_x / self._zoom)
        src_y0 = max(0.0, -self._offset_y / self._zoom)
        src_x1 = min(float(iw), (cw - self._offset_x) / self._zoom)
        src_y1 = min(float(ih), (ch - self._offset_y) / self._zoom)

        if src_x1 <= src_x0 or src_y1 <= src_y0:
            # image is entirely off-screen
            self.canvas.delete("all")
            self._draw_crosshairs_only()
            return

        # destination size in canvas pixels
        dst_w = max(1, int((src_x1 - src_x0) * self._zoom))
        dst_h = max(1, int((src_y1 - src_y0) * self._zoom))

        crop = self.pil_image.crop((int(src_x0), int(src_y0),
                                    int(src_x1) + 1, int(src_y1) + 1))
        if fast:
            resample = Image.NEAREST
        elif self._zoom >= 1.0:
            resample = Image.NEAREST   # zoomed in: crisp pixels, no blur
        else:
            resample = Image.LANCZOS   # zoomed out: anti-alias the downscale
        tile = crop.resize((dst_w, dst_h), resample)

        draw_x = max(0.0, self._offset_x)
        draw_y = max(0.0, self._offset_y)

        self.canvas.delete("all")
        self._photo = ImageTk.PhotoImage(tile)
        self.canvas.create_image(draw_x, draw_y, anchor=tk.NW, image=self._photo)
        self._draw_crosshairs_only()

    def _draw_crosshairs_only(self):
        color = POINT_DONE if len(self.points) == REQUIRED_POINTS else POINT_CLR
        for i, pt in enumerate(self.points):
            cx, cy = self._img_to_canvas(pt["pixel"][0], pt["pixel"][1])
            self._draw_crosshair(cx, cy, i + 1, color)

    def _draw_crosshair(self, cx: float, cy: float, label: int, color: str):
        r = CROSSHAIR_R
        self.canvas.create_line(cx - r, cy, cx + r, cy, fill=color, width=2)
        self.canvas.create_line(cx, cy - r, cx, cy + r, fill=color, width=2)
        self.canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4,
                                outline=color, width=2)
        self.canvas.create_text(cx + r + 4, cy - r,
                                text=str(label), fill=color,
                                font=FONT_BOLD, anchor=tk.W)

    # ── coordinate math ───────────────────────────────────────────────────────

    def _img_to_canvas(self, ix: float, iy: float) -> tuple[float, float]:
        return ix * self._zoom + self._offset_x, iy * self._zoom + self._offset_y

    def _canvas_to_img(self, cx: float, cy: float) -> tuple[float, float]:
        return ((cx - self._offset_x) / self._zoom,
                (cy - self._offset_y) / self._zoom)

    # ── mouse events ──────────────────────────────────────────────────────────

    def _on_left_click(self, event):
        if self.pil_image is None:
            return
        if len(self.points) >= REQUIRED_POINTS:
            return
        ix, iy = self._canvas_to_img(event.x, event.y)
        iw, ih = self.pil_image.size
        if not (0 <= ix <= iw and 0 <= iy <= ih):
            return
        self._pending_click = (int(round(ix)), int(round(iy)))
        self._show_coord_popup(event.x_root, event.y_root)

    def _on_right_press(self, event):
        self._drag_start = (event.x, event.y)
        self.canvas.configure(cursor="fleur")

    def _on_right_drag(self, event):
        if self._drag_start is None:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._offset_x += dx
        self._offset_y += dy
        self._drag_start = (event.x, event.y)
        self._render(fast=True)
        self._schedule_settle()

    def _on_right_release(self, event):
        self._drag_start = None
        self.canvas.configure(cursor="crosshair")
        self._render(fast=False)
        self._cancel_settle()

    def _on_scroll(self, event):
        if self.pil_image is None:
            return
        factor = 1.12
        if event.num == 5 or event.delta < 0:
            factor = 1 / factor
        mx, my = event.x, event.y
        self._zoom *= factor
        self._zoom = max(0.05, min(self._zoom, 50.0))
        self._offset_x = mx - (mx - self._offset_x) * factor
        self._offset_y = my - (my - self._offset_y) * factor
        self._render(fast=True)
        self._schedule_settle()

    def _on_canvas_resize(self, event):
        if self.pil_image is not None:
            self._render(fast=False)

    def _schedule_settle(self):
        """Debounce: re-render at full quality 120 ms after last interaction."""
        if self._settle_job is not None:
            self.root.after_cancel(self._settle_job)
        self._settle_job = self.root.after(80, self._on_settle)

    def _cancel_settle(self):
        if self._settle_job is not None:
            self.root.after_cancel(self._settle_job)
            self._settle_job = None

    def _on_settle(self):
        self._settle_job = None
        self._render(fast=False)

    # ── coordinate input popup ────────────────────────────────────────────────

    def _show_coord_popup(self, root_x: int, root_y: int):
        popup = tk.Toplevel(self.root)
        popup.title("")
        popup.configure(bg=PANEL_BG)
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.grab_set()

        idx = len(self.points) + 1
        tk.Label(popup, text=f"Point {idx} of {REQUIRED_POINTS}",
                 font=FONT_TITLE, fg=HIGHLIGHT, bg=PANEL_BG).pack(
            padx=20, pady=(16, 4))

        px, py = self._pending_click
        tk.Label(popup, text=f"Pixel: ({px}, {py})",
                 font=FONT_MONO, fg=TEXT_DIM, bg=PANEL_BG).pack(padx=20)

        tk.Label(popup, text="GPS coordinates  (lng, lat):",
                 font=FONT_BOLD, fg=TEXT, bg=PANEL_BG).pack(
            padx=20, pady=(12, 2), anchor=tk.W)
        tk.Label(popup, text='e.g. 31.767811°, 35.194956°',
                 font=FONT_MONO, fg=TEXT_DIM, bg=PANEL_BG).pack(
            padx=20, anchor=tk.W)

        entry_var = tk.StringVar()
        entry = tk.Entry(popup, textvariable=entry_var,
                         font=FONT_MONO, bg=ACCENT, fg=TEXT,
                         insertbackground=HIGHLIGHT, relief=tk.FLAT,
                         highlightthickness=1,
                         highlightcolor=HIGHLIGHT,
                         highlightbackground=TEXT_DIM,
                         width=30)
        entry.pack(padx=20, pady=8, ipady=6, fill=tk.X)
        entry.focus_set()

        err_var = tk.StringVar()
        err_lbl = tk.Label(popup, textvariable=err_var, font=FONT_MONO,
                           fg=HIGHLIGHT, bg=PANEL_BG)
        err_lbl.pack(padx=20)

        btn_row = tk.Frame(popup, bg=PANEL_BG)
        btn_row.pack(padx=20, pady=(8, 16), fill=tk.X)

        def confirm():
            result = parse_gps(entry_var.get())
            if result is None:
                err_var.set("Invalid format. Try: 31.767811°, 35.194956°  (lng, lat)")
                entry.focus_set()
                return
            lat, lng = result
            self.points.append({
                "pixel": list(self._pending_click),
                "gps": {"lat": lat, "lng": lng},
            })
            popup.destroy()
            self._on_point_added()

        def cancel():
            self._pending_click = None
            popup.destroy()

        confirm_btn = tk.Button(btn_row, text="Confirm", command=confirm,
                                font=FONT_BOLD, fg=TEXT, bg=SUCCESS,
                                activebackground=HIGHLIGHT, activeforeground=TEXT,
                                relief=tk.FLAT, padx=14, pady=4, cursor="hand2")
        confirm_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))

        cancel_btn = tk.Button(btn_row, text="Cancel", command=cancel,
                               font=FONT_BOLD, fg=TEXT, bg=ACCENT,
                               activebackground=HIGHLIGHT, activeforeground=TEXT,
                               relief=tk.FLAT, padx=14, pady=4, cursor="hand2")
        cancel_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)

        entry.bind("<Return>", lambda e: confirm())
        entry.bind("<Escape>", lambda e: cancel())
        popup.protocol("WM_DELETE_WINDOW", cancel)

        # position near click but keep on screen
        popup.update_idletasks()
        w, h = popup.winfo_reqwidth(), popup.winfo_reqheight()
        sw, sh = popup.winfo_screenwidth(), popup.winfo_screenheight()
        x = min(root_x + 12, sw - w - 8)
        y = min(root_y + 12, sh - h - 8)
        popup.geometry(f"+{x}+{y}")

    # ── point lifecycle ───────────────────────────────────────────────────────

    def _on_point_added(self):
        self._render(fast=False)
        self._refresh_sidebar()
        n = len(self.points)
        if n < REQUIRED_POINTS:
            self._set_status(f"Point {n} placed. Click to place point {n+1}.")
        else:
            self._set_status(
                "All 4 points placed.  Use Save or Save As to export.")
            self._save_btn.configure(state=tk.NORMAL)
            self._saveas_btn.configure(state=tk.NORMAL)
            self._reset_btn.configure(state=tk.NORMAL)

    def _reset_points(self):
        self.points.clear()
        self._render(fast=False)
        self._refresh_sidebar()
        self._save_btn.configure(state=tk.DISABLED)
        self._saveas_btn.configure(state=tk.DISABLED)
        self._reset_btn.configure(state=tk.DISABLED)
        self._set_status("Points cleared. Click to place point 1.")

    # ── sidebar refresh ───────────────────────────────────────────────────────

    def _refresh_sidebar(self):
        n = len(self.points)
        self._progress_var.set(f"{n} / {REQUIRED_POINTS} points")

        # update progress bar
        self._prog_canvas.update_idletasks()
        bar_w = self._prog_canvas.winfo_width()
        filled = int(bar_w * n / REQUIRED_POINTS)
        self._prog_canvas.coords(self._prog_bar, 0, 0, filled, 6)

        for i, frame in enumerate(self._point_frames):
            if i < n:
                pt = self.points[i]
                px, py = pt["pixel"]
                lat = pt["gps"]["lat"]
                lng = pt["gps"]["lng"]
                frame._info_label.configure(
                    text=f"({px}, {py})\n{lat:.6f}°\n{lng:.6f}°",
                    fg=POINT_DONE if n == REQUIRED_POINTS else SUCCESS)
                frame._num_label.configure(fg=SUCCESS)
            else:
                frame._info_label.configure(text="—", fg=TEXT_DIM)
                frame._num_label.configure(fg=TEXT_DIM)

    # ── saving ────────────────────────────────────────────────────────────────

    def _build_payload(self) -> dict:
        return {
            "image": self.image_path,
            "calibration_points": self.points,
        }

    def _save(self):
        if not self.image_path:
            return
        stem = Path(self.image_path).stem
        out = Path(self.image_path).parent / f"{stem}_calibration.json"
        self._write(out)

    def _save_as(self):
        if not self.image_path:
            return
        stem = Path(self.image_path).stem
        initial = f"{stem}_calibration.json"
        path = filedialog.asksaveasfilename(
            title="Save calibration as…",
            initialfile=initial,
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if path:
            self._write(Path(path))

    def _write(self, path: Path):
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._build_payload(), fh, indent=2)
            self._set_status(f"Saved: {path}")
            messagebox.showinfo("Saved", f"Calibration saved to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc))

    # ── status bar ────────────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self._status_var.set(f"  {msg}")


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    image_arg = sys.argv[1] if len(sys.argv) > 1 else None
    root = tk.Tk()
    root.geometry("1100x680")

    # window icon colour (title bar colour on supported platforms)
    try:
        root.tk_setPalette(background=BG)
    except Exception:
        pass

    app = MapCalibratorApp(root, image_arg)
    root.mainloop()


if __name__ == "__main__":
    main()
