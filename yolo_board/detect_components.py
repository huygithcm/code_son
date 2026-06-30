#coding=utf-8
"""Detect & dem linh kien bang YOLO (thay cho template matching fpm).

Model YOLO da train voi NHIEU class (moi loai linh kien 1 class). Script:
  - chay model -> dem so luong moi class tim duoc
  - so voi so luong ky vong (expected.json) -> PASS/FAIL tung loai + tong

expected.json (tao tay, ten class lay tu data.yaml cua Roboflow):
    { "cap_220_35v": 1, "ind_470": 1, "ic": 1, "cap_100_50v": 1 }
Thieu class nao trong file => mac dinh ky vong = 1.

Chay tren anh:
    fpm_core\\.venv\\Scripts\\python.exe yolo_board\\detect_components.py --images a.jpg b.jpg
Chay tren camera (live, tkinter):
    fpm_core\\.venv\\Scripts\\python.exe yolo_board\\detect_components.py --live
"""
import os
import sys
import json
import glob
import argparse
from collections import Counter

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

DEFAULT_W = os.path.join(HERE, "weights", "best.pt")
if not os.path.exists(DEFAULT_W):
    DEFAULT_W = os.path.join(HERE, "runs", "board_yolo", "weights", "best.pt")
EXPECTED_JSON = os.path.join(HERE, "expected.json")

_MODEL = None


def load_model(weights=DEFAULT_W):
    global _MODEL
    if _MODEL is None:
        from ultralytics import YOLO
        if not os.path.exists(weights):
            raise FileNotFoundError(f"Chua co model: {weights}. Train truoc.")
        _MODEL = YOLO(weights)
    return _MODEL


