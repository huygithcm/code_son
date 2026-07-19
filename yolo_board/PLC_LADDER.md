# Đặc tả chương trình PLC — Ladder (LAD)

Tài liệu implement chi tiết cho TIA Portal. Đọc kèm:
[CHU_TRINH.md](CHU_TRINH.md) (tổng quan chu trình) · [PLC_SETUP.md](PLC_SETUP.md) (kết nối, I/O)

Cập nhật: 18/07/2026 · Nhánh `yolo-plc`

> **Loại nút nhấn:** tất cả START / STOP / E-Stop đều là **nút nhấn nhả**
> (momentary — buông tay là tín hiệu mất). Vì vậy chương trình phải **tự giữ**
> mọi trạng thái do nút tạo ra. Xem mục 6.
>
> **Cấu hình hiện tại (đang test):** chỉ có START và STOP, **cả hai đấu NO —
> nhấn = 1**. Chưa lắp E-Stop. Dùng ladder ở [mục 6B](#6b-phiên-bản-test--chỉ-có-start-và-stop),
> chỉ chạy khi **đã ngắt khí nén**.
>
> **Cấu hình đích (chạy thật):** STOP và E-Stop đấu **NC — nhấn = 0**, có mạch
> cắt cứng. Dùng ladder ở mục 6. Quy trình chuyển đổi ở [mục 6C](#6c-chuyển-sang-cấu-hình-an-toàn-trước-khi-chạy-có-tải).
>
> **Xy lanh:** van đơn, không có cảm biến hành trình. Ngõ ra **ON = đẩy ra**,
> **OFF = tự thu về**. Chỉ cần kích ngõ ra trong khoảng thời gian định trước rồi
> chạy tiếp — **không có trạng thái chờ thu về riêng** (xem mục 7.1).

---

## 1. Cấu trúc chương trình

| Khối | Tên | Nội dung |
|---|---|---|
| `OB1` | Main | Gọi tuần tự FC1 → FC2 → FC3 → FC4 |
| `FC1` | `FC_AnToan` | Chốt E-Stop, mạch an toàn, latch START/STOP |
| `FC2` | `FC_MayTrangThai` | Máy trạng thái S0–S8, S99 |
| `FC3` | `FC_NgoRa` | Điều khiển cơ cấu + đèn + còi |
| `FC4` | `FC_GiaoTiepPC` | Watchdog PC, bộ đếm, cập nhật DB1 |

Tách khối như trên để dễ tìm lỗi. Nếu muốn gọn, gộp hết vào `OB1` cũng chạy được
nhưng khó bảo trì.

> **Thứ tự gọi rất quan trọng.** `FC1` phải chạy trước để tính điều kiện an toàn,
> `FC3` chạy sau cùng để ngõ ra phản ánh trạng thái mới nhất trong cùng vòng quét.

### 1.1 — Cách gọi FC trong OB1

Trong TIA Portal, mỗi FC là một **khối hộp không có chân vào/ra** (vì các FC này
không khai báo tham số, chúng đọc/ghi thẳng vào tag toàn cục và DB). Gọi bằng
cách kéo thả từ cây dự án vào network của OB1.

**Các bước:**

1. Mở `OB1 [Main]`
2. Ở cây bên trái: *Program blocks* → kéo `FC1` thả vào **Network 1** của OB1
3. Làm tương tự với `FC2`, `FC3`, `FC4` — mỗi khối một network riêng

**Kết quả trong OB1 — 4 network, mỗi network một lệnh gọi:**

```
                ┌──────────────┐
NW1  ───────────┤  "FC_AnToan" ├───────
                │      FC1     │
                └──────────────┘

                ┌──────────────────┐
NW2  ───────────┤ "FC_MayTrangThai"├───
                │       FC2        │
                └──────────────────┘

                ┌──────────────┐
NW3  ───────────┤  "FC_NgoRa"  ├───────
                │      FC3     │
                └──────────────┘

                ┌──────────────────┐
NW4  ───────────┤ "FC_GiaoTiepPC"  ├───
                │       FC4        │
                └──────────────────┘
```

**Dây trái nối thẳng vào khối, không có tiếp điểm nào phía trước** — nghĩa là FC
luôn được gọi mỗi vòng quét, không điều kiện. Đây là điều bạn muốn: máy trạng
thái và mạch an toàn phải chạy liên tục.

> **Không đặt tiếp điểm điều kiện trước lệnh gọi FC.** Ví dụ nếu đặt
> `chu_trinh_chay ┤ ├` trước `FC3`, thì khi máy dừng, FC3 không chạy → các ngõ ra
> **giữ nguyên giá trị cũ** thay vì tắt. Băng chuyền sẽ tiếp tục quay sau khi
> nhấn STOP. Luôn gọi FC vô điều kiện, việc bật/tắt để logic bên trong FC lo.

**Nếu muốn gộp hết vào OB1** (không tách FC): bỏ qua bước trên, dựng thẳng
NW1–NW30 trong OB1 theo đúng thứ tự số hiệu network trong tài liệu này. Thứ tự
network chính là thứ tự thực thi.

---

## 2. Chuẩn bị trong TIA Portal

Ba việc phải làm trước khi viết code, thiếu là chương trình không chạy đúng:

1. **Bật PUT/GET**: CPU → Properties → Protection & Security → tick
   *"Permit access with PUT/GET communication from remote partner"*
2. **Bật Clock memory byte**: CPU → Properties → System and clock memory →
   tick *Enable clock memory byte*, đặt địa chỉ **`%MB100`**
   (dùng để nháy đèn — xem mục 9)
3. **DB1 phải TẮT "Optimized block access"**: chuột phải DB1 → Properties →
   bỏ tick *Optimized block access*

---

## 3. Cấu trúc DB1 — giao tiếp với máy tính

**Tên khối:** `DB_GiaoTiepPC` · **Số:** `DB1` · **Optimized block access: TẮT**

| Offset | Tên biến | Kiểu | Ai ghi | Ý nghĩa |
|---|---|---|---|---|
| `0.0` | `TRIGGER` | Bool | **PLC** | PCB đã vào vị trí, yêu cầu PC chụp |
| `0.1` | `DONE` | Bool | **PC** | PC xử lý xong, kết quả sẵn sàng |
| `0.2` | `PASS` | Bool | **PC** | Kết quả đạt |
| `0.3` | `FAIL` | Bool | **PC** | Kết quả không đạt |
| `0.4` | `PC_ALIVE` | Bool | **PC** | Nhịp tim, PC đảo bit mỗi giây |
| `0.5` | `PC_SAN_SANG` | Bool | **PC** | PC đã nạp model, sẵn sàng nhận việc |
| `0.6` | *dự phòng* | Bool | — | |
| `0.7` | *dự phòng* | Bool | — | |
| `1.0` | `MAY_DANG_CHAY` | Bool | **PLC** | Chu trình đang chạy |
| `1.1` | `MAY_LOI` | Bool | **PLC** | Đang ở trạng thái lỗi |
| `1.2` | `E_STOP_TAC_DONG` | Bool | **PLC** | E-Stop đang bị chốt |
| `1.3` | *dự phòng* | Bool | — | |
| `2` | `SO_LOI` | Int | **PC** | Số lỗi phát hiện trên PCB |
| `4` | `MA_LOI` | Int | **PC** | Mã loại lỗi |
| `6` | `DEM_TONG` | Int | **PLC** | Tổng PCB đã kiểm tra |
| `8` | `DEM_PASS` | Int | **PLC** | Số PCB đạt |
| `10` | `DEM_FAIL` | Int | **PLC** | Số PCB loại |
| `12` | `TRANG_THAI_MAY` | Int | **PLC** | Số hiệu trạng thái hiện tại (0–8, 99) |
| `14` | *dự phòng* | Int | — | |

**Tổng: 16 byte.**

> **Quy tắc không được vi phạm:** mỗi ô chỉ có **một** bên ghi. PLC không bao giờ
> ghi vào ô của PC và ngược lại. Vi phạm quy tắc này sẽ sinh ra lỗi chập chờn
> cực kỳ khó tìm.

---

## 4. Cấu trúc DB2 — dữ liệu nội bộ

**Tên khối:** `DB_May` · **Số:** `DB2` · Optimized bật hay tắt đều được (chỉ PLC dùng).

| Tên biến | Kiểu | Giá trị đầu | Ý nghĩa |
|---|---|---|---|
| `trang_thai` | **Int** | `0` | Trạng thái hiện tại của máy |
| `kq_pass` | Bool | `FALSE` | Kết quả PASS đã chốt cho phôi hiện tại |
| `kq_fail` | Bool | `FALSE` | Kết quả FAIL đã chốt |
| `pc_mat_ket_noi` | Bool | `FALSE` | Mất nhịp tim từ PC |
| `xung_alive` | Bool | `FALSE` | Xung 1 vòng quét khi `PC_ALIVE` đảo |
| `T_day_phoi` | Time | `T#1S` | Thời gian kích xy lanh 1 |
| `T_loai_bo` | Time | `T#5S` | Thời gian kích xy lanh 2 |
| `T_cho_pc` | Time | `T#3S` | Timeout chờ PC trả kết quả |
| `T_ket_phoi` | Time | `T#15S` | Timeout phát hiện kẹt phôi |

> `trang_thai` **bắt buộc kiểu Int**, không phải Bool — nó chứa các giá trị 0–8
> và 99. Khai báo nhầm Bool sẽ khiến TIA báo lỗi khi dựng khối MOVE.

Để các thời gian ở DB thay vì gõ cứng vào timer, sau này chỉnh được từ HMI/GUI mà
không phải sửa chương trình.

### ⚠ Sửa "Start value" xong mà timer vẫn chạy như T#0ms

TIA phân biệt hai cột, và chương trình **chỉ dùng cột thứ hai**:

| Cột trong DB | Ý nghĩa | Chương trình dùng |
|---|---|---|
| **Start value** | Giá trị nạp khi DB được **khởi tạo lại** | ❌ |
| **Actual / Monitor value** | Giá trị **đang nằm trong bộ nhớ CPU** | ✅ |

Sửa Start value rồi Download **không** ghi đè Actual value — TIA cố tình giữ giá
trị đang chạy để không làm gián đoạn máy. Kết quả: `T_day_phoi` vẫn là `T#0ms`,
TON hết giờ ngay lập tức, máy trạng thái nhảy vọt qua S1 và S8 trong một vòng quét.

**Ba cách xử lý:**

1. **Ghi thẳng Actual value** — Online → mở DB2 → *Monitor all* → nhập `T#1S` vào
   cột *Monitor value*. Có hiệu lực ngay, không cần dừng máy. Nhưng mất khi CPU
   cold restart.
2. **Khởi tạo lại DB** — chuột phải `DB_May` → *Download to device* → chọn
   **Reinitialize**. Cần CPU ở STOP. Đây là cách làm Start value thực sự có tác dụng.
3. **Kiểm tra cột Retain** — nếu biến được tick *Retain*, giá trị giữ qua warm
   restart và Start value bị bỏ qua. Các biến thời gian là tham số cấu hình,
   **không nên** tick Retain.

**Trong giai đoạn bring-up**, đơn giản nhất là gõ thẳng hằng số vào chân `PT`
(`T#1S`) thay cho tham chiếu DB. Hằng số nằm trong code nên compile + download là
có hiệu lực ngay, không dính chuyện Start/Actual value. Chuyển sang tham chiếu DB
khi chu trình đã chạy ổn.

> **`T_loai_bo` đang để 5 giây** theo yêu cầu ban đầu. Nếu chỉ cần kích 1 giây
> như xy lanh 1 thì đổi giá trị này, không phải sửa ladder.

---

## 5. Bảng tag

### PLC tags — bit nhớ (M)

| Địa chỉ | Tên | Ý nghĩa |
|---|---|---|
| `%M0.0` | `an_toan_ok` | Mạch an toàn thông |
| `%M0.1` | `chu_trinh_chay` | Latch: đã nhấn START, chưa dừng |
| `%M0.3` | `estop_chot` | **Chốt E-Stop** — giữ trạng thái khẩn cấp sau khi buông nút |
| `%MB100` | *clock memory* | Byte nháy hệ thống (CPU tự tạo) |

**Bit nháy có sẵn trong `%MB100`:**

| Bit | Tần số | Dùng cho |
|---|---|---|
| `%M100.5` | 1 Hz | Nháy chậm — cảnh báo |
| `%M100.3` | 2 Hz | Nháy nhanh — lỗi nghiêm trọng |

> Hai bit này **chỉ hoạt động khi đã bật clock memory byte** (mục 2, bước 2).
> Chưa bật thì chúng luôn = 0 → đèn không nháy, rất dễ tưởng nhầm là sai logic đèn.

### Bit nhớ cho tiếp điểm bắt sườn — mỗi tiếp điểm MỘT bit riêng

Mỗi tiếp điểm `┤P├` / `┤N├` lưu trạng thái vòng quét trước vào một bit nhớ. **Hai
tiếp điểm dùng chung một bit sẽ ghi đè nhau**: cái chạy trước "ăn" mất sườn, cái
sau không bao giờ nhận được → máy kẹt trạng thái. TIA thường tự hỏi và tạo bit
khi kéo tiếp điểm vào, nhưng phải kiểm tra không có bit nào bị dùng hai lần.

| Bit | Tên đề xuất | Dùng ở |
|---|---|---|
| `%M50.4` | `P_trig_s3_pass` | NW15 — sườn `in_sensor_3` cho nhánh **PASS** |
| `%M50.5` | `P_trig_s3_fail` | NW16 — sườn `in_sensor_3` cho nhánh **FAIL** |
| `%M50.6` | `P_trig_start` | NW4 — sườn nút START |
| `%M50.7` | `P_trig_alive` | NW27 — sườn lên `PC_ALIVE` |
| `%M51.0` | `N_trig_alive` | NW27 — sườn xuống `PC_ALIVE` |

> **`in_sensor_3` xuất hiện ở hai network nên cần HAI bit khác nhau** — đây là chỗ
> dễ sai nhất. Dùng chung một bit `P_trig_sensor3` cho cả NW15 và NW16 sẽ làm máy
> kẹt ở S6 hoặc S7 tuỳ vòng quét, và lỗi xuất hiện không đều nên rất khó tìm.

### Cảm biến 1 và 2 dùng tiếp điểm THƯỜNG, không dùng sườn

NW9 và NW10 chờ board **đã tới nơi**, không phải thời điểm vừa tới. Nếu dùng
`┤P├` ở đây và board đã che cảm biến **trước khi** máy vào trạng thái đó, sườn lên
đã xảy ra mất rồi → chờ mãi không thấy → **kẹt trạng thái**.

Chỉ `in_sensor_3` mới cần bắt sườn, vì ở đó cần biết đúng thời điểm board vừa tới
để dừng hoặc đếm.

### Instance DB cho timer

Mỗi TON cần một instance DB riêng. Khi kéo khối TON vào network, TIA tự hỏi và tạo.

| Tên instance | Dùng ở | Thời gian |
|---|---|---|
| `IDB_T_DAY` | S1 — kích xy lanh 1 | `DB2.T_day_phoi` |
| `IDB_T_LOAI` | S8 — kích xy lanh 2 | `DB2.T_loai_bo` |
| `IDB_T_PC` | S4 — chờ PC | `DB2.T_cho_pc` |
| `IDB_T_ALIVE` | Watchdog PC | `T#3S` |
| `IDB_T_KET2` | S2 — kẹt phôi | `DB2.T_ket_phoi` |
| `IDB_T_KET3` | S3 — kẹt phôi | `DB2.T_ket_phoi` |
| `IDB_T_KET7` | S7 — kẹt phôi | `DB2.T_ket_phoi` |

### Cơ chế reset timer — không cần lệnh reset riêng

`TON` **tự reset khi chân `IN` xuống 0**: giá trị `ET` về 0 và `Q` về 0. Trong
thiết kế này, chân `IN` của mọi timer đều nối với một điều kiện dạng
`trang_thai = X`, nên rời khỏi trạng thái đó là timer tự reset. Không cần lệnh
`RT` (Reset Timer) ở bất cứ đâu.

**Điều kiện để cơ chế này hoạt động:** chân `IN` phải xuống 0 giữa hai lần dùng.
Nếu `IN` nối với điều kiện có thể giữ mức 1 xuyên qua nhiều trạng thái (ví dụ
`trang_thai = 2 OR = 3`), timer sẽ **không reset** khi chuyển giữa các trạng thái
đó — đây là lý do các timer kẹt phôi phải tách thành ba network riêng.

Muốn kiểm tra khi chạy thử: mở Watch table xem `IDB_T_DAY.ET`, giá trị phải nhảy
về 0 mỗi lần máy rời khỏi trạng thái tương ứng.

---

## 5B. Quy ước ký hiệu trong tài liệu này

Các sơ đồ bên dưới dùng **ký hiệu rút gọn** cho dễ đọc. Dưới đây là dạng thật khi
dựng trong TIA Portal.

### Tiếp điểm và cuộn dây — giống thật

| Ký hiệu | Tên trong TIA | Ý nghĩa |
|---|---|---|
| `┤ ├` | Normally Open contact | Thông khi bit = 1 |
| `┤/├` | Normally Closed contact | Thông khi bit = 0 |
| `┤P├` | P_TRIG / positive edge | Xung 1 vòng quét khi bit lên 1 |
| `┤N├` | N_TRIG / negative edge | Xung 1 vòng quét khi bit về 0 |
| `( )` | Coil | Gán bit theo trạng thái mạch |
| `( S )` | Set coil | Bật bit, giữ nguyên |
| `( R )` | Reset coil | Tắt bit, giữ nguyên |

### Quy tắc: MOVE cho Int, Set/Reset cho Bool

Đây là chỗ TIA sẽ báo lỗi ngay nếu làm sai kiểu:

| Kiểu biến | Ví dụ | Lệnh dùng | Lệnh **không** dùng được |
|---|---|---|---|
| `Int` | `DB2.trang_thai`, `DB1.DEM_TONG` | `MOVE`, `INC` | `( S )`, `( R )` |
| `Bool` | `DB2.kq_pass`, `DB1.TRIGGER` | `( )`, `( S )`, `( R )` | `MOVE` |

> **Không MOVE được số nguyên vào biến Bool.** Nếu TIA báo lỗi kiểu dữ liệu khi
> bạn dựng `MOVE 0 → DB2.trang_thai`, nguyên nhân gần như chắc chắn là
> `trang_thai` đang bị khai báo là **Bool** trong DB2. Mở DB2 và đổi kiểu về
> **Int**.

### MOVE — là khối hộp, không phải mũi tên

Viết tắt trong tài liệu:

```
──[ MOVE  0 → DB2.trang_thai ]
```

Dạng thật phải dựng trong TIA — khối `MOVE` có 4 chân `EN`, `ENO`, `IN`, `OUT1`:

```
     điều kiện           ┌──── MOVE ────┐
     ──────┤ ├───────────┤EN         ENO├──
                       0 ┤IN       OUT1├────  DB2.trang_thai
                         └──────────────┘
```

- `EN` nối với điều kiện của rung (dây trái)
- `IN` là **hằng số hoặc biến nguồn** — gõ trực tiếp `0`, `1`, `99`…
- `OUT1` là **biến đích** — kéo thả `DB2.trang_thai` vào

Khối MOVE nằm ở *Instructions → Basic instructions → Move operations → MOVE*.

### So sánh — cũng là khối hộp

Viết tắt:

```
     DB2.trang_thai
     ──[ == Int  5 ]────
```

Dạng thật — khối `CMP ==` (Compare):

```
       DB2.trang_thai
     ┌──────┴───────┐
     │    == Int    │────
     └──────┬───────┘
            5
```

Trong TIA, kéo khối `CMP ==` từ *Comparator operations*, đặt biến ở ô trên và
giá trị so sánh ở ô dưới. Nhớ đổi kiểu dữ liệu sang **Int**.

### INC — tăng bộ đếm

Viết tắt:

```
──[ INC  DB1.DEM_TONG ]
```

Dạng thật — khối `INC` có `EN`, `ENO`, `IN/OUT`:

```
     điều kiện           ┌──── INC ────┐
     ──────┤ ├───────────┤EN        ENO├──
                         │   Int       │
                         └──────┬──────┘
                                │  DB1.DEM_TONG
                            IN/OUT
```

Khối `INC` nằm ở *Basic instructions → Math functions → INC*.

> **Nhiều lệnh trên cùng một rung.** Khi một điều kiện phải chạy nhiều khối,
> trong TIA bạn nối chúng **nối tiếp** qua chân `ENO → EN` của khối kế tiếp, hoặc
> tạo **nhiều nhánh song song** cùng xuất phát từ điều kiện đó. Cách nhánh song
> song dễ đọc hơn và đó là cách các sơ đồ dưới đây thể hiện bằng dấu `┬` `├` `└`.

---

## 6. FC1 — Chốt E-Stop, an toàn và latch

### Vì sao cần chốt E-Stop

Nút nhấn nhả buông tay là tín hiệu trở lại bình thường. Nếu chỉ đọc trực tiếp
`%I0.5`, người vận hành nhấn E-Stop rồi buông ra là máy **hết trạng thái khẩn cấp
ngay lập tức** — cực kỳ nguy hiểm. Vì vậy phải `SET` một bit chốt, và chỉ `RESET`
khi có thao tác xác nhận rõ ràng của người vận hành.

Quy trình khôi phục sau E-Stop:
1. Xử lý xong sự cố
2. Buông / xoay nhả nút E-Stop
3. **Nhấn STOP** để xác nhận → chốt được xoá
4. Nhấn START để chạy lại

### NW1 — Chốt E-Stop khi nhấn

E-Stop đấu **NC**: không nhấn = 1, nhấn hoặc **đứt dây** = 0.

```
     in_emergency_button              estop_chot
NW1  ──────┤/├──────────────────────────( S )──────
           %I0.5                        %M0.3
```

### NW2 — Xoá chốt E-Stop

```
     in_emergency_button   in_stop_button          estop_chot
NW2  ──────┤ ├────────────────┤/├────────────────────( R )──────
           %I0.5              %I0.0                  %M0.3
```

Chỉ xoá khi **đồng thời**: E-Stop đã nhả (`%I0.5` = 1) **và** người vận hành đang
nhấn STOP (`%I0.0` = 0 vì đấu NC). Buông E-Stop không thôi thì chốt vẫn giữ.

### NW3 — Điều kiện an toàn

```
     estop_chot     in_stop_button           an_toan_ok
NW3  ──────┤/├──────────┤ ├────────────────────( )──────
           %M0.3        %I0.0                  %M0.0
```

Mạch thông khi: không có chốt E-Stop **và** không đang nhấn STOP.

> Dùng tiếp điểm **thường hở** `┤ ├` cho nút NC. Nghe ngược nhưng đúng: nút NC
> không nhấn → tín hiệu 1 → tiếp điểm đóng → mạch thông. Nhấn nút hoặc **đứt dây**
> → tín hiệu 0 → mạch hở → dừng. Đây chính là lý do phải đấu NC.

### NW4 — Latch chu trình (tự giữ START)

```
     in_start_button        an_toan_ok        chu_trinh_chay
NW4  ──────┤P├────────┬───────┤ ├────────────────( )──────
           %I0.1      │       %M0.0              %M0.1
        (M_edge_start)│
     chu_trinh_chay   │
     ──────┤ ├────────┘
           %M0.1
```

Nhánh song song `chu_trinh_chay` là phần tự giữ: nhả nút START vẫn chạy tiếp.
Nhấn STOP hoặc E-Stop → `an_toan_ok` = 0 → mất tự giữ → dừng, và **không tự chạy
lại** khi nhả nút.

> **Nút START dùng tiếp điểm bắt sườn lên `┤P├`**, không phải tiếp điểm thường.
> Nếu dùng tiếp điểm thường, người vận hành giữ nút START rồi nhấn STOP: máy dừng
> đúng lúc nhấn STOP, nhưng vừa buông STOP ra là **máy tự chạy lại ngay** vì
> START vẫn đang bị giữ. Bắt sườn lên buộc phải nhả rồi nhấn lại mới khởi động
> được.

### Nếu dùng `┤P├` mà mạch không tự giữ

Về nguyên lý mạch trên chạy đúng, nên hiện tượng không giữ gần như luôn do **đặt
sai vị trí nhánh song song**. Điểm hợp nhánh phải nằm **ngay sau `┤P├`, trước
`an_toan_ok`**.

**Sai 1 — nhánh OR bọc cả P lẫn `an_toan_ok`:**

```
     ──┤P├────┤ ├────┬───( )
     ──┤ ├───────────┘
```

Nhánh giữ đi vòng qua `an_toan_ok` → *latch giữ được nhưng nhấn STOP không dừng*.

**Sai 2 — `┤P├` nằm sau điểm hợp nhánh:**

```
     ──┬──┤ ├──┬──┤P├──┤ ├───( )
       └──┤ ├──┘
```

Cả rung chỉ dẫn điện 1 vòng quét → *coil bật rồi tắt ngay, không tự giữ*.

### Cách thay thế chắc chắn hơn: Set/Reset coil

Nếu vẽ nhánh song song hay bị lỗi, bỏ hẳn OR-latch và dùng hai network. Không có
nhánh nào nên khó sai hơn nhiều:

```
     in_start_button    pc_mat_ket_noi        chu_trinh_chay
NW4a ──────┤P├─────────────┤/├──────────────────( S )──────
           %I0.1                                %M0.1

     an_toan_ok                                 chu_trinh_chay
NW4b ──────┤/├──────────────────────────────────( R )──────
           %M0.0                                %M0.1
```

Set coil giữ bit cho tới khi gặp Reset — **bản thân nó đã là tự giữ**, không cần
nhánh hồi tiếp.

> **Thứ tự bắt buộc: `( R )` phải nằm SAU `( S )`.** Lệnh chạy sau thắng, nên đặt
> Reset sau thì **lệnh dừng luôn thắng lệnh chạy** — đúng nguyên tắc an toàn. Đảo
> ngược thứ tự sẽ khiến giữ nút START đè được lệnh dừng.
>
> Hai network này phải nằm **cùng trong FC1**. Đừng đặt Reset ở FC khác chạy sau —
> đó chính là lỗi đã gặp ở NW29 (xem mục 10).

### NW5 — Reset khi dừng

```
     chu_trinh_chay
NW5  ──────┤/├──────┬──[ MOVE  0 → DB2.trang_thai ]
           %M0.1    │
                    ├──[ RESET  DB2.kq_pass ]
                    ├──[ RESET  DB2.kq_fail ]
                    └──[ RESET  DB1.TRIGGER ]
```

Dừng máy thì đưa về trạng thái đầu và xoá mọi cờ kết quả. Không xoá bộ đếm.

### NW6 — Báo trạng thái E-Stop cho PC

```
     estop_chot              DB1.E_STOP_TAC_DONG
NW6  ──────┤ ├────────────────────( )──────
           %M0.3
```

Báo theo **bit chốt**, không theo `%I0.5` trực tiếp — để GUI hiển thị đúng là máy
vẫn đang ở trạng thái khẩn cấp kể cả khi nút đã được buông ra.

---

## 6B. PHIÊN BẢN TEST — chỉ có START và STOP

> ### ⚠ CHỈ DÙNG ĐỂ CHẠY THỬ LOGIC
>
> Phiên bản này **không có nút dừng khẩn cấp**. Chỉ được dùng khi:
> - **Đã ngắt khí nén** — xy lanh không thể chuyển động
> - Chỉ quan sát đèn báo và nghe tiếng van
> - Không có phôi thật, không có người thao tác gần cơ cấu
>
> **Không được chạy phiên bản này khi đã cấp khí nén hoặc có tải.**

### Vì sao không thể chỉ "bỏ qua" `%I0.5`

Ngõ vào chưa đấu dây sẽ đọc ra **0**. Logic NC hiểu 0 là *đang nhấn E-Stop*, nên
`an_toan_ok` sẽ luôn = 0 và **máy không bao giờ khởi động được**. Nếu bạn dựng
NW1–NW6 rồi thấy nhấn START không ăn, đây chính là nguyên nhân.

Vì vậy phiên bản test phải **bỏ hẳn** `%I0.5` và `estop_chot` khỏi mạch.

### NW1-T — Điều kiện an toàn (rút gọn)

Nút STOP hiện đang đấu **NO (thường hở)**: không nhấn = 0, **nhấn = 1**.
Vì vậy phải dùng tiếp điểm **thường đóng** `┤/├` để đảo lại.

```
     in_stop_button            an_toan_ok
NW1T ──────┤/├──────────────────( )──────
           %I0.0                %M0.0
```

Không nhấn → `%I0.0` = 0 → tiếp điểm `┤/├` đóng → `an_toan_ok` = 1 → cho chạy.
Nhấn STOP → `%I0.0` = 1 → tiếp điểm hở → `an_toan_ok` = 0 → dừng.

> **Đây là kiểu đấu KHÔNG an toàn, chỉ chấp nhận trong giai đoạn test.**
> Với kiểu NO, nếu **đứt dây hoặc hỏng tiếp điểm** thì `%I0.0` mãi = 0, tức là
> "không ai nhấn STOP" — **nút dừng mất tác dụng hoàn toàn mà không có dấu hiệu
> gì**. Xem mục 6C.

### NW2-T — Latch chu trình

```
     in_start_button        an_toan_ok        chu_trinh_chay
NW2T ──────┤P├────────┬───────┤ ├────────────────( )──────
           %I0.1      │       %M0.0              %M0.1
        (M_edge_start)│
     chu_trinh_chay   │
     ──────┤ ├────────┘
           %M0.1
```

### NW3-T — Reset khi dừng

Viết tắt:

```
     chu_trinh_chay
NW3T ──────┤/├──────┬──[ MOVE  0 → DB2.trang_thai ]
           %M0.1    │
                    ├──[ RESET  DB2.kq_pass ]
                    ├──[ RESET  DB2.kq_fail ]
                    └──[ RESET  DB1.TRIGGER ]
```

**Dạng đầy đủ** — một điều kiện chạy 4 lệnh, dùng 4 nhánh song song:

```
     chu_trinh_chay      ┌──── MOVE ────┐
     ──────┤/├────────┬──┤EN         ENO├──
           %M0.1      │0 ┤IN       OUT1├────  DB2.trang_thai
                      │  └──────────────┘
                      │
                      │      DB2.kq_pass
                      ├────────( R )────
                      │
                      │      DB2.kq_fail
                      ├────────( R )────
                      │
                      │      DB1.TRIGGER
                      └────────( R )────
```

Trong TIA: đặt khối MOVE trước, rồi bấm chuột phải ở nhánh → *Insert branch* để
thêm ba nhánh còn lại, mỗi nhánh đặt một Reset coil.

### Ba network này thay cho NW1–NW6

Để trống NW4–NW6, **FC2 vẫn bắt đầu từ NW7** — số hiệu network ở các mục sau giữ
nguyên, không phải đánh số lại.

### Những chỗ phải sửa kèm ở phiên bản test

| Network | Ở bản đầy đủ | Ở bản test |
|---|---|---|
| NW6 | `estop_chot` → `DB1.E_STOP_TAC_DONG` | **Bỏ network này** |
| NW25 | Nhánh 3 dùng `estop_chot` | **Bỏ nhánh 3** (đèn đỏ) |
| NW26 | Nhánh `estop_chot` | **Bỏ nhánh đó** (còi) |

### Kịch bản test cho bản rút gọn

| # | Thao tác | Kết quả đúng |
|---|---|---|
| 1 | Nhấn START rồi buông | `chu_trinh_chay` = 1, giữ nguyên sau khi buông |
| 2 | Nhấn STOP rồi buông | `chu_trinh_chay` = 0, không tự bật lại |
| 3 | **Giữ** START, nhấn rồi buông STOP | Máy **không** tự chạy lại |

Tình huống 3 là chỗ dễ sai nhất — nếu sai, máy tự khởi động bất ngờ.

---

## 6C. Chuyển sang cấu hình an toàn trước khi chạy có tải

### Bước 1 — Đổi nút STOP sang NC

Đấu lại nút STOP dùng tiếp điểm **thường đóng**. Kiểm tra bằng Watch table:
**không nhấn thì `%I0.0` phải = 1**.

Sau khi đổi, **phải sửa lại NW1-T** — đảo tiếp điểm `┤/├` về `┤ ├`:

```
     in_stop_button            an_toan_ok
     ──────┤ ├──────────────────( )──────
           %I0.0                %M0.0
```

> Quên bước sửa này thì logic bị đảo ngược hoàn toàn: **không nhấn STOP thì máy
> dừng, nhấn STOP thì máy chạy**.

### Bước 2 — Lắp nút E-Stop

1. Đấu nút E-Stop kiểu **NC** vào `%I0.5`
2. Kiểm tra: không nhấn thì `%I0.5` = **1** (nếu = 0 là đấu sai kiểu)
3. Thay NW1-T bằng NW1–NW3 ở mục 6
4. Thêm lại NW6, và các nhánh `estop_chot` ở NW25, NW26
5. Chạy đủ 6 tình huống test ở mục 12.1

### Bước 3 — Mạch cắt cứng cho E-Stop

E-Stop phải cắt nguồn cơ cấu chấp hành qua **safety relay hoặc contactor**, song
song với việc đưa tín hiệu vào `%I0.5`. Chi tiết ở mục 13.

### Vì sao NC là bắt buộc, không phải "nên có"

| Tình huống | Đấu NC | Đấu NO |
|---|---|---|
| Không nhấn | `%I0.0` = 1 → chạy | `%I0.0` = 0 → chạy |
| Nhấn nút | `%I0.0` = 0 → **dừng** | `%I0.0` = 1 → **dừng** |
| **Đứt dây / lỏng cọc** | `%I0.0` = 0 → **dừng** ✅ | `%I0.0` = 0 → **vẫn chạy** ❌ |
| **Hỏng tiếp điểm** | → **dừng** ✅ | → nút vô tác dụng ❌ |

Cột cuối là toàn bộ lý do. Với NC, mọi hư hỏng đều đẩy máy về trạng thái an toàn.
Với NO, hư hỏng làm mất khả năng dừng **mà không có dấu hiệu báo trước**.

---

## 7. FC2 — Máy trạng thái

### 7.1 — Danh sách trạng thái

| # | Tên | Ngõ ra bật | Điều kiện chuyển | Kế tiếp |
|---|---|---|---|---|
| S0 | `KHOI_TAO` | — | Nhấn START | S1 |
| S1 | `DAY_PHOI` | `%Q0.4` + `%Q0.5` | Hết `T_day_phoi` (1 s) | S2 |
| S2 | `CHO_SENSOR1` | `%Q0.5` | `%I0.4` = 1 | S3 |
| S3 | `CHAY_TOI_S2` | `%Q0.5` | `%I0.2` = 1 | S4 |
| S4 | `CHO_KET_QUA` | — (dừng) | `DONE` = 1 | S5 |
| S5 | `PHAN_LOAI` | — | `kq_pass` → S6 · `kq_fail` → S7 | S6 / S7 |
| S6 | `CHO_PASS_QUA` | `%Q0.5` | `%I0.3` sườn lên | S1 |
| S7 | `CHAY_TOI_S3` | `%Q0.5` | `%I0.3` sườn lên | S8 |
| S8 | `LOAI_BO` | `%Q0.6` (dừng BC) | Hết `T_loai_bo` (5 s) | S1 |
| S99 | `LOI` | — | Nhấn STOP | S0 |

### 7.2 — Vì sao không có trạng thái chờ xy lanh thu về

Xy lanh van đơn: ngõ ra tắt là tự rút. Câu hỏi là **bao lâu sau đó mới có nguy cơ
va chạm** — và trong chu trình này, khoảng thời gian đó đã đủ dài sẵn:

| Xy lanh | Tắt ở cuối | Nguy cơ tiếp theo | Thời gian có được |
|---|---|---|---|
| Xy lanh 1 `%Q0.4` | S1 | Lần đẩy phôi kế tiếp | Cả một chu trình (~10 s+) |
| Xy lanh 2 `%Q0.6` | S8 | PCB kế tiếp tới cảm biến 3 | S1→S7 (~10 s+) |

Xy lanh rút trong dưới 1 giây, nên **thời gian chờ đã nằm sẵn trong chu trình**.
Thêm trạng thái chờ riêng chỉ làm chậm máy mà không tăng an toàn.

> **Đánh đổi phải biết:** vì không có cảm biến hành trình, PLC **không biết** xy
> lanh đã rút thật hay chưa. Nếu áp khí yếu, lò xo yếu hoặc cần bị kẹt, máy vẫn
> chạy tiếp như bình thường. Rủi ro này được chấp nhận vì biên thời gian rất
> rộng (>10 s cho thao tác <1 s). Nếu sau này lắp được **reed switch**, nên đổi
> điều kiện chuyển của S1 và S8 sang tín hiệu cảm biến thay cho timer.

### NW7 — S0 → S1: nhấn START

Viết tắt:

```
     DB2.trang_thai      chu_trinh_chay
NW7  ──[ == Int  0 ]────────┤ ├──────────[ MOVE  1 → DB2.trang_thai ]
                            %M0.1
```

**Dạng đầy đủ để dựng trong TIA** — dùng network này làm mẫu cho tất cả network
chuyển trạng thái còn lại:

```
       DB2.trang_thai
     ┌──────┴───────┐   chu_trinh_chay    ┌──── MOVE ────┐
     │    == Int    ├────────┤ ├──────────┤EN         ENO├──
     └──────┬───────┘        %M0.1      1 ┤IN       OUT1├────  DB2.trang_thai
            0                             └──────────────┘
```

Đọc từ trái sang: nếu `trang_thai` bằng 0 **và** `chu_trinh_chay` = 1 thì mạch
thông tới chân `EN` → khối MOVE chạy → ghi giá trị `1` vào `DB2.trang_thai`.

### NW8 — S1 → S2: hết thời gian kích xy lanh 1

```
     DB2.trang_thai          IDB_T_DAY (TON)
NW8  ──[ == Int  1 ]──────────┤IN      Q├────[ MOVE  2 → DB2.trang_thai ]
                    DB2.T_day_phoi┤PT   ET├
```

Rời khỏi S1 thì `%Q0.4` tự về 0 (xem NW21) → xy lanh 1 thu về trong khi băng
chuyền vẫn chở phôi đi.

### NW9 — S2 → S3: cảm biến 1 thấy phôi

```
     DB2.trang_thai      in_sensor_1
NW9  ──[ == Int  2 ]────────┤ ├──────────[ MOVE  3 → DB2.trang_thai ]
                            %I0.4
```

### NW10 — S3 → S4: tới cảm biến 2, yêu cầu PC chụp

```
     DB2.trang_thai      in_sensor_2
NW10 ──[ == Int  3 ]────────┤ ├───────┬──[ MOVE  4 → DB2.trang_thai ]
                            %I0.2     │
                                      └──[ SET  DB1.TRIGGER ]
```

Băng chuyền dừng ở S4 (xem NW20) — PCB đứng yên khi chụp ảnh.

### NW11 — S4 → S5: PC trả kết quả

```
     DB2.trang_thai      DB1.DONE
NW11 ──[ == Int  4 ]────────┤ ├───────┬──[ MOVE  5 → DB2.trang_thai ]
                                      │
                          DB1.PASS    │
                          ──┤ ├───────┼──[ SET  DB2.kq_pass ]
                                      │
                          DB1.FAIL    │
                          ──┤ ├───────┼──[ SET  DB2.kq_fail ]
                                      │
                                      └──[ RESET  DB1.TRIGGER ]
```

> **Đây là network chống lỗi tranh chấp, viết đúng thứ tự này rất quan trọng.**
> Phải **chốt** `PASS`/`FAIL` vào biến nội bộ `kq_pass`/`kq_fail` **ngay tại thời
> điểm thấy `DONE`**, trong cùng một vòng quét. Vì ngay sau khi PLC hạ `TRIGGER`,
> phía PC sẽ xoá `DONE`/`PASS`/`FAIL` để chuẩn bị phôi kế tiếp. Nếu các network
> sau còn đọc trực tiếp `DB1.PASS` thì có thể đọc phải giá trị đã bị xoá.

### NW12 — S4: timeout chờ PC

```
     DB2.trang_thai          IDB_T_PC (TON)
NW12 ──[ == Int  4 ]──────────┤IN      Q├────[ MOVE  99 → DB2.trang_thai ]
                      DB2.T_cho_pc┤PT   ET├
```

Quá 3 giây không có `DONE` → vào trạng thái lỗi. **Tuyệt đối không mặc định PASS.**

### NW13 — S5 → S6: kết quả PASS

```
     DB2.trang_thai      DB2.kq_pass
NW13 ──[ == Int  5 ]────────┤ ├──────────[ MOVE  6 → DB2.trang_thai ]
```

### NW14 — S5 → S7: kết quả FAIL

```
     DB2.trang_thai      DB2.kq_fail
NW14 ──[ == Int  5 ]────────┤ ├──────────[ MOVE  7 → DB2.trang_thai ]
```

### NW15 — S6 → S1: PCB tốt tới cảm biến 3 (sườn lên)

```
     DB2.trang_thai      in_sensor_3
NW15 ──[ == Int  6 ]────────┤P├───────┬──[ MOVE  1 → DB2.trang_thai ]
                            %I0.3     │
                       (M_edge_S6)    ├──[ INC  DB1.DEM_PASS ]
                                      ├──[ INC  DB1.DEM_TONG ]
                                      ├──[ RESET  DB2.kq_pass ]
                                      └──[ RESET  DB2.kq_fail ]
```

Tiếp điểm `┤P├` là **bắt sườn lên**, cần một bit nhớ phụ (TIA tự hỏi khi kéo vào,
đặt tên `M_edge_S6`).

### NW16 — S7 → S8: PCB lỗi tới cảm biến 3 (sườn lên)

```
     DB2.trang_thai      in_sensor_3
NW16 ──[ == Int  7 ]────────┤P├──────────[ MOVE  8 → DB2.trang_thai ]
                            %I0.3
                       (M_edge_S7)
```

### NW17 — S8 → S1: hết thời gian kích xy lanh 2

```
     DB2.trang_thai          IDB_T_LOAI (TON)
NW17 ──[ == Int  8 ]──────────┤IN      Q├──┬──[ MOVE  1 → DB2.trang_thai ]
                     DB2.T_loai_bo┤PT  ET├ │
                                           ├──[ INC  DB1.DEM_FAIL ]
                                           ├──[ INC  DB1.DEM_TONG ]
                                           ├──[ RESET  DB2.kq_pass ]
                                           └──[ RESET  DB2.kq_fail ]
```

Rời khỏi S8 thì `%Q0.6` tự về 0 → xy lanh 2 thu về trong lúc chu trình mới bắt đầu.

### NW18a/b/c — Phát hiện kẹt phôi

Ba trạng thái S2, S3, S7 đều là "băng chuyền chạy, chờ cảm biến". Quá 15 giây chưa
tới cảm biến kế tiếp → phôi kẹt hoặc rơi → báo lỗi.

> **Không gộp ba trạng thái vào một timer.** Nếu viết `IN` = (`trang_thai`=2 OR
> =3 OR =7), thì khi chuyển S2 → S3 chân `IN` **vẫn giữ mức 1 liên tục** → timer
> không reset → 15 giây bị tính gộp. Phải tách thành **ba timer độc lập**, mỗi
> cái một instance DB riêng.

**NW18a — kẹt ở S2 (chờ cảm biến 1)**

```
     DB2.trang_thai          IDB_T_KET2 (TON)
     ──[ == Int  2 ]───────────┤IN      Q├────[ MOVE  99 → DB2.trang_thai ]
                    DB2.T_ket_phoi┤PT   ET├
```

**NW18b — kẹt ở S3 (chờ cảm biến 2)**

```
     DB2.trang_thai          IDB_T_KET3 (TON)
     ──[ == Int  3 ]───────────┤IN      Q├────[ MOVE  99 → DB2.trang_thai ]
                    DB2.T_ket_phoi┤PT   ET├
```

**NW18c — kẹt ở S7 (chờ cảm biến 3, hàng lỗi)**

```
     DB2.trang_thai          IDB_T_KET7 (TON)
     ──[ == Int  7 ]───────────┤IN      Q├────[ MOVE  99 → DB2.trang_thai ]
                    DB2.T_ket_phoi┤PT   ET├
```

> Dùng chung một instance DB cho nhiều khối timer là lỗi nặng: các khối sẽ ghi đè
> dữ liệu của nhau. Mỗi khối timer luôn cần một instance riêng.

### NW19 — Thoát trạng thái lỗi

```
     DB2.trang_thai      chu_trinh_chay
NW19 ──[ == Int 99 ]────────┤/├──────────[ MOVE  0 → DB2.trang_thai ]
                            %M0.1
```

Chỉ thoát lỗi khi đã nhấn STOP. Buộc người vận hành phải xử lý sự cố rồi mới
khởi động lại được.

---

## 8. FC3 — Ngõ ra cơ cấu

### NW20 — Băng chuyền `%Q0.5`

Chạy ở S1, S2, S3, S6, S7. **Dừng** ở S4 (chụp ảnh), S5, S8 (loại bỏ).

```
     DB2.trang_thai
     ──[ == Int  1 ]──┐
     ──[ == Int  2 ]──┤
     ──[ == Int  3 ]──┤    an_toan_ok    out_bang_chuyen
     ──[ == Int  6 ]──┼───────┤ ├──────────( )──────
     ──[ == Int  7 ]──┘       %M0.0        %Q0.5
NW20
```

Nối tiếp `an_toan_ok` là lớp bảo vệ thứ hai: E-Stop cắt băng chuyền ngay lập tức
kể cả khi máy trạng thái chưa kịp chuyển.

### NW21 — Xy lanh 1 đẩy phôi `%Q0.4`

```
     DB2.trang_thai      an_toan_ok      out_xilanh_day_pcb
NW21 ──[ == Int  1 ]────────┤ ├──────────────( )──────
                            %M0.0            %Q0.4
```

### NW22 — Xy lanh 2 loại bỏ `%Q0.6`

```
     DB2.trang_thai      an_toan_ok      out_xilanh_loai_bo_pcb
NW22 ──[ == Int  8 ]────────┤ ├──────────────( )──────
                            %M0.0            %Q0.6
```

---

## 9. FC3 — Đèn báo và còi

| Đèn | Trạng thái | Ý nghĩa |
|---|---|---|
| **Xanh** `%Q0.0` | Sáng | Chu trình chạy bình thường (S1–S6) |
| **Vàng** `%Q0.1` | Sáng | Máy dừng, sẵn sàng — chờ nhấn START |
| **Vàng** `%Q0.1` | Nháy 1 Hz | Mất kết nối PC |
| **Đỏ** `%Q0.2` | Sáng | Đang xử lý PCB lỗi (S7, S8) |
| **Đỏ** `%Q0.2` | Nháy 2 Hz | Lỗi hệ thống (S99) hoặc E-Stop đang chốt |
| **Còi** `%Q0.3` | Kêu | Có PCB lỗi hoặc lỗi hệ thống |

### NW23 — Đèn xanh

```
     DB2.trang_thai              DB2.trang_thai        out_light_xanh
NW23 ──[ >= Int  1 ]────────────[ <= Int  6 ]────────────( )──────
                                                          %Q0.0
```

### NW24 — Đèn vàng

```
     DB2.trang_thai
NW24 ──[ == Int  0 ]──────────────────────┐
                                          │       out_line_vang
     DB2.pc_mat_ket_noi   %M100.5         ├─────────( )──────
     ────────┤ ├────────────┤ ├───────────┘         %Q0.1
                          (1 Hz)
```

### NW25 — Đèn đỏ

```
     DB2.trang_thai
     ──[ >= Int  7 ]──┬──[ <= Int  8 ]──┐
                                        │
     DB2.trang_thai         %M100.3     │        out_line_do
     ──[ == Int 99 ]──────────┤ ├───────┼─────────( )──────
                            (2 Hz)      │         %Q0.2
     estop_chot              %M100.3    │
     ────────┤ ├──────────────┤ ├───────┘
             %M0.3          (2 Hz)
NW25
```

### NW26 — Còi cảnh báo

```
     DB2.trang_thai
     ──[ >= Int  7 ]──┬──[ <= Int  8 ]──┐
                                        │
     DB2.trang_thai                     ├────────┐
     ──[ == Int 99 ]────────────────────┘        │   out_warning_buzzer
                                                 ├─────( )──────
     estop_chot                                  │     %Q0.3
     ────────┤ ├─────────────────────────────────┘
             %M0.3
NW26
```

> Còi kêu suốt 5 giây ở S8 sẽ rất ồn nếu tỉ lệ lỗi cao. Cân nhắc nối tiếp thêm
> `%M100.5` cho còi kêu ngắt quãng.

---

## 10. FC4 — Watchdog PC và cập nhật trạng thái

### NW27 — Bắt nhịp tim PC

```
     DB1.PC_ALIVE
     ──────┤P├──────┐            DB2.xung_alive
                    ├──────────────( )──────
     DB1.PC_ALIVE   │
     ──────┤N├──────┘
NW27
```

Bắt **cả hai sườn** vì PC đảo bit qua lại. Mỗi lần đảo sinh một xung 1 vòng quét.

### NW28 — Phát hiện mất kết nối PC

```
     DB2.xung_alive        IDB_T_ALIVE (TON)       DB2.pc_mat_ket_noi
NW28 ──────┤/├───────────────┤IN      Q├──────────────( )──────
                       T#3S  ┤PT      ET├
```

### NW29 — Chặn khởi động khi PC hỏng

> ### ⚠ ĐÃ SỬA — bản cũ dùng RESET gây kẹt máy
>
> Bản trước của tài liệu này viết:
>
> ```
> trang_thai == 0  AND  pc_mat_ket_noi  →  [ RESET chu_trinh_chay ]
> ```
>
> **Cách viết đó làm máy không bao giờ khởi động được.** Ở trạng thái chờ,
> `trang_thai = 0` luôn đúng, nên khi `pc_mat_ket_noi` = TRUE thì lệnh RESET chạy
> **mỗi vòng quét**. Tệ hơn: `FC4` được gọi **sau** `FC1`, nên lệnh RESET của FC4
> luôn ghi đè lệnh SET của FC1 trong cùng vòng quét → nhấn START bao nhiêu lần
> cũng vô ích, và **không có dấu hiệu gì** cho biết vì sao.
>
> Nguyên tắc rút ra: **không dùng một khối chạy sau để RESET biến mà khối chạy
> trước đang SET.** Muốn chặn thì đưa điều kiện vào thẳng mạch tạo ra biến đó.

**Cách đúng: bỏ hẳn network này**, thay bằng việc thêm một tiếp điểm vào mạch
latch NW4 (hoặc NW2-T ở bản test):

```
     in_start_button    pc_mat_ket_noi     an_toan_ok      chu_trinh_chay
     ──────┤P├──────┬───────┤/├───────────────┤ ├────────────( )──────
           %I0.1    │                        %M0.0           %M0.1
                    │
     chu_trinh_chay │
     ──────┤ ├──────┘
           %M0.1
```

Đặt `pc_mat_ket_noi ┤/├` **nằm ngoài nhánh song song**, sau điểm hợp nhánh:

- PC hỏng → không nhấn START khởi động được (đúng ý đồ ban đầu)
- PC hỏng giữa chu trình → mất tự giữ → máy dừng an toàn
- Không có hai khối tranh nhau ghi cùng một bit

> Nếu muốn phôi đang chạy dở được hoàn tất thay vì dừng ngay, đặt
> `pc_mat_ket_noi ┤/├` **nối tiếp với nhánh START** (trước điểm hợp nhánh) thay
> vì sau nó — khi đó nó chỉ chặn khởi động mới, không cắt tự giữ.

### NW30 — Cập nhật trạng thái cho PC đọc

```
NW30 ──┬──[ MOVE  DB2.trang_thai → DB1.TRANG_THAI_MAY ]
       │
       │   chu_trinh_chay          DB1.MAY_DANG_CHAY
       ├──────┤ ├────────────────────( )──────
       │      %M0.1
       │
       │   DB2.trang_thai            DB1.MAY_LOI
       └──[ == Int 99 ]────────────────( )──────
```

---

## 11. Bảng tổng hợp ngõ ra theo trạng thái

Dùng bảng này để kiểm tra khi chạy thử — đối chiếu đèn thực tế với cột mong đợi.

| S | Tên | `Q0.5` BC | `Q0.4` XL1 | `Q0.6` XL2 | `Q0.0` Xanh | `Q0.1` Vàng | `Q0.2` Đỏ | `Q0.3` Còi |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0 | KHOI_TAO | — | — | — | — | ● | — | — |
| 1 | DAY_PHOI | ● | ● | — | ● | — | — | — |
| 2 | CHO_SENSOR1 | ● | — | — | ● | — | — | — |
| 3 | CHAY_TOI_S2 | ● | — | — | ● | — | — | — |
| 4 | CHO_KET_QUA | — | — | — | ● | — | — | — |
| 5 | PHAN_LOAI | — | — | — | ● | — | — | — |
| 6 | CHO_PASS_QUA | ● | — | — | ● | — | — | — |
| 7 | CHAY_TOI_S3 | ● | — | — | — | — | ● | ● |
| 8 | LOAI_BO | — | — | ● | — | — | ● | ● |
| 99 | LOI | — | — | — | — | — | ✳ 2Hz | ● |
| — | E-Stop chốt | — | — | — | — | — | ✳ 2Hz | ● |

● = ON · ✳ = nháy · — = OFF

---

## 12. Thứ tự implement và test

| Bước | Việc | Cách kiểm tra |
|---|---|---|
| 1 | Tạo DB1 (16 byte, tắt Optimized), DB2 | Chạy tool Python đọc đủ 16 byte không lỗi |
| 2 | Viết FC1 — bản test NW1-T–NW3-T ([mục 6B](#6b-phiên-bản-test--chỉ-có-start-và-stop)) | Xem mục 12.1 |
| 3 | Viết FC3 phần đèn (NW23–NW26) | Ép `DB2.trang_thai` bằng tay, xem đèn đúng bảng mục 11 |
| 4 | Viết FC2 (NW7–NW19) | **Ngắt khí nén**, theo dõi `trang_thai` chuyển từng bước |
| 5 | Viết FC3 phần cơ cấu (NW20–NW22) | Vẫn ngắt khí nén, nghe tiếng van đóng mở |
| 6 | Viết FC4 (NW27–NW30) | Tắt phần mềm PC, kiểm tra đèn vàng nháy sau 3 s |
| 7 | Ghép với PC, chạy không tải | Đủ một vòng PASS và một vòng FAIL |
| 8 | Cấp khí nén, chạy phôi thật | Chỉnh `T_day_phoi`, `T_loai_bo` cho khớp cơ cấu |

**Bước 4 và 5 không được bỏ qua.**

### 12.1 — Kịch bản test nút nhấn nhả (bản đầy đủ có E-Stop)

| # | Thao tác | Kết quả đúng |
|---|---|---|
| 1 | Nhấn START rồi **buông** | `chu_trinh_chay` = 1 và **giữ nguyên** |
| 2 | Nhấn STOP rồi **buông** | `chu_trinh_chay` = 0 và **không tự bật lại** |
| 3 | Nhấn E-Stop rồi **buông** | `estop_chot` = 1 và **vẫn giữ** |
| 4 | Đang chốt E-Stop, nhấn START | Máy **không** chạy |
| 5 | Buông E-Stop, nhấn STOP | `estop_chot` = 0 |
| 6 | **Giữ** START, nhấn rồi buông STOP | Máy dừng và **không tự chạy lại** |

Tình huống 3 và 6 dễ sai nhất. Sai số 3 → E-Stop vô dụng. Sai số 6 → máy tự khởi
động bất ngờ.

### Watch table nên tạo sẵn

```
DB2.trang_thai        DB1.TRIGGER       DB1.DONE
DB2.kq_pass           DB1.PASS          DB1.FAIL
DB2.kq_fail           DB1.SO_LOI        DB2.pc_mat_ket_noi
IDB_T_DAY.ET          IDB_T_LOAI.ET     IDB_T_PC.ET
%M0.0 an_toan_ok      %M0.1 chu_trinh_chay      %M0.3 estop_chot
%IB0 (toàn bộ ngõ vào)   %QB0 (toàn bộ ngõ ra)
```

---

## 13. Những chỗ dễ sai

**Nhầm lẫn giữa hai bản ladder do kiểu đấu nút khác nhau.** Hiện đang tồn tại
song song hai cấu hình:

| | Kiểu đấu | Tiếp điểm dùng | Ladder |
|---|---|---|---|
| Đang test | STOP kiểu **NO** (nhấn = 1) | `┤/├` thường đóng | Mục 6B |
| Chạy thật | STOP + E-Stop kiểu **NC** (nhấn = 0) | `┤ ├` thường hở | Mục 6 |

Dùng nhầm tiếp điểm sẽ **đảo ngược hoàn toàn** ý nghĩa nút dừng. Mỗi lần đổi cách
đấu dây, bắt buộc kiểm tra lại `%I0.0` trong Watch table.

**Đọc trực tiếp `%I0.5` thay vì bit chốt.** Nút nhấn nhả buông ra là hết tín hiệu
→ máy tự thoát trạng thái khẩn cấp. Mọi chỗ cần biết "đang có sự cố E-Stop" phải
dùng `estop_chot` (`%M0.3`).

**Nút START dùng tiếp điểm thường thay vì `┤P├`.** Giữ START rồi nhấn STOP →
buông STOP là máy chạy lại ngay.

**Khai báo `trang_thai` là Bool.** Phải là **Int** — nó chứa giá trị 0–8 và 99.
Khai nhầm Bool thì TIA báo lỗi ngay khi dựng khối MOVE.

**Khối chạy sau RESET biến mà khối chạy trước vừa SET.** Vì FC được gọi tuần tự
trong OB1, lệnh của khối sau **luôn thắng**. Ví dụ đã gây lỗi thật: NW29 (ở FC4)
RESET `chu_trinh_chay` trong khi NW4 (ở FC1) SET nó → máy không bao giờ khởi động
được, nhấn START không có phản ứng gì. Triệu chứng đặc trưng: `an_toan_ok` = 1,
nhấn START thấy `%I0.1` lên 1, nhưng `%M0.1` vẫn = 0. Cách chữa: đưa điều kiện
chặn vào thẳng mạch latch, đừng dùng khối khác RESET.

**Thiếu NW27 làm `pc_mat_ket_noi` kẹt TRUE vĩnh viễn.** NW28 dùng
`xung_alive ┤/├` làm chân `IN`. Nếu chưa dựng NW27 thì `xung_alive` luôn FALSE →
`IN` luôn TRUE → sau 3 giây `pc_mat_ket_noi` = TRUE và không bao giờ về. Mọi thứ
phụ thuộc bit này sẽ chặn máy. Kiểm tra: đưa `xung_alive` vào Watch table, nó
phải nhấp nháy khi phần mềm PC đang chạy.

**Ghi `trang_thai` ở nhiều network cùng lúc.** Network sau ghi đè network trước →
máy nhảy cóc trạng thái. Mỗi trạng thái chỉ có đúng một đường ra (trừ S5 rẽ hai
nhánh theo `kq_pass`/`kq_fail`, hai nhánh loại trừ nhau).

**Quên chốt `PASS`/`FAIL` ở NW11.** Đọc trực tiếp `DB1.PASS` ở NW13 sẽ chập chờn
vì PC xoá bit ngay sau khi PLC hạ `TRIGGER`.

**Timer không reset vì `IN` giữ mức 1 xuyên nhiều trạng thái.** Gộp nhiều trạng
thái bằng OR thì chuyển giữa chúng không làm `IN` xuống 0 → thời gian cộng dồn.
Đây là lý do timer kẹt phôi tách thành NW18a/b/c. Kiểm tra `ET` trong Watch table.

**Dùng chung instance DB cho nhiều khối timer.** Các khối ghi đè dữ liệu của nhau,
chương trình vẫn biên dịch được nên rất khó phát hiện.

**Quên tắt "Optimized block access" cho DB1.** PLC chạy bình thường nhưng Python
đọc DB1 sẽ lỗi — dễ tưởng nhầm là lỗi mạng.

**Quên bật clock memory byte.** Các network đèn dùng `%M100.5`, `%M100.3` sẽ không
nháy, đèn cứ tắt — dễ tưởng sai logic đèn.

**E-Stop chỉ nằm trong phần mềm.** `%I0.5` chỉ để PLC *biết* mà báo đèn và chốt
trạng thái. Việc cắt nguồn cơ cấu chấp hành phải do **safety relay/contactor phần
cứng** đảm nhiệm. Bit chốt trong phần mềm **không thay thế được** mạch an toàn
phần cứng.
