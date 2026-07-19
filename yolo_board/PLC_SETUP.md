# Kết nối PLC S7 — cấu hình đã xác minh

Ghi lại cấu hình đã kiểm tra chạy được, để lần sau không phải dò lại từ đầu.

Cập nhật: 18/07/2026 · Nhánh `yolo-plc`

---

## 1. Thông số kết nối

| Mục | Giá trị |
|---|---|
| IP PLC | `192.168.0.1` |
| Rack / Slot | `0` / `1` |
| Cổng | TCP 102 (ISO-TSAP) |
| Interface PC | Ethernet 2 — `192.168.0.241/24` |
| MAC PLC | `30-b8-51-66-64-54` |
| Thư viện | `python-snap7` 3.0.0 |

Đã quét rack 0–1 × slot 0–3: **chỉ rack=0 slot=1 dùng được**, các tổ hợp khác bị reset kết nối.

> **Cảnh báo IP trùng.** `192.168.1.10` (giá trị mặc định trong
> [vision_serial_gui.py:386](../vision_serial_gui.py#L386) và ví dụ trong
> [plc_s7.py](plc_s7.py)) **trùng với IP Wi-Fi của máy tính này**. Ping tới đó
> vẫn "thành công" nhưng thực chất là ping chính máy mình, rất dễ hiểu nhầm là
> đã thấy PLC. Luôn dùng `192.168.0.1`.

---

## 2. Bắt buộc bật trong TIA Portal

Thiếu bước này thì **kết nối vẫn báo thành công nhưng mọi lệnh đọc/ghi đều lỗi** —
đây là cái bẫy đã mất nhiều thời gian nhất.

1. Device configuration → chọn CPU → **Properties → Protection & Security**
2. Tick **"Permit access with PUT/GET communication from remote partner"**
3. Compile → **Download to device** (phải tải cả cấu hình phần cứng, không chỉ chương trình)

### Cách nhận biết khi chưa bật

```
connected = True                    <-- gây hiểu nhầm là đã xong
S7 protocol error (class=0x81, code=0x04): This service is not implemented...
Read SZL failed: Object does not exist (0x0a)
```

Dấu hiệu quyết định: **cả vùng M, I, Q đều lỗi**. Các vùng này luôn tồn tại trên
mọi CPU, nên nếu chúng cũng lỗi thì chắc chắn là do PUT/GET, không phải do DB
thiếu hay do "Optimized block access".

---

## 3. Bảng ánh xạ ngõ ra (đã test thực tế)

Tên tag lấy từ TIA Portal, đã đối chiếu khớp với kết quả bấm thử từng ngõ.

| Địa chỉ | Tag TIA | Thiết bị |
|---|---|---|
| `%Q0.0` | `out_light_xanh` | Đèn báo xanh |
| `%Q0.1` | `out_line_vang` | Đèn báo vàng |
| `%Q0.2` | `out_line_do` | Đèn báo đỏ |
| `%Q0.3` | `out_warning_buzzer` | Còi cảnh báo |
| `%Q0.4` | `out_xilanh_day_pcb` | Xy lanh đẩy PCB |
| `%Q0.5` | `out_bang_chuyen` | Băng chuyền |
| `%Q0.6` | `out_xilanh_loai_bo_pcb` | Xy lanh loại bỏ PCB |

Bảng này cũng nằm ở [output_map.json](output_map.json), GUI tự nạp khi khởi động.

> Tag gốc trong TIA ghi là `out_warning _buzzer` (có dấu cách thừa giữa
> `warning` và `_buzzer`). Nên sửa lại trong TIA cho sạch.

---

## 4. Bảng ánh xạ ngõ vào (đã chốt)

| Địa chỉ | Tag TIA | Thiết bị |
|---|---|---|
| `%I0.0` | `in_stop_button` | Nút STOP |
| `%I0.1` | `in_start_button` | Nút START |
| `%I0.2` | `in_sensor_2` | Cảm biến 2 |
| `%I0.3` | `in_sensor_3` | Cảm biến 3 |
| `%I0.4` | `in_sensor_1` | Cảm biến 1 |
| `%I0.5` | `in_emergency_button` | Nút dừng khẩn cấp |

Bảng này cũng nằm ở [input_map.json](input_map.json).

> Lưu ý thứ tự: `in_sensor_1` nằm ở `%I0.4`, **không** phải `%I0.2`. Ba cảm biến
> không đánh số liên tiếp theo địa chỉ — dễ nhầm khi viết code, cần tra bảng.

---

## 5. Vùng nhớ đã kiểm tra

| Vùng | Trạng thái |
|---|---|
| I (Input) `IB0–IB7` | đọc được |
| Q (Output) `QB0–QB7` | đọc + ghi được |
| M (Merker) `MB0–MB3` | đọc được |
| DB1 | đọc được, **chỉ dài 2 byte** |
| DB2, DB5, DB10, DB100 | không tồn tại |

### Lưu ý quan trọng về DB1

DB1 hiện chỉ có **2 byte**. Đọc từ 4 byte trở lên báo `Invalid address (0x05)`.

Hàm `send_result()` trong [plc_s7.py](plc_s7.py) mặc định ghi INT tại
`byte_count=2` (chiếm byte 2–3) → **vượt kích thước DB1 và sẽ lỗi**. Trước khi
dùng hàm này cần một trong hai:

- Mở rộng DB1 lên tối thiểu 4 byte trong TIA Portal, hoặc
- Truyền tham số `byte_count` khác cho phù hợp

### Hàm không dùng được

`get_cpu_state()` và `get_cpu_info()` đều bị CPU từ chối (lỗi `0x8404` / `0x0a`).
S7-1200/1500 thường chặn các hàm chẩn đoán này qua PUT/GET — **đây là bình thường,
không phải lỗi cấu hình**. Muốn biết CPU đang RUN hay STOP thì nhìn đèn LED trên
CPU (xanh = RUN, vàng = STOP).

---

## 6. Các lệnh hay dùng

```powershell
# Test kết nối nhanh
.\.venv\Scripts\python.exe yolo_board\plc_s7.py --ip 192.168.0.1

# GUI test/map ngõ ra (khuyến nghị)
.\.venv\Scripts\python.exe yolo_board\test_outputs_gui.py

# Bản dòng lệnh
.\.venv\Scripts\python.exe yolo_board\test_outputs.py --ip 192.168.0.1
.\.venv\Scripts\python.exe yolo_board\test_outputs.py --dry-run   # không ghi PLC
```

Cả hai tool test đều mặc định bật **DRY-RUN / hỏi xác nhận** trước khi ghi thật,
tự tắt toàn bộ ngõ ra khi thoát, và có nút/lệnh **TẮT TOÀN BỘ** để dừng khẩn.

---

## 7. Vấn đề cần biết khi ghi ngõ ra

Nếu CPU đang **RUN** và chương trình PLC cũng điều khiển chính các ngõ Q đó, nó
sẽ **ghi đè lại sau mỗi vòng quét** → ngõ ra nhấp nháy hoặc không lên được. Đây
là bản chất của việc ghi trực tiếp vùng Q từ bên ngoài, không phải lỗi tool.

Khi gặp hiện tượng này, chọn một trong hai:
- Chuyển CPU sang **STOP** (lưu ý: nhiều CPU tự cắt ngõ ra khi STOP)
- Tạm khóa đoạn chương trình điều khiển ngõ ra đó trong TIA Portal

Trong GUI, cột đèn **"PLC"** đọc ngược trạng thái thật từ PLC mỗi 300ms — nếu đèn
không khớp với trạng thái nút thì đúng là đang bị chương trình ghi đè.

---

## 8. Môi trường Python

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Thư viện chính: `ultralytics` 8.4.83 · `torch` 2.12.1+cpu · `opencv-python` 4.13.0.92 ·
`PyQt5` 5.15.11 · `python-snap7` 3.0.0

Hai điểm cần lưu ý khi cài lại:

- `ultralytics` sẽ tự kéo `opencv-python` bản mới, gây **trùng với
  `opencv-python-headless`** ghi trong requirements → nên chỉ giữ **một** bản
  OpenCV duy nhất (`opencv-python==4.13.0.92`).
- `torch` đang là **bản CPU**. Máy có GPU NVIDIA thì cài bản CUDA từ pytorch.org.
- SDK camera MindVision (`mvsdk`) không cài qua pip, cần driver/DLL cài sẵn trên máy.