def load_expected():
    if os.path.exists(EXPECTED_JSON):
        with open(EXPECTED_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {}


def detect(bgr, conf=0.25, weights=DEFAULT_W, roi=None, imgsz=640):
    """Tra ve list dict: {name, score, box=(x0,y0,x1,y1)} cho moi linh kien.
    roi=(x0,y0,x1,y1): chi detect trong vung nay (crop). Vi YOLO luon resize ve
    imgsz co dinh, crop ROI giup GIAM imgsz ma van du chi tiet -> NHANH HON.
    Vd: ROI + imgsz=416 nhanh ~3x so voi full + imgsz=960.
    Toa do box luon tra ve theo anh GOC (da cong offset ROI)."""
    model = load_model(weights)
    ox, oy = 0, 0
    img = bgr
    if roi is not None:
        H, W = bgr.shape[:2]
        x0, y0, x1, y1 = roi
        x0 = max(0, min(int(x0), W - 1)); y0 = max(0, min(int(y0), H - 1))
        x1 = max(x0 + 1, min(int(x1), W)); y1 = max(y0 + 1, min(int(y1), H))
        img = bgr[y0:y1, x0:x1]
        ox, oy = x0, y0
    res = model.predict(img, conf=conf, imgsz=imgsz, verbose=False)[0]
    names = res.names                       # {id: ten_class}
    out = []
    if res.boxes is not None:
        for b, c, k in zip(res.boxes.xyxy.cpu().numpy(),
                           res.boxes.conf.cpu().numpy(),
                           res.boxes.cls.cpu().numpy().astype(int)):
            x0, y0, x1, y1 = map(int, b)
            out.append({"name": names[k], "score": float(c),
                        "box": (x0 + ox, y0 + oy, x1 + ox, y1 + oy)})
    return out


def evaluate(dets, expected, default_exp=1):
    """So luong tim duoc vs ky vong -> dict {name: (found, exp, ok)} + ok_all.
    OK khi found == exp (so luong DUNG: thieu hay thua deu NG).
    Class khong khai trong expected.json -> ky vong = default_exp (mac dinh 1).
    Vd expected.json: {"capacitor": 2} -> capacitor can dung 2, cac class khac can 1."""
    counts = Counter(d["name"] for d in dets)
    keys = set(counts) | set(expected)
    rows, ok_all = {}, True
    for name in sorted(keys):
        found = counts.get(name, 0)
        exp = int(expected.get(name, default_exp))
        ok = (found == exp)
        ok_all &= ok
        rows[name] = (found, exp, ok)
    return rows, ok_all


def draw(bgr, dets):
    vis = bgr.copy()
    for d in dets:
        x0, y0, x1, y1 = d["box"]
        cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 255, 0), 2)
        cv2.putText(vis, f'{d["name"]} {d["score"]:.2f}', (x0, max(18, y0 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    return vis


def _print_report(name, rows, ok_all):
    print(f"\n{name}:")
    for n, (found, exp, ok) in rows.items():
        print(f"  {n:16} found={found} exp={exp}  {'PASS' if ok else 'FAIL'}")
    print(f"  => TONG: {'PASS' if ok_all else 'FAIL'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=DEFAULT_W)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--images", nargs="*")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--roi", default=None,
                    help="vung detect 'x0,y0,x1,y1' (toa do anh goc) -> dung imgsz nho")
    ap.add_argument("--imgsz", type=int, default=640,
                    help="kich thuoc resize cua YOLO. ROI + imgsz nho (416/320) = nhanh nhat")
    ap.add_argument("--roi-margin", type=int, default=80,
                    help="margin (px) noi rong Auto ROI (HSV) de khong cat linh kien mep board")
    args = ap.parse_args()

    expected = load_expected()
    roi = tuple(int(v) for v in args.roi.split(",")) if args.roi else None

    if args.live:
        _run_live(args.weights, args.conf, expected, roi, args.imgsz, args.roi_margin)
        return

    imgs = args.images or sorted(glob.glob(os.path.join(HERE, "dataset", "images", "*.jpg")))
    out = os.path.join(HERE, "pred_out"); os.makedirs(out, exist_ok=True)
    for p in imgs:
        bgr = cv2.imread(p)
        if bgr is None:
            continue
        dets = detect(bgr, args.conf, args.weights, roi, args.imgsz)
        rows, ok_all = evaluate(dets, expected)
        _print_report(os.path.basename(p), rows, ok_all)
        cv2.imwrite(os.path.join(out, os.path.basename(p)), draw(bgr, dets))
    print("\nAnh ket qua trong", out)


def _run_live(weights, conf, expected, roi=None, imgsz=640, roi_margin=80):
    """Live view bang tkinter (venv dung opencv headless, khong co cv2.imshow).
    Keo chuot tren anh de chon ROI (chi detect trong vung do -> nhanh hon).
    roi truyen vao la toa do anh GOC; trong GUI ta luu lai theo anh goc."""
    from PIL import Image, ImageTk
    import tkinter as tk
    from tkinter import ttk
    from camera_mv import Camera, mvsdk

    from segment_board import board_bbox     # tach board bang HSV (mau xanh)

    cam = Camera(); cam.open()
    root = tk.Tk(); root.title("YOLO detect linh kien")
    bar = tk.Frame(root); bar.pack(fill="x")

    def auto_roi_hsv():
        """Tu dong dat ROI quanh board bang nguong HSV (segment_board).
        Noi rong ROI (margin + 8% moi chieu) de KHONG cat linh kien o mep board."""
        if st.get("bgr") is None:
            return
        bgr = st["bgr"]; H, W = bgr.shape[:2]
        bb = board_bbox(bgr, margin=roi_margin, scale=1.0)   # full-res cho chinh xac
        if bb is None:
            info.config(text="HSV: khong tach duoc board", fg="#c62828")
            return
        x, y, w, h = bb
        ex, ey = int(w * 0.08), int(h * 0.08)               # noi them theo ti le
        x0 = max(0, x - ex); y0 = max(0, y - ey)
        x1 = min(W, x + w + ex); y1 = min(H, y + h + ey)
        st["roi"] = (x0, y0, x1, y1)

    tk.Button(bar, text="Auto ROI (HSV)", command=auto_roi_hsv,
              bg="#1565c0", fg="white").pack(side="left", padx=4, pady=4)
    tk.Button(bar, text="Xoa ROI", command=lambda: st.update(roi=None)).pack(side="left", padx=4, pady=4)
    tk.Label(bar, text="Keo chuot de chon ROI, hoac Auto ROI (HSV)").pack(side="left", padx=8)
    body = tk.Frame(root); body.pack(fill="both", expand=True)
    canvas = tk.Canvas(body, bg="gray20", cursor="cross"); canvas.pack(side="left", fill="both", expand=True)

    # ----- bang ket qua PASS/FAIL (cap nhat moi frame) -----
    panel = tk.Frame(body); panel.pack(side="right", fill="y")
    tree = ttk.Treeview(panel, columns=("found", "exp", "st"),
                        show="tree headings", height=20)
    tree.heading("#0", text="Linh kien"); tree.column("#0", width=140)
    for c, t, w in (("found", "found", 60), ("exp", "exp", 50), ("st", "trang thai", 80)):
        tree.heading(c, text=t); tree.column(c, width=w, anchor="center")
    tree.tag_configure("PASS", background="#c8e6c9")
    tree.tag_configure("FAIL", background="#ffcdd2")
    tree.pack(fill="y", expand=True, padx=4, pady=4)
    total = tk.Label(panel, text="", font=("Segoe UI", 14, "bold")); total.pack(pady=4)
    fps_lbl = tk.Label(panel, text="", font=("Consolas", 10)); fps_lbl.pack()

    def info_config(text, fg="#000"):       # tuong thich auto_roi_hsv cu (bao loi HSV)
        total.config(text=text, fg=fg)
    info = type("X", (), {"config": staticmethod(lambda text="", fg="#000": info_config(text, fg))})()

    def update_table(rows, ok_all, ms):
        for i in tree.get_children():
            tree.delete(i)
        for n, (found, exp, ok) in rows.items():
            tree.insert("", "end", text=n, values=(found, exp, "PASS" if ok else "FAIL"),
                        tags=(("PASS" if ok else "FAIL"),))
        total.config(text=("TONG: PASS" if ok_all else "TONG: FAIL"),
                     fg=("#2e7d32" if ok_all else "#c62828"))
        fps_lbl.config(text=f"{ms:.0f} ms/frame  (~{1000/ms:.1f} FPS)" if ms > 0 else "")

    st = {"img": None, "roi": roi, "scale": 1.0, "drag": None, "tmp": None, "bgr": None}

    def on_down(e):
        st["drag"] = (e.x, e.y)
        if st["tmp"]:
            canvas.delete(st["tmp"])
        st["tmp"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#00e5ff", width=2)

    def on_move(e):
        if st["drag"] and st["tmp"]:
            canvas.coords(st["tmp"], st["drag"][0], st["drag"][1], e.x, e.y)

    def on_up(e):
        if not st["drag"]:
            return
        (x0, y0), (x1, y1) = st["drag"], (e.x, e.y)
        st["drag"] = None
        bx0, bx1 = sorted((x0, x1)); by0, by1 = sorted((y0, y1))
        if bx1 - bx0 < 8 or by1 - by0 < 8:
            return
        s = st["scale"] or 1.0
        st["roi"] = (int(bx0 / s), int(by0 / s), int(bx1 / s), int(by1 / s))

    canvas.bind("<ButtonPress-1>", on_down)
    canvas.bind("<B1-Motion>", on_move)
    canvas.bind("<ButtonRelease-1>", on_up)

    def tick():
        import time
        try:
            _, rgb = cam.grab()
            bgr = np.ascontiguousarray(rgb[:, :, ::-1])
            st["bgr"] = bgr                  # cho Auto ROI (HSV) dung frame hien tai
            t0 = time.time()
            dets = detect(bgr, conf, weights, st["roi"], imgsz)
            ms = (time.time() - t0) * 1000
            rows, ok_all = evaluate(dets, expected)
            vis = cv2.cvtColor(draw(bgr, dets), cv2.COLOR_BGR2RGB)
            s = min(900 / vis.shape[1], 1.0)
            st["scale"] = s
            disp = cv2.resize(vis, (int(vis.shape[1] * s), int(vis.shape[0] * s)))
            st["img"] = ImageTk.PhotoImage(Image.fromarray(np.ascontiguousarray(disp)))
            canvas.config(width=disp.shape[1], height=disp.shape[0])
            canvas.delete("all"); canvas.create_image(0, 0, anchor="nw", image=st["img"])
            if st["roi"]:
                rx0, ry0, rx1, ry1 = [int(v * s) for v in st["roi"]]
                canvas.create_rectangle(rx0, ry0, rx1, ry1, outline="#00e5ff", width=2, dash=(6, 4))
            update_table(rows, ok_all, ms)
        except mvsdk.CameraException:
            pass
        root.after(20, tick)

    def on_close():
        cam.close(); root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)
    tick(); root.mainloop()


if __name__ == "__main__":
    main()
