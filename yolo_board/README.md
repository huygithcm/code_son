# YOLO Board Detection

Thay thế bước tách board bằng HSV (`segment_board.py`) bằng YOLO — robust hơn,
không còn phụ thuộc màu xanh / ánh sáng.

## Cài đặt (1 lần)

```
fpm_core\.venv\Scripts\python.exe -m pip install ultralytics
```

## Quy trình

### 1. Chụp data (~100–150 ảnh đa dạng)
```
fpm_core\.venv\Scripts\python.exe yolo_board\capture_dataset.py
```
- `SPACE`/`s` = lưu ảnh, `a` = bật/tắt auto-capture, `q` = thoát.
- **Đa dạng quan trọng hơn số lượng**: đổi vị trí, góc xoay, ánh sáng, khoảng cách.

### 2. Auto-gán nhãn bằng HSV cũ
```
fpm_core\.venv\Scripts\python.exe yolo_board\auto_label_hsv.py
```
- Xuất nhãn YOLO vào `dataset/labels/` + ảnh preview vào `dataset/preview/`.
- Mở `dataset/preview/`, ảnh nào box **sai** → sửa tay bằng LabelImg / Roboflow / CVAT.
- Ảnh in chữ "HSV FAIL" = HSV không tách được → bắt buộc gán tay.

### 3. Chia train/val + tạo board.yaml
```
fpm_core\.venv\Scripts\python.exe yolo_board\split_dataset.py --val 0.2
```

### 4. Train
```
fpm_core\.venv\Scripts\python.exe yolo_board\train.py --model yolo11n.pt --epochs 100
```
Model lưu ở `runs/board_yolo/weights/best.pt`.

### 5. Detect / tích hợp
```
fpm_core\.venv\Scripts\python.exe yolo_board\detect_board.py --live
```
Trong code dùng:
```python
from yolo_board.detect_board import board_bbox_yolo
bb = board_bbox_yolo(bgr)   # (x, y, w, h) — thay cho board_bbox() HSV
```

## File
| File | Việc |
|------|------|
| `capture_dataset.py` | Chụp loạt ảnh từ camera |
| `auto_label_hsv.py`  | Auto-gán nhãn bằng HSV cũ |
| `split_dataset.py`   | Chia train/val + tạo board.yaml |
| `train.py`           | Train YOLO |
| `detect_board.py`    | Detect bằng model đã train (live/ảnh) |
