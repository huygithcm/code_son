# PLAN — Hệ thống kiểm tra board trên băng chuyền (AOI + PLC S7-1200)

Hệ tự động: **Cấp phôi → Băng chuyền → Kiểm tra (camera + YOLO) → Loại bỏ board lỗi (xi lanh)**.
PLC lo cơ cấu & an toàn (thời gian thực); PC lo vision + GUI + log. Giao tiếp qua `python-snap7` (DB1 handshake).

---

## 1. Kiến trúc tổng thể

```
        ┌─────────── Băng chuyền ───────────┐
 [Ổ phôi]→[Xi lanh cấp]→ S1(chụp) ──→ S2(loại) →[Output OK]
                           │             │
                        [Camera]     [Xi lanh reject]→[Thùng NG]
                           │
  PLC S7-1214C  ←IO→  cảm biến / van / đèn
       ↕ snap7 (DB1 handshake, Ethernet)
  PC: camera MindVision + YOLO (yolo_board/) + GUI + log
```

- **PLC**: đọc cảm biến, chạy/dừng băng chuyền, cấp phôi, bắn xi lanh loại board lỗi, đèn tháp/còi, E-stop, watchdog.
- **PC**: nhận trigger từ PLC → chụp → YOLO detect → đếm linh kiện so `expected.json` → trả PASS/FAIL về PLC + lưu log/ảnh NG + GUI.

---

## 2. PLC: S7-1200 CPU 1214C DC/DC/DC

Onboard: **14 DI**, **10 DQ** (transistor sourcing/PNP, 0.5A/điểm), 2 AI (chưa dùng).
→ **Thừa nhiều IO.** Xi lanh điều khiển bằng 1 ngõ ra, KHÔNG dùng reed phản hồi vị trí (định thời bằng timer).

### 2.1 Bảng ngõ vào (DI) — dùng 8/14
| Địa chỉ | Tín hiệu | Ghi chú |
|--------|----------|---------|
| I0.0 | Nút Start | |
| I0.1 | Nút Stop | |
| I0.2 | E-Stop (NC) | qua relay an toàn |
| I0.3 | S1 – board ở vị trí chụp | cảm biến quang PNP |
| I0.4 | S2 – board ở vị trí loại bỏ | |
| I0.5 | S0 – có phôi trong ổ chứa | báo hết phôi |
| I0.6 | S3 – board đã lên băng | xác nhận cấp thành công |
| I0.7 | Thùng NG đầy (tùy chọn) | |
| I1.0–I1.5 | Dự phòng (6) | đủ chỗ thêm reed sau nếu cần |

### 2.2 Bảng ngõ ra (DQ) — dùng 7/10
| Địa chỉ | Tín hiệu | Ghi chú |
|--------|----------|---------|
| Q0.0 | Băng chuyền (Run/VFD) | nếu đóng cắt động cơ trực tiếp → qua contactor |
| Q0.1 | Van xi lanh reject | 1 ngõ ra: OFF=thu, ON=đẩy |
| Q0.2 | Đèn xanh (chạy/PASS) | |
| Q0.3 | Đèn đỏ (FAIL/alarm) | |
| Q0.4 | Đèn vàng + còi | tải lớn → qua relay |
| Q0.5 | Van xi lanh cấp phôi | 1 ngõ ra: OFF=thu, ON=đẩy |
| Q0.6 | Van escapement (tùy chọn) | chống cấp đôi |
| Q0.7, Q1.0, Q1.1 | Dự phòng | |

### 2.3 Lưu ý đấu nối (DC/DC/DC)
1. Ngõ ra transistor 0.5A: chạy van khí 24V, đèn LED nhỏ trực tiếp; **còi/đèn tháp lớn, contactor động cơ → qua relay trung gian**.
2. Băng chuyền qua **biến tần** thì Q0.0 chỉ là tín hiệu Run; đóng cắt trực tiếp thì bắt buộc contactor.
3. Dùng **cảm biến PNP** (hợp input bản DC). NPN không phù hợp trực tiếp.
4. **E-Stop** phải đi qua **relay an toàn phần cứng** cắt nguồn van + động cơ, không chỉ dựa input I0.2.
5. Cần encoder truy vết board sau này → 1214C có HSC trên I0.0–I0.5, khi đó cân nhắc lại sơ đồ chân.

