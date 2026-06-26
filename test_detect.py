#coding=utf-8
"""Script test chan doan detect: chup 1 frame, auto tach board (ROI), detect tat ca
linh kien, in best-score + so luong, luu anh overlay va vung pot de xem.

Chay: fpm_core\\.venv\\Scripts\\python.exe test_detect.py
"""
import sys, os, numpy as np, cv2
sys.path.insert(0, ".")
sys.path.insert(0, "fpm_core")
from camera_mv import Camera
from component_detector import ComponentLibrary
from segment_board import normalize_board

LIB = "fpm_core/templates_board"


def main():
    cam = Camera()
    print("cam:", cam.open())
    for _ in range(6):
        gray, rgb = cam.grab()
    cam.close()
    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    cv2.imwrite("test_frame.jpg", bgr)

    lib = ComponentLibrary(LIB).load()
    r = normalize_board(bgr)
    if r is None:
        print("KHONG tach duoc board!"); return
    sub, canon_bgr = r       # board da nan ve canonical
    x = y = 0
    print("board chuan hoa:", canon_bgr.shape)

    exp = lib.expected_counts()
    # ha nguong tat ca ve 0.3 de THAY best-score that du khong dat nguong
    for c in lib.components.values():
        c.cfg["score"] = 0.3
        c.cfg["max_pos"] = 5

    results, flipped = lib.detect_oriented(sub)
    if flipped:
        canon_bgr = cv2.rotate(canon_bgr, cv2.ROTATE_180)
        print("(board vao khung lat 180 do -> da tu xoay lai)")
    hits = {}
    for r in results:
        hits.setdefault(r["name"], []).append((r["score"], (r["center"][0] + x, r["center"][1] + y)))

    print(f'\n{"comp":10}{"best":>7}{"#>=0.7":>8}  vi tri best (canonical)')
    vis = canon_bgr.copy()
    for n in sorted(lib.components):
        lst = sorted(hits.get(n, []), reverse=True)
        best = lst[0][0] if lst else 0.0
        nb = sum(1 for s, _ in lst if s >= 0.7)
        pos = lst[0][1] if lst else None
        print(f'{n:10}{best:7.3f}{nb:8}  {pos}')
        if pos:
            cv2.circle(vis, (int(pos[0]), int(pos[1])), 18, (0, 0, 255), 2)
            cv2.putText(vis, f"{n} {best:.2f}", (int(pos[0]) + 8, int(pos[1])),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    cv2.imwrite("test_overlay.jpg", vis)
    cv2.imwrite("test_board.jpg", canon_bgr)
    print("\nDa luu: test_frame.jpg, test_overlay.jpg (canonical), test_board.jpg")


if __name__ == "__main__":
    main()
