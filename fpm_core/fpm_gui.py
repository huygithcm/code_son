r"""GUI cho fpm — Fastest Image Pattern Matching.

Chọn ảnh nguồn (Source) + ảnh mẫu (Template), chỉnh tham số, bấm Match;
ảnh nguồn được vẽ khung + tâm + score cho từng kết quả và hiển thị ngay.

Chạy:  .\.venv\Scripts\python.exe fpm_gui.py
"""
import os
import threading
import traceback

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from fpm_env import setup_fpm_dll_dirs, HERE

setup_fpm_dll_dirs()
import fpm  # noqa: E402

# Thư mục ảnh test mặc định (ưu tiên bản cục bộ trong fpm_core).
_DEFAULT_IMG_DIRS = [
    os.path.join(HERE, "Test Images"),
    os.path.join(os.path.dirname(HERE), "Test Images"),
]
DEFAULT_IMG_DIR = next((d for d in _DEFAULT_IMG_DIRS if os.path.isdir(d)), HERE)

BOX_COLORS = [
    (0, 220, 0), (255, 80, 80), (80, 160, 255), (255, 200, 0),
    (255, 0, 255), (0, 220, 220), (255, 140, 0), (160, 80, 255),
]


def load_image(path):
    """Đọc ảnh -> (PIL RGB để hiển thị, numpy gray uint8 để match)."""
    img = Image.open(path)
    rgb = img.convert("RGB")
    gray = np.asarray(img.convert("L"), dtype=np.uint8)
    return rgb, gray


class FpmGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("fpm — Image Pattern Matching")
        self.geometry("1180x760")
        self.minsize(900, 600)

        self.src_path = None
        self.tmpl_path = None
        self.src_rgb = None      # PIL RGB
        self.src_gray = None     # numpy gray
        self.tmpl_gray = None
        self._photo = None       # giữ ref ImageTk
        self._tmpl_photo = None

        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)

        # Panel trái: điều khiển
        left = ttk.Frame(root)
        left.pack(side="left", fill="y", padx=(0, 8))

        ttk.Label(left, text="Ảnh", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Button(left, text="Chọn ảnh nguồn (Source)…",
                   command=self.pick_source).pack(fill="x", pady=2)
        self.src_lbl = ttk.Label(left, text="(chưa chọn)", foreground="#666",
                                 wraplength=240)
        self.src_lbl.pack(anchor="w")
        ttk.Button(left, text="Chọn ảnh mẫu (Template)…",
                   command=self.pick_template).pack(fill="x", pady=(8, 2))
        self.tmpl_lbl = ttk.Label(left, text="(chưa chọn)", foreground="#666",
                                  wraplength=240)
        self.tmpl_lbl.pack(anchor="w")

        # Preview template
        self.tmpl_canvas = tk.Canvas(left, width=240, height=140, bg="#202020",
                                     highlightthickness=1, highlightbackground="#444")
        self.tmpl_canvas.pack(pady=6)

        ttk.Separator(left).pack(fill="x", pady=6)
        ttk.Label(left, text="Tham số", font=("Segoe UI", 10, "bold")).pack(anchor="w")

        self.var_score = tk.DoubleVar(value=0.5)
        self.var_maxpos = tk.IntVar(value=10)
        self.var_angle = tk.DoubleVar(value=30.0)
        self.var_simd = tk.BooleanVar(value=True)
        self.var_subpix = tk.BooleanVar(value=False)

        self._add_spin(left, "Score (0–1)", self.var_score, 0.0, 1.0, 0.05)
        self._add_spin(left, "Max targets", self.var_maxpos, 1, 100, 1)
        self._add_spin(left, "Tolerance angle (°)", self.var_angle, 0, 180, 5)
        ttk.Checkbutton(left, text="Dùng SIMD", variable=self.var_simd).pack(anchor="w")
        ttk.Checkbutton(left, text="Sub-pixel", variable=self.var_subpix).pack(anchor="w")

        ttk.Separator(left).pack(fill="x", pady=6)
        self.match_btn = ttk.Button(left, text="▶  Match", command=self.run_match)
        self.match_btn.pack(fill="x", pady=2)
        ttk.Button(left, text="Lưu ảnh kết quả…",
                   command=self.save_result).pack(fill="x", pady=2)

        ttk.Separator(left).pack(fill="x", pady=6)
        ttk.Label(left, text="Kết quả", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.result_box = tk.Text(left, width=34, height=14, font=("Consolas", 9))
        self.result_box.pack(fill="both", expand=True)

        # Panel phải: ảnh đã xử lý
        right = ttk.Frame(root)
        right.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(right, bg="#101010", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._redraw_canvas())

        self.status = ttk.Label(self, text="Sẵn sàng.", relief="sunken", anchor="w")
        self.status.pack(side="bottom", fill="x")

        self._result_image = None  # PIL RGB đã vẽ khung (full-res, để lưu)

    def _add_spin(self, parent, label, var, lo, hi, step):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, width=18).pack(side="left")
        ttk.Spinbox(row, from_=lo, to=hi, increment=step, textvariable=var,
                    width=8).pack(side="right")

    # ---------------- Actions ----------------
    def pick_source(self):
        path = filedialog.askopenfilename(
            title="Chọn ảnh nguồn", initialdir=DEFAULT_IMG_DIR,
            filetypes=[("Ảnh", "*.bmp *.png *.jpg *.jpeg *.tif *.tiff"), ("Tất cả", "*.*")])
        if not path:
            return
        try:
            self.src_rgb, self.src_gray = load_image(path)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được ảnh:\n{e}")
            return
        self.src_path = path
        self.src_lbl.config(text=os.path.basename(path))
        self._result_image = self.src_rgb.copy()
        self._redraw_canvas()
        self.status.config(text=f"Ảnh nguồn: {self.src_gray.shape[1]}x{self.src_gray.shape[0]}")

    def pick_template(self):
        path = filedialog.askopenfilename(
            title="Chọn ảnh mẫu", initialdir=DEFAULT_IMG_DIR,
            filetypes=[("Ảnh", "*.bmp *.png *.jpg *.jpeg *.tif *.tiff"), ("Tất cả", "*.*")])
        if not path:
            return
        try:
            tmpl_rgb, self.tmpl_gray = load_image(path)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được ảnh:\n{e}")
            return
        self.tmpl_path = path
        self.tmpl_lbl.config(text=os.path.basename(path))
        self._show_template(tmpl_rgb)

    def _show_template(self, tmpl_rgb):
        cw, ch = 240, 140
        im = tmpl_rgb.copy()
        im.thumbnail((cw, ch))
        self._tmpl_photo = ImageTk.PhotoImage(im)
        self.tmpl_canvas.delete("all")
        self.tmpl_canvas.create_image(cw // 2, ch // 2, image=self._tmpl_photo)

    def _make_params(self):
        p = fpm.MatchParams()
        p.score = float(self.var_score.get())
        p.max_pos = int(self.var_maxpos.get())
        p.tolerance_angle = float(self.var_angle.get())
        p.use_simd = bool(self.var_simd.get())
        p.sub_pixel = bool(self.var_subpix.get())
        return p

    def run_match(self):
        if self.src_gray is None or self.tmpl_gray is None:
            messagebox.showwarning("Thiếu ảnh", "Hãy chọn cả ảnh nguồn và ảnh mẫu.")
            return
        self.match_btn.config(state="disabled")
        self.status.config(text="Đang match…")
        params = self._make_params()
        threading.Thread(target=self._match_worker, args=(params,), daemon=True).start()

    def _match_worker(self, params):
        try:
            results = fpm.match(self.src_gray, self.tmpl_gray, params)
            err = None
        except Exception:
            results, err = None, traceback.format_exc()
        self.after(0, self._match_done, results, err)

    def _match_done(self, results, err):
        self.match_btn.config(state="normal")
        if err is not None:
            self.status.config(text="Lỗi khi match.")
            messagebox.showerror("Match thất bại", err)
            return
        self._draw_results(results)
        self._show_results_text(results)
        self.status.config(text=f"Xong — {len(results)} kết quả.")

    def _draw_results(self, results):
        img = self.src_rgb.copy()
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", max(14, img.width // 80))
        except Exception:
            font = ImageFont.load_default()
        lw = max(2, img.width // 500)
        for i, r in enumerate(results):
            color = BOX_COLORS[i % len(BOX_COLORS)]
            (lt, rt, rb, lb) = r["corners"]
            pts = [tuple(lt), tuple(rt), tuple(rb), tuple(lb), tuple(lt)]
            draw.line(pts, fill=color, width=lw)
            cx, cy = r["center"]
            rdot = lw + 2
            draw.ellipse([cx - rdot, cy - rdot, cx + rdot, cy + rdot], fill=color)
            label = f"#{i} {r['score']:.3f} {r['angle']:.1f}°"
            draw.text((lt[0] + 3, lt[1] + 3), label, fill=color, font=font)
        self._result_image = img
        self._redraw_canvas()

    def _redraw_canvas(self):
        img = self._result_image if self._result_image is not None else self.src_rgb
        self.canvas.delete("all")
        if img is None:
            return
        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)
        disp = img.copy()
        disp.thumbnail((cw, ch))
        self._photo = ImageTk.PhotoImage(disp)
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo)

    def _show_results_text(self, results):
        self.result_box.delete("1.0", "end")
        if not results:
            self.result_box.insert("end", "Không tìm thấy match nào.\n")
            return
        for i, r in enumerate(results):
            cx, cy = r["center"]
            self.result_box.insert(
                "end",
                f"#{i}  score={r['score']:.4f}\n"
                f"    angle={r['angle']:.2f}°  center=({cx:.1f},{cy:.1f})\n")

    def save_result(self):
        if self._result_image is None:
            messagebox.showinfo("Chưa có ảnh", "Chưa có ảnh kết quả để lưu.")
            return
        path = filedialog.asksaveasfilename(
            title="Lưu ảnh kết quả", defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("BMP", "*.bmp")])
        if not path:
            return
        self._result_image.save(path)
        self.status.config(text=f"Đã lưu: {path}")


if __name__ == "__main__":
    FpmGui().mainloop()