---

## 3. Xi lanh (single-acting, lò xo hồi — fail-safe)
- **Mỗi xi lanh chỉ 1 ngõ ra điều khiển**: Van OFF → THU về (home); Van ON → ĐẨY ra.
- **Không dùng reed phản hồi vị trí** → dùng **timer định thời** (thời gian đẩy / thời gian thu) trong PLC.
- Mất điện/E-Stop → van mất điện → xi lanh tự thu về (an toàn).
- Điều kiện Start: cả 2 van = OFF (mặc định xi lanh đã thu về).
- Đánh đổi: không có reed nên không tự phát hiện kẹt xi lanh; bù bằng timer dwell đủ rộng. Sau này cần phát hiện kẹt → thêm reed vào I1.x (đã chừa chỗ).

---

## 4. Giao tiếp PC ↔ PLC — DB1 handshake

Trong TIA: tạo **DB1**, **tắt "Optimized block access"**, **bật "Permit PUT/GET communication"** (CPU → Protection).

| Địa chỉ | Tên | Hướng | Ý nghĩa |
|--------|-----|------|---------|
| DBX0.0 | PC_Heartbeat | PC→PLC | PC đảo bit liên tục (watchdog) |
| DBX0.1 | Trigger_Req | PLC→PC | Yêu cầu kiểm tra (board ở S1) |
| DBX0.2 | Result_Ready | PC→PLC | PC đã có kết quả |
| DBX0.3 | Result_PASS | PC→PLC | Kết quả PASS |
| DBX0.4 | Result_FAIL | PC→PLC | Kết quả FAIL |
| DBW2 | Fail_count | PC→PLC | Số loại linh kiện NG |
| DBW4 | Board_ID | PLC→PC | Số thứ tự board (truy vết) |

**Trình tự handshake:**
1. Board chạm S1 → PLC dừng băng, tăng `Board_ID`, set `Trigger_Req=1`.
2. PC thấy cạnh lên `Trigger_Req` → chụp + detect → ghi `Result_PASS/FAIL`, `Fail_count`, set `Result_Ready=1`.
3. PLC nhận `Result_Ready` → lưu kết quả gắn `Board_ID` vào FIFO, chạy băng tiếp, clear `Trigger_Req`.
4. PC thấy `Trigger_Req=0` → clear `Result_Ready`.
5. Board tới S2: nếu kết quả board đó = FAIL → bắn xi lanh reject.

**Watchdog 2 chiều:** PC mất nhịp Heartbeat >2s → PLC dừng an toàn + alarm; PLC mất kết nối → GUI báo đỏ.

---

## 5. Logic PLC (cấu trúc TIA)

- **FB_Sequence** — máy trạng thái tổng:
  `IDLE → RUN → FEED → MOVE → AT_S1(stop, inspect) → WAIT_VISION → RESUME → (S2: reject nếu FAIL) → FEED...`
- **FB_Feeder** — cấp phôi:
  1. Điều kiện: RUN + vùng S1 trống + có phôi (S0=1) + chưa có board chờ.
  2. `Q0.5=ON` đẩy → **timer T_đẩy** → board xuống băng → `Q0.5=OFF` thu → **timer T_thu**.
  3. S3 xác nhận board lên băng trong thời gian cho phép → cấp OK, tăng Board_ID; không thấy → "Lỗi cấp phôi".
  4. S0=0 → "Hết phôi", dừng cấp (chạy hết board còn lại rồi dừng).
  5. Escapement Q0.6 (tùy chọn) chống cấp đôi.
- **FB_RejectStation** — xi lanh reject:
  board FAIL tới S2 → `Q0.1=ON` → **timer T_đẩy** (board rơi xuống thùng NG) → `Q0.1=OFF` → **timer T_thu**. Đếm reject. (Không reed → định thời bằng timer.)
- **FB_VisionHandshake** — quản lý DB1 + watchdog PC_Heartbeat.
- **FB_Alarms** — E-stop, mất PC, thùng NG đầy, hết phôi, lỗi cấp phôi (S3 không thấy board).
- **Truy vết board (FIFO/shift register):** kết quả đẩy vào hàng đợi khi rời S1, lấy ra khi tới S2.

