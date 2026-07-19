# Kế hoạch chu trình — PLC + GUI

Thiết kế chu trình kiểm tra PCB tự động. Đọc kèm [PLC_SETUP.md](PLC_SETUP.md)
(thông số kết nối, bảng I/O đã chốt).

Cập nhật: 18/07/2026 · Nhánh `yolo-plc`

---

## 1. Tóm tắt chu trình

```
KHỞI TẠO: băng chuyền đứng yên
   │
   ├─ Nhấn START
   │
   ▼
[1] Xy lanh 1 (%Q0.4) đẩy phôi ra băng chuyền
   │
   ▼
[2] Cảm biến 1 (%I0.4) xác nhận có board trên băng chuyền
   │
   ▼
[3] Băng chuyền chạy → PCB tới cảm biến 2 (%I0.2)
   │
   ▼
[4] DỪNG băng chuyền → PC chụp ảnh + chạy YOLO
   │
   ├── PASS ──► [5a] Băng chuyền chạy, PCB đi qua cảm biến 3 → hết chu trình
   │
   └── FAIL ──► [5b] Băng chuyền chạy tới cảm biến 3 (%I0.3)
                     → DỪNG → xy lanh 2 loại bỏ (%Q0.6) ON 5 giây → OFF
   │
   ▼
Quay lại [1] cho phôi kế tiếp
```

---

## 2. I/O sử dụng

### Ngõ vào

| Địa chỉ | Tag | Vai trò trong chu trình |
|---|---|---|
| `%I0.0` | `in_stop_button` | Dừng chu trình (NC) |
| `%I0.1` | `in_start_button` | Khởi động chu trình |
| `%I0.2` | `in_sensor_2` | **Vị trí chụp ảnh** — PCB tới đây thì dừng băng chuyền |
| `%I0.3` | `in_sensor_3` | **Vị trí loại bỏ** — nơi xy lanh đẩy PCB lỗi ra |
| `%I0.4` | `in_sensor_1` | Xác nhận phôi đã lên băng chuyền |
| `%I0.5` | `in_emergency_button` | Dừng khẩn cấp (NC) |

### Ngõ ra

| Địa chỉ | Tag | Vai trò |
|---|---|---|
| `%Q0.0` | `out_light_xanh` | Đang chạy bình thường / kết quả PASS |
| `%Q0.1` | `out_line_vang` | Cảnh báo — PC không phản hồi, timeout |
| `%Q0.2` | `out_line_do` | Kết quả FAIL / lỗi hệ thống |
| `%Q0.3` | `out_warning_buzzer` | Còi báo khi có PCB lỗi |
| `%Q0.4` | `out_xilanh_day_pcb` | **Xy lanh 1** — đẩy phôi ra băng chuyền |
| `%Q0.5` | `out_bang_chuyen` | Băng chuyền |
| `%Q0.6` | `out_xilanh_loai_bo_pcb` | **Xy lanh 2** — loại bỏ PCB lỗi tại cảm biến 3 |

Hệ thống có đúng **2 xy lanh**: xy lanh 1 đẩy phôi vào, xy lanh 2 loại phôi lỗi ra.

---

## 3. Máy trạng thái (PLC)

Đây là phần chạy trên PLC. Mỗi bước là một trạng thái, chỉ chuyển khi thoả điều kiện.

| # | Trạng thái | Ngõ ra bật | Điều kiện chuyển tiếp | Trạng thái kế |
|---|---|---|---|---|
| S0 | `KHOI_TAO` | — (tất cả OFF) | Nhấn START | S1 |
| S1 | `DAY_PHOI` | `%Q0.4` — xy lanh 1, `%Q0.5` | Hết `T_day_phoi` (1 s) | S2 |
| S2 | `CHO_SENSOR1` | `%Q0.5` | `%I0.4` = 1 (có board) | S3 |
| S3 | `CHAY_TOI_S2` | `%Q0.5` | `%I0.2` = 1 (tới vị trí chụp) | S4 |
| S4 | `CHO_KET_QUA` | — (băng chuyền DỪNG) | `DONE` = 1 từ PC | S5 |
| S5 | `PHAN_LOAI` | — | `PASS` → S6 · `FAIL` → S7 | S6 / S7 |
| S6 | `CHO_PASS_QUA` | `%Q0.5` | `%I0.3` sườn lên (0 → 1) | S1 |
| S7 | `CHAY_TOI_S3` | `%Q0.5` | `%I0.3` sườn lên (0 → 1) | S8 |
| S8 | `LOAI_BO` | `%Q0.6` — xy lanh 2 (băng chuyền DỪNG) | Hết `T_loai_bo` (5 s) | S1 |