> Giai đoạn đầu: **stop-and-go, 1 board/chu kỳ** cho chắc. Tối ưu pipeline (cấp phôi song song lúc đang kiểm tra) sau.

---

## 6. An toàn (bắt buộc)
- E-Stop cắt nguồn động cơ + van bằng **relay an toàn phần cứng**; phần mềm chỉ phản ánh trạng thái.
- Cả 2 xi lanh về home trước khi Start.
- Watchdog 2 chiều PC↔PLC.
- Van nối sao cho mất điện → xi lanh thu về (không kẹt board ở trạng thái đẩy).

---

## 7. GIAO DIỆN PC (mở rộng từ `detect_components.py`)

- **Live view** + ROI / Auto ROI (HSV) — đã có.
- **Bảng PASS/FAIL** từng linh kiện, cập nhật mỗi board — đã có; đèn TỔNG PASS/NG to.
- **Chế độ**: Auto (PLC trigger) / Manual (nút Chụp & Detect).
- **Thống kê**: tổng kiểm tra, PASS, FAIL, **yield %**, đếm theo từng loại lỗi, số reject, số phôi đã cấp. Reset ca.
- **Log CSV** mỗi board: thời gian, Board_ID, kết quả, số lượng từng class, đường dẫn ảnh.
- **Lưu ảnh NG** (overlay) theo ngày.
- **Trạng thái** PLC + Camera (đèn báo) + nút reconnect.
- **Cấu hình**: chỉnh `expected.json` bằng spinbox từng class, ngưỡng conf, imgsz, IP/DB mapping PLC, thông số camera.
- **Recipe** đổi sản phẩm: model + expected riêng từng loại board.
- **Bảng cảnh báo**: mất camera, mất PLC, thùng NG đầy, hết phôi, lỗi cấp phôi.
- **Nút tay (jog)**: cấp phôi tay, test xi lanh — để căn chỉnh.
- (Tùy chọn) Phân quyền Operator/Admin.

**Kiến trúc phần mềm PC (đa luồng):**
- Thread GUI (tkinter).
- Thread PLC (`plc_worker.py`): poll `Trigger_Req`, ghi Heartbeat + kết quả.
- Inspection chạy khi có trigger: camera grab → `detect_components.detect()` → `evaluate()`.
- File: `expected.json`, `settings.json`, `recipes/`; log: `logs/*.csv` + `ng_images/`.

---

## 8. Model vision hiện tại
- YOLO 5 class: `capacitor, diode, inductor, lm2596, potentiometer`.
- `expected.json`: capacitor=2, các loại khác=1. **PASS khi found == exp** (thiếu/thừa đều NG).
- ROI + imgsz nhỏ (416/320) để tăng tốc; imgsz 640 nếu ưu tiên độ chính xác.

---

## 9. Các giai đoạn triển khai
1. **PLC nền**: đấu IO, chạy/dừng băng chuyền, test tay 2 xi lanh (mỗi cái 1 ngõ ra, định thời timer) + đọc cảm biến.
2. **Cấp phôi**: FB_Feeder, xác nhận S3, xử lý hết phôi / lỗi cấp.
3. **Định vị**: S1 stop-and-go, S2 vị trí loại bỏ.
4. **Handshake**: PC↔PLC DB1 với kết quả giả + watchdog.
5. **Tích hợp vision**: trigger → detect → kết quả thật.
6. **Loại bỏ**: xi lanh reject tại S2 theo kết quả + reed feedback + fault, đếm reject.
7. **GUI nâng cao**: thống kê, log CSV, ảnh NG, recipe, alarm, jog.
8. **Robust**: reconnect, watchdog, xử lý ngoại lệ.
9. **Nghiệm thu**: throughput, tỉ lệ loại nhầm (false reject) & lọt lỗi (escape).

---

## 10. Việc tiếp theo (phía PC)
- [ ] `plc_worker.py` — luồng handshake DB1 (poll Trigger_Req → detect → ghi kết quả + Heartbeat).
- [ ] Ghép `plc_worker` + `detect_components` vào 1 GUI tổng (Auto/Manual, thống kê, log).
- [ ] Editor `expected.json` trên GUI (spinbox từng class).
- [ ] Log CSV + lưu ảnh NG.