> **Không có trạng thái chờ xy lanh thu về.** Xy lanh van đơn tự rút khi ngõ ra
> tắt, và chu trình đã có sẵn hơn 10 giây trước lần va chạm tiềm tàng kế tiếp —
> thừa cho thao tác rút dưới 1 giây. Xem
> [PLC_LADDER.md mục 7.2](PLC_LADDER.md#72--vì-sao-không-có-trạng-thái-chờ-xy-lanh-thu-về).

### Bộ định thời

| Tên | Giá trị đề xuất | Ghi chú |
|---|---|---|
| `T_day_phoi` — kích xy lanh 1 | 1.0 s | Kích rồi chạy tiếp, không chờ thu về |
| `T_loai_bo` — kích xy lanh 2 | **5.0 s** (theo yêu cầu) | Xem cảnh báo mục 7 |
| `T_cho_pc` — timeout chờ PC | 3.0 s | Quá hạn → S99 |
| `T_ket_phoi` — timeout kẹt phôi | 15 s | Áp dụng riêng cho S2, S3, S7 |
| T_TIMEOUT — chờ PC | 3.0 s | Quá hạn → S_LOI |

### Trạng thái lỗi

| # | Trạng thái | Vào khi | Ngõ ra | Thoát |
|---|---|---|---|---|
| S_LOI | `LOI_PC` | Ở S5 quá T_TIMEOUT không có `DONE` | `%Q0.1` + `%Q0.3` | Nhấn STOP rồi START lại |

Không có phản hồi từ PC thì **không được đoán PASS**. Luôn coi là lỗi và dừng máy.

---

## 4. Giao thức DB1

> **Bố trí dưới đây đã được thay thế.** Bản chính thức đầy đủ (16 byte, có thêm
> bộ đếm PASS/FAIL và cờ trạng thái) nằm ở
> [PLC_LADDER.md mục 3](PLC_LADDER.md#3-cấu-trúc-db1--giao-tiếp-với-máy-tính).
> Phần dưới giữ lại để hiểu nguyên lý bắt tay.

DB1 hiện chỉ **2 byte** — phải mở rộng trong TIA Portal và **tắt
"Optimized block access"**.

| Địa chỉ | Kiểu | Tên | Ai ghi | Ý nghĩa |
|---|---|---|---|---|
| `DB1.DBX0.0` | Bool | `TRIGGER` | PLC | PCB đã vào vị trí, yêu cầu PC chụp |
| `DB1.DBX0.1` | Bool | `DONE` | PC | PC đã xử lý xong, kết quả đã sẵn sàng |
| `DB1.DBX0.2` | Bool | `PASS` | PC | Kết quả đạt |
| `DB1.DBX0.3` | Bool | `FAIL` | PC | Kết quả không đạt |
| `DB1.DBX0.4` | Bool | `PC_ALIVE` | PC | Nhịp tim, PC đảo bit mỗi giây |
| `DB1.DBX1.0` | Bool | `TRANG_THAI_CHAY` | PLC | Chu trình đang chạy (cho GUI hiển thị) |
| `DB1.DBW2` | Int | `SO_LOI` | PC | Số lỗi phát hiện được |
| `DB1.DBW4` | Int | `MA_LOI` | PC | Mã loại lỗi |
| `DB1.DBW6` | Int | `DEM_SAN_PHAM` | PLC | Tổng số PCB đã kiểm tra |

### Trình tự bắt tay

```
PLC:  TRIGGER = 1          (PCB đã dừng tại cảm biến 2)
PC:   thấy TRIGGER = 1  →  chụp ảnh  →  chạy YOLO
PC:   ghi SO_LOI, MA_LOI  →  ghi PASS hoặc FAIL  →  DONE = 1
PLC:  thấy DONE = 1  →  đọc PASS/FAIL  →  hành động
PLC:  TRIGGER = 0
PC:   thấy TRIGGER = 0  →  DONE = 0, PASS = 0, FAIL = 0   (sẵn sàng phôi kế)
```

**Thứ tự ghi rất quan trọng:** PC phải ghi `SO_LOI`/`MA_LOI` và `PASS`/`FAIL`
**trước**, rồi mới set `DONE = 1` sau cùng. Nếu set `DONE` trước, PLC có thể đọc
được dữ liệu của phôi trước đó.

---

## 5. Phần mềm GUI làm gì

Vòng lặp chính (polling DB1 mỗi 100–200 ms):

1. Đọc `TRIGGER`. Nếu `TRIGGER = 1` và chưa xử lý phôi này:
   - Chụp ảnh từ camera MindVision
   - Chạy YOLO ([detect_components.py](detect_components.py))
   - So với `expected.json` → tính PASS/FAIL và số lỗi
   - Ghi `SO_LOI`, `MA_LOI` → ghi `PASS`/`FAIL` → set `DONE = 1`
   - Lưu ảnh + kết quả vào log
2. Khi thấy `TRIGGER = 0` → clear `DONE`, `PASS`, `FAIL`
3. Song song: đảo bit `PC_ALIVE` mỗi giây
4. Hiển thị: ảnh có khung nhận diện, kết quả, số đếm, trạng thái kết nối

### GUI **không** làm

- Không điều khiển trực tiếp băng chuyền hay xy lanh trong chế độ tự động
- Không xử lý E-Stop
- Không quyết định thời điểm dừng băng chuyền

Toàn bộ điều khiển cơ cấu thuộc về PLC. GUI chỉ đưa ra phán quyết PASS/FAIL.

Riêng [test_outputs_gui.py](test_outputs_gui.py) có điều khiển trực tiếp ngõ ra —
đó là **công cụ bảo trì**, chỉ dùng khi máy dừng, không dùng lúc đang sản xuất.

---

## 6. Phần cứng / PLC làm gì

- Mạch tự giữ băng chuyền: START bật, STOP và E-Stop cắt
- Toàn bộ máy trạng thái ở mục 3
- Các bộ định thời T1–T4, T_TIMEOUT
- Giám sát `PC_ALIVE`: mất nhịp tim quá 3 s → báo đèn vàng, không nhận phôi mới
- Đèn báo và còi
- Bộ đếm sản phẩm

Nguyên tắc: **PC treo hoặc mất mạng thì PLC vẫn phải tự dừng an toàn được.**

---

## 7. Những điểm cần rà lại trước khi chạy

### Thời gian loại bỏ 5 giây là dài

Xy lanh thông thường chỉ cần 0.5–1 giây để đẩy xong. Giữ 5 giây làm giảm năng
suất đáng kể (mỗi PCB lỗi mất thêm ~4 s) và giữ áp lên xy lanh lâu không cần
thiết. Đề xuất đặt T3 thành **biến chỉnh được trong HMI/GUI**, khởi đầu 5 s theo
yêu cầu rồi giảm dần khi chạy thử. Nếu xy lanh có **cảm biến hành trình**, nên
dùng tín hiệu đó thay cho thời gian — chắc chắn hơn nhiều.

### Nút STOP và E-Stop phải là tiếp điểm NC

Nếu đấu NO, một sợi dây đứt sẽ làm nút dừng mất tác dụng mà không ai biết.
Kiểm tra: khi **không** nhấn, `%I0.0` và `%I0.5` phải = **1**.

### E-Stop phải cắt cứng bằng phần cứng

Đi qua safety relay/contactor cắt nguồn cơ cấu chấp hành, **song song** với việc
vào `%I0.5` để PLC biết mà báo trạng thái. Chỉ dựa vào logic phần mềm là không đủ:
CPU treo hoặc relay dính tiếp điểm thì phần mềm không cứu được.

### Phân biệt hai loại dừng băng chuyền

- **Dừng an toàn** (STOP, E-Stop) → mất tự giữ, phải bấm START lại
- **Dừng theo chu trình** (đang chụp ảnh, đang loại bỏ) → tạm dừng, tự chạy tiếp

Phải là hai biến riêng. Gộp chung thì mỗi phôi lại phải bấm START.

### Bắt sườn lên tại cảm biến 3

Cả S7 (PASS) và S8 (FAIL) đều bắt **sườn lên** của `%I0.3` (0 → 1), tức thời
điểm PCB **vừa tới** cảm biến 3.

Ưu điểm: tín hiệu chắc chắn, không sợ bỏ lỡ. Bắt sườn xuống có rủi ro PCB dừng
ngay trên cảm biến (băng chuyền đã dừng) → sườn xuống không bao giờ tới → máy
treo ở S7.

**Hệ quả cần xử lý:** ở S7, khi bắt được sườn lên thì PCB PASS **vẫn còn nằm
trên băng chuyền** tại cảm biến 3, chưa ra khỏi máy. Chu trình quay về S1 đẩy
phôi mới ngay lúc đó. Vì vậy **băng chuyền phải tiếp tục chạy trong S1 và S2**
để tấm PASS thoát ra, nếu không nó sẽ nằm lại và cảm biến 3 vẫn giữ mức 1 →
chu trình kế tiếp hiểu sai trạng thái.

Xem bảng trạng thái: S1 và S2 đã bật `%Q0.5` vì lý do này.

---

## 8. Câu hỏi còn để mở

1. **Cảm biến 1 (`%I0.4`) đặt ở đâu?** Ngay sau xy lanh 1, hay ở đầu băng chuyền?
2. **Xy lanh có cảm biến hành trình không?** Nếu có thì bỏ được T1/T2/T4, dùng
   tín hiệu thật thay cho canh giờ — chắc chắn hơn nhiều.
3. **Băng chuyền có dừng khi loại bỏ không?** Tài liệu đang giả định là **có dừng**
   ở S9 để xy lanh 2 đẩy PCB ra an toàn.
4. **Kho phôi có cảm biến báo hết phôi không?** Hiện chu trình sẽ cứ đẩy dù đã hết.
5. **Xử lý khi PCB kẹt?** Nên có timeout ở S3/S4/S8: chạy quá lâu không tới cảm
   biến kế tiếp → báo lỗi kẹt phôi.

> Đã chốt: hệ thống có **2 xy lanh** — xy lanh 1 (`%Q0.4`) đẩy phôi vào, xy lanh 2
> (`%Q0.6`) loại phôi lỗi ra tại cảm biến 3.

---

## 9. Thứ tự triển khai

| Bước | Việc | Ai làm |
|---|---|---|
| 1 | Xác nhận 6 câu hỏi mục 8 | Bạn |
| 2 | Kiểm tra STOP/E-Stop đấu NC, E-Stop có cắt cứng | Bạn |
| 3 | Mở rộng DB1 lên 8 byte, tắt Optimized access | Bạn (TIA) |
| 4 | Viết tool kiểm chứng đọc/ghi đủ 9 trường DB1 | Claude |
| 5 | Viết máy trạng thái + timer phía PLC — xem [PLC_LADDER.md](PLC_LADDER.md) | Bạn (TIA) |
| 6 | Ghép vòng TRIGGER→YOLO→DONE vào GUI | Claude |
| 7 | Chạy thử **ngắt khí nén**, kiểm tra logic bằng đèn | Cả hai |
| 8 | Chạy thử có tải, phôi mẫu PASS và FAIL | Cả hai |
| 9 | Tinh chỉnh T1–T4, ngưỡng YOLO | Cả hai |

Bước 7 không được bỏ qua. Chạy logic trước khi cấp khí nén giúp phát hiện sai
trình tự mà không làm hỏng phôi hay kẹt cơ cấu.
