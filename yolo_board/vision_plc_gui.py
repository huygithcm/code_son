#coding=utf-8
"""GUI kiem tra PCB tu dong theo chu trinh PLC — PyQt5 + YOLO + snap7.

Chay vong bat tay voi PLC theo dung giao thuc DB1 mo ta trong PLC_LADDER.md:

    PLC:  TRIGGER = 1            (PCB da dung tai cam bien 2)
    PC :  chup anh -> YOLO -> ghi SO_LOI, MA_LOI -> ghi PASS/FAIL -> DONE = 1
    PLC:  doc PASS/FAIL -> hanh dong -> TRIGGER = 0
    PC :  thay TRIGGER = 0 -> xoa DONE/PASS/FAIL, san sang phoi ke tiep

Song song do PC dao bit PC_ALIVE moi giay de PLC biet PC con song.

Chay:
    .venv\\Scripts\\python.exe yolo_board\\vision_plc_gui.py

Che do khong can phan cung (de thu giao dien / thu logic):
  - "Mo phong PLC": khong ket noi that, co nut tu tao TRIGGER
  - "Anh tu file"  : dung anh co san thay cho camera
"""
import os
import sys
import time
import struct
from datetime import datetime

import numpy as np
import cv2

# QUAN TRONG: phai import torch/ultralytics o LUONG CHINH truoc khi tao QThread.
# Tren Windows, neu de QThread import torch lan dau se loi:
#   [WinError 1114] DLL initialization routine failed ... torch\lib\c10.dll
# Hai dong duoi chi de nap DLL som, khong dung truc tiep o file nay.
import torch                             # noqa: F401
from ultralytics import YOLO             # noqa: F401

from PyQt5.QtCore import Qt, QThread, QMutex, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QSizePolicy, QSpinBox, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import detect_components as dc              # noqa: E402

try:
    import snap7
    from snap7.type import Area             # noqa: F401
    HAS_SNAP7 = True
except ImportError:
    HAS_SNAP7 = False

try:
    from camera_mv import Camera, mvsdk
    HAS_CAM = True
except Exception:
    HAS_CAM = False

MAU_OK = "#1a7f1a"
MAU_NG = "#c00000"
MAU_CHO = "#e08000"

TAC_GIA = "Nguyễn Văn Sơn"
MSSV = "42001245"

DB_SO = 1
DB_KICH_THUOC = 16          # bo tri day du; GUI tu do neu DB that nho hon
DB_TOI_THIEU = 6            # du cho byte0, byte1, SO_LOI, MA_LOI

# ----- Ban do bit trong DB1 — KHOP VOI DB THAT TREN PLC -----
# Byte 0 chua CA bit cua PLC lan cua PC, nen khi ghi phai doc-sua-ghi va giu
# nguyen cac bit cua PLC. Xem canh bao o _ghi_bit_pc().
BIT_TRIGGER      = (0, 0)       # PLC ghi
BIT_DONE         = (0, 1)       # PC  ghi
BIT_PASS         = (0, 2)       # PC  ghi
BIT_FAIL         = (0, 3)       # PC  ghi
BIT_PC_ALIVE     = (0, 4)       # PC  ghi
BIT_PC_SAN_SANG  = (0, 5)       # PC  ghi
BIT_MAY_CHAY     = (0, 6)       # PLC ghi
BIT_MAY_LOI      = (0, 7)       # PLC ghi
BIT_ESTOP        = (1, 0)       # PLC ghi

# Mat na cac bit PC so huu trong byte 0 (dung khi doc-sua-ghi)
MASK_PC_BYTE0 = sum(1 << b for (_, b) in
                    (BIT_DONE, BIT_PASS, BIT_FAIL, BIT_PC_ALIVE, BIT_PC_SAN_SANG))
W_SO_LOI, W_MA_LOI = 2, 4                       # PC ghi
W_DEM_TONG, W_DEM_PASS, W_DEM_FAIL = 6, 8, 10   # PLC ghi
W_TRANG_THAI = 12                               # PLC ghi

TEN_TRANG_THAI = {
    0: "KHOI_TAO — chờ START", 1: "DAY_PHOI — xy lanh 1",
    2: "CHO_SENSOR1", 3: "CHAY_TOI_S2", 4: "CHO_KET_QUA — chờ PC",
    5: "PHAN_LOAI", 6: "CHO_PASS_QUA", 7: "CHAY_TOI_S3 — hàng lỗi",
    8: "LOAI_BO — xy lanh 2", 99: "LỖI HỆ THỐNG",
}


def _lay_bit(data, byte, bit):
    return bool(data[byte] & (1 << bit))


# ----------------------------------------------------------------------
# Thread giao tiep PLC — SO HUU snap7 client, moi truy cap PLC deu o day
# ----------------------------------------------------------------------
class PlcWorker(QThread):
    """snap7 client khong an toan da luong, nen chi thread nay duoc cham vao PLC.
    GUI muon ghi ket qua thi goi dat_ket_qua(), thread se ghi o vong lap ke tiep."""

    yeu_cau_chup = pyqtSignal()             # TRIGGER len 1
    trang_thai = pyqtSignal(dict)           # toan bo DB1 da giai ma
    bao_loi = pyqtSignal(str)
    ket_noi_doi = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = None
        self.mo_phong = False
        self.db_kich_thuoc = DB_KICH_THUOC
        self._chay = True
        self._mutex = QMutex()
        self._cau_hinh = None               # (ip, rack, slot, mo_phong)
        self._yeu_cau_ket_noi = False
        self._yeu_cau_ngat = False
        self._ket_qua_cho = None            # (ok, so_loi, ma_loi)
        self._da_gui = False                # da ghi DONE cho phoi hien tai
        self._trigger_truoc = False
        self._alive = False
        self._t_alive = 0.0
        self._mp_trigger = False            # trigger gia lap
        self._mp_dem = {"tong": 0, "pass": 0, "fail": 0}

    # ---------- API goi tu GUI ----------
    def yeu_cau_ket_noi(self, ip, rack, slot, mo_phong):
        self._mutex.lock()
        self._cau_hinh = (ip, rack, slot, mo_phong)
        self._yeu_cau_ket_noi = True
        self._mutex.unlock()

    def yeu_cau_ngat(self):
        self._mutex.lock()
        self._yeu_cau_ngat = True
        self._mutex.unlock()

    def dat_ket_qua(self, ok, so_loi, ma_loi=0):
        self._mutex.lock()
        self._ket_qua_cho = (bool(ok), int(so_loi), int(ma_loi))
        self._mutex.unlock()

    def kich_trigger_mo_phong(self):
        self._mutex.lock()
        self._mp_trigger = True
        self._mutex.unlock()

    def dung(self):
        self._chay = False

    # ---------- doc/ghi ----------
    @property
    def da_ket_noi(self):
        if self.mo_phong:
            return True
        try:
            return self.client is not None and self.client.get_connected()
        except Exception:
            return False

    def _do_kich_thuoc_db(self):
        """DB1 tren PLC co the nho hon bo tri day du (dang lam do). Do xem doc
        duoc toi da bao nhieu byte de con giai ma dung phan co that."""
        cuoi = 0
        for n in (2, 4, 6, 8, 10, 12, 14, 16):
            try:
                self.client.db_read(DB_SO, 0, n)
                cuoi = n
            except Exception:
                break
        return cuoi

    def _doc_db(self):
        if self.mo_phong:
            d = bytearray(DB_KICH_THUOC)
            if self._mp_trigger:
                d[0] |= 1 << BIT_TRIGGER[1]
            struct.pack_into(">h", d, W_DEM_TONG, self._mp_dem["tong"])
            struct.pack_into(">h", d, W_DEM_PASS, self._mp_dem["pass"])
            struct.pack_into(">h", d, W_DEM_FAIL, self._mp_dem["fail"])
            struct.pack_into(">h", d, W_TRANG_THAI, 4 if self._mp_trigger else 0)
            return d
        d = bytearray(self.client.db_read(DB_SO, 0, self.db_kich_thuoc))
        if len(d) < DB_KICH_THUOC:              # dem 0 cho cac truong chua co
            d += bytearray(DB_KICH_THUOC - len(d))
        return d

    def _ghi_bit_pc(self, byte0_vua_doc=None):
        """Ghi cac bit PC so huu, nam CHUNG byte 0 voi bit cua PLC.

        Vi phai doc-sua-ghi ca byte, co rui ro: neu PLC set TRIGGER dung trong
        khe giua luc ta doc va luc ta ghi, gia tri moi se bi ghi de mat.
        Giam thieu bang cach dung lai byte vua doc trong cung vong lap (mới nhất
        có thể) thay vì đọc lại lần nữa.
        Cach triet de: doi NW10 ben PLC tu 'SET TRIGGER' sang cuon day thuong
        'trang_thai == 4 -> ( ) TRIGGER' de no tu phuc hoi moi vong quet.
        """
        if self.mo_phong:
            return
        goc = byte0_vua_doc
        if goc is None:
            goc = self.client.db_read(DB_SO, 0, 1)[0]
        v = goc & ~MASK_PC_BYTE0             # giu nguyen bit cua PLC
        if self._done:
            v |= 1 << BIT_DONE[1]
        if self._pass:
            v |= 1 << BIT_PASS[1]
        if self._fail:
            v |= 1 << BIT_FAIL[1]
        if self._alive:
            v |= 1 << BIT_PC_ALIVE[1]
        if self._san_sang:
            v |= 1 << BIT_PC_SAN_SANG[1]
        self.client.db_write(DB_SO, 0, bytearray([v & 0xFF]))

    def _ghi_so_lieu(self, so_loi, ma_loi):
        if self.mo_phong:
            return
        self.client.db_write(DB_SO, W_SO_LOI, bytearray(struct.pack(">h", so_loi)))
        self.client.db_write(DB_SO, W_MA_LOI, bytearray(struct.pack(">h", ma_loi)))

    # ---------- vong lap chinh ----------
    def run(self):
        self._done = self._pass = self._fail = False
        self._san_sang = False

        while self._chay:
            # --- xu ly yeu cau ket noi / ngat ---
            self._mutex.lock()
            xin_kn, xin_ngat = self._yeu_cau_ket_noi, self._yeu_cau_ngat
            cau_hinh = self._cau_hinh
            self._yeu_cau_ket_noi = self._yeu_cau_ngat = False
            self._mutex.unlock()

            if xin_ngat:
                self._ngat()
            if xin_kn:
                self._ket_noi(cau_hinh)

            if not self.da_ket_noi:
                self.msleep(200)
                continue

            try:
                self._mot_vong()
            except Exception as e:
                self.bao_loi.emit(f"Lỗi PLC: {e}")
                self._ngat()
            self.msleep(100)

        self._ngat()

    def _ket_noi(self, cau_hinh):
        ip, rack, slot, mo_phong = cau_hinh
        self.mo_phong = mo_phong
        try:
            if not mo_phong:
                self.client = snap7.client.Client()
                self.client.connect(ip, rack, slot)
                if not self.client.get_connected():
                    raise ConnectionError(f"Không kết nối được PLC {ip}")
                n = self._do_kich_thuoc_db()
                if n < DB_TOI_THIEU:
                    raise ValueError(
                        f"DB{DB_SO} chỉ đọc được {n} byte, cần tối thiểu "
                        f"{DB_TOI_THIEU}. Mở rộng DB{DB_SO} trong TIA Portal "
                        f"và tắt 'Optimized block access'.")
                self.db_kich_thuoc = n
                thieu = [ten for ten, off in (
                    ("SO_LOI", W_SO_LOI), ("MA_LOI", W_MA_LOI),
                    ("DEM_TONG", W_DEM_TONG), ("DEM_PASS", W_DEM_PASS),
                    ("DEM_FAIL", W_DEM_FAIL), ("TRANG_THAI_MAY", W_TRANG_THAI),
                ) if off + 2 > n]
                if thieu:
                    self.bao_loi.emit(
                        f"DB{DB_SO} chỉ có {n} byte — thiếu: {', '.join(thieu)} "
                        f"(sẽ hiển thị 0 và không ghi được).")
                else:
                    self.bao_loi.emit(f"DB{DB_SO} = {n} byte — đủ mọi trường.")
            else:
                self.db_kich_thuoc = DB_KICH_THUOC
            self._done = self._pass = self._fail = False
            self._da_gui = False
            self._trigger_truoc = False
            self.ket_noi_doi.emit(True)
        except Exception as e:
            self.client = None
            self.bao_loi.emit(f"Lỗi kết nối PLC: {e}")
            self.ket_noi_doi.emit(False)

    def _ngat(self):
        if self.client is not None:
            try:
                self._done = self._pass = self._fail = False
                self._san_sang = False
                self._ghi_bit_pc()
                self.client.disconnect()
            except Exception:
                pass
        self.client = None
        self.mo_phong = False
        self.ket_noi_doi.emit(False)

    def _mot_vong(self):
        d = self._doc_db()
        trigger = _lay_bit(d, *BIT_TRIGGER)

        # --- nhip tim: dao bit moi giay ---
        if time.time() - self._t_alive >= 1.0:
            self._alive = not self._alive
            self._t_alive = time.time()
            self._ghi_bit_pc(d[0])

        # --- co ket qua tu GUI -> ghi xuong PLC ---
        self._mutex.lock()
        kq = self._ket_qua_cho
        self._ket_qua_cho = None
        self._mutex.unlock()

        if kq is not None:
            ok, so_loi, ma_loi = kq
            # THU TU BAT BUOC: so lieu truoc, PASS/FAIL, DONE sau cung
            self._ghi_so_lieu(so_loi, ma_loi)
            self._pass, self._fail = ok, not ok
            self._done = True
            self._ghi_bit_pc(d[0])
            self._da_gui = True
            if self.mo_phong:
                self._mp_dem["tong"] += 1
                self._mp_dem["pass" if ok else "fail"] += 1
                self._mp_trigger = False

        # --- TRIGGER len 1 -> yeu cau GUI chup ---
        if trigger and not self._trigger_truoc and not self._da_gui:
            self.yeu_cau_chup.emit()

        # --- TRIGGER ve 0 -> don dep, san sang phoi ke tiep ---
        if not trigger and self._da_gui:
            self._done = self._pass = self._fail = False
            self._ghi_bit_pc(d[0])
            self._da_gui = False

        self._trigger_truoc = trigger

        self.trang_thai.emit({
            "trigger": trigger,
            "may_chay": _lay_bit(d, *BIT_MAY_CHAY),
            "may_loi": _lay_bit(d, *BIT_MAY_LOI),
            "estop": _lay_bit(d, *BIT_ESTOP),
            "dem_tong": struct.unpack_from(">h", d, W_DEM_TONG)[0],
            "dem_pass": struct.unpack_from(">h", d, W_DEM_PASS)[0],
            "dem_fail": struct.unpack_from(">h", d, W_DEM_FAIL)[0],
            "trang_thai_may": struct.unpack_from(">h", d, W_TRANG_THAI)[0],
        })

    def dat_san_sang(self, v):
        self._san_sang = bool(v)


# ----------------------------------------------------------------------
# Thread YOLO
# ----------------------------------------------------------------------
class YoloWorker(QThread):
    ket_qua = pyqtSignal(object, list, dict, bool, float)   # bgr, dets, rows, ok, ms
    bao_loi = pyqtSignal(str)
    model_ok = pyqtSignal()

    def __init__(self, conf=0.25, imgsz=640, parent=None):
        super().__init__(parent)
        self.conf = conf
        self.imgsz = imgsz
        self.expected = dc.load_expected()
        self._mutex = QMutex()
        self._viec = None
        self._chay = True

    def dat_viec(self, bgr, roi):
        self._mutex.lock()
        self._viec = (bgr, roi)
        self._mutex.unlock()

    def dung(self):
        self._chay = False

    def run(self):
        try:
            dc.load_model()
            self.model_ok.emit()
        except Exception as e:
            self.bao_loi.emit(f"Lỗi tải model: {e}")
            return
        while self._chay:
            self._mutex.lock()
            viec = self._viec
            self._viec = None
            self._mutex.unlock()
            if viec is None:
                self.msleep(20)
                continue
            bgr, roi = viec
            try:
                t0 = time.perf_counter()
                dets = dc.detect(bgr, self.conf, roi=roi, imgsz=self.imgsz)
                ms = (time.perf_counter() - t0) * 1000
                rows, ok_all = dc.evaluate(dets, self.expected)
                self.ket_qua.emit(bgr, dets, rows, ok_all, ms)
            except Exception as e:
                self.bao_loi.emit(f"Lỗi detect: {e}")


# ----------------------------------------------------------------------
# Vung hien thi anh
# ----------------------------------------------------------------------
class ImageView(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 320)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background: #202020; border: 1px solid #999;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setText("Chưa có ảnh")

    def hien_thi(self, bgr):
        if bgr is None or bgr.size == 0:
            return
        if bgr.ndim == 2:                       # camera mono -> doi sang 3 kenh
            bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
        if bgr.dtype != np.uint8:
            bgr = bgr.astype(np.uint8)
        bgr = np.ascontiguousarray(bgr)         # QImage doi bo nho lien tuc
        h, w = bgr.shape[:2]
        img = QImage(bgr.data, w, h, 3 * w, QImage.Format_BGR888)
        if img.isNull():
            return
        pm = QPixmap.fromImage(img)
        if pm.isNull():
            return
        self.setPixmap(pm.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))


# ----------------------------------------------------------------------
# Cua so chinh
# ----------------------------------------------------------------------
class VisionPlcWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kiểm tra PCB tự động — YOLO + PLC S7")
        self.cam = None
        self.anh_test = None
        self.roi = None
        self.dang_xu_ly = False
        self.giu_ket_qua = 0.0          # thoi diem het giu anh ket qua
        self.thu_muc_log = os.path.join(HERE, "log_ket_qua")

        self._dung_giao_dien()

        self.yolo = YoloWorker(self.sp_conf.value(), self.cbo_imgsz.currentData())
        self.yolo.ket_qua.connect(self._yolo_xong)
        self.yolo.bao_loi.connect(self._ghi_log)
        self.yolo.model_ok.connect(self._model_da_tai)
        self.yolo.start()

        self.plc = PlcWorker()
        self.plc.yeu_cau_chup.connect(self._plc_yeu_cau_chup)
        self.plc.trang_thai.connect(self._cap_nhat_trang_thai)
        self.plc.bao_loi.connect(self._ghi_log)
        self.plc.ket_noi_doi.connect(self._plc_ket_noi_doi)
        self.plc.start()

        # Live view: lay frame lien tuc tu camera de hien thi (khong chay YOLO)
        self.timer_live = QTimer(self)
        self.timer_live.timeout.connect(self._live_tick)
        self.timer_live.start(50)               # ~20 FPS

    # ------------------------------------------------------------------
    def _dung_giao_dien(self):
        trung_tam = QWidget()
        self.setCentralWidget(trung_tam)
        ngoai = QVBoxLayout(trung_tam)

        banner = QLabel(f"  Kiểm tra PCB tự động — YOLO + PLC S7        "
                        f"GVHD/SV: {TAC_GIA} · MSSV: {MSSV}")
        banner.setStyleSheet(
            "background: #123a63; color: white; padding: 8px; font-weight: bold;")
        ngoai.addWidget(banner)

        than = QHBoxLayout()
        ngoai.addLayout(than, 1)

        # ---------- trai: anh ----------
        trai = QVBoxLayout()
        self.anh = ImageView()
        trai.addWidget(self.anh, 1)

        h_kq = QHBoxLayout()
        self.lbl_kq = QLabel("—")
        self.lbl_kq.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.lbl_kq.setAlignment(Qt.AlignCenter)
        self.lbl_kq.setMinimumHeight(52)
        self.lbl_kq.setStyleSheet("border: 1px solid #999; background: #f0f0f0;")
        h_kq.addWidget(self.lbl_kq, 2)
        self.lbl_ms = QLabel("")
        self.lbl_ms.setFont(QFont("Consolas", 10))
        self.lbl_ms.setAlignment(Qt.AlignCenter)
        h_kq.addWidget(self.lbl_ms, 1)
        trai.addLayout(h_kq)
        than.addLayout(trai, 3)

        # ---------- phai: dieu khien ----------
        phai = QVBoxLayout()
        phai.addWidget(self._nhom_plc())
        phai.addWidget(self._nhom_camera())
        phai.addWidget(self._nhom_yolo())
        phai.addWidget(self._nhom_chup())
        phai.addWidget(self._nhom_trang_thai())
        phai.addWidget(self._nhom_bang_kq(), 1)
        than.addLayout(phai, 2)

        # ---------- log ----------
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        self.log.setFont(QFont("Consolas", 9))
        ngoai.addWidget(self.log)

        self.statusBar().showMessage("Đang tải model YOLO…")

    def _nhom_plc(self):
        g = QGroupBox("PLC")
        lo = QGridLayout(g)
        lo.addWidget(QLabel("IP:"), 0, 0)
        self.txt_ip = QLineEdit("192.168.0.1")
        lo.addWidget(self.txt_ip, 0, 1, 1, 2)

        lo.addWidget(QLabel("Rack/Slot:"), 1, 0)
        self.sp_rack = QSpinBox(); self.sp_rack.setRange(0, 7)
        self.sp_slot = QSpinBox(); self.sp_slot.setRange(0, 31); self.sp_slot.setValue(1)
        lo.addWidget(self.sp_rack, 1, 1)
        lo.addWidget(self.sp_slot, 1, 2)

        self.chk_mo_phong = QCheckBox("Mô phỏng PLC (không kết nối thật)")
        self.chk_mo_phong.setChecked(not HAS_SNAP7)
        lo.addWidget(self.chk_mo_phong, 2, 0, 1, 3)

        self.btn_plc_kn = QPushButton("Kết nối")
        self.btn_plc_kn.setStyleSheet("QPushButton { padding: 5px; font-weight: bold; }")
        self.btn_plc_kn.clicked.connect(self._plc_ket_noi)
        self.btn_plc_ngat = QPushButton("Ngắt")
        self.btn_plc_ngat.setStyleSheet("QPushButton { padding: 5px; font-weight: bold; }")
        self.btn_plc_ngat.clicked.connect(self.plc_ngat)
        self.btn_plc_ngat.setEnabled(False)
        lo.addWidget(self.btn_plc_kn, 3, 0, 1, 2)
        lo.addWidget(self.btn_plc_ngat, 3, 2)

        self.lbl_plc = QLabel("Chưa kết nối")
        self.lbl_plc.setStyleSheet(f"color: {MAU_NG}; font-weight: bold;")
        lo.addWidget(self.lbl_plc, 4, 0, 1, 3)

        self.btn_gia_lap = QPushButton("Giả lập TRIGGER (chỉ khi mô phỏng)")
        self.btn_gia_lap.clicked.connect(lambda: self.plc.kich_trigger_mo_phong())
        lo.addWidget(self.btn_gia_lap, 5, 0, 1, 3)
        return g

    def _nhom_camera(self):
        g = QGroupBox("Nguồn ảnh")
        lo = QHBoxLayout(g)
        self.btn_cam_kn = QPushButton("Mở camera")
        self.btn_cam_kn.clicked.connect(self._cam_mo)
        lo.addWidget(self.btn_cam_kn)
        b = QPushButton("Ảnh từ file…")
        b.clicked.connect(self._chon_anh)
        lo.addWidget(b)
        self.lbl_cam = QLabel("Chưa có")
        self.lbl_cam.setStyleSheet(f"color: {MAU_NG}; font-weight: bold;")
        lo.addWidget(self.lbl_cam)

        self.chk_live = QCheckBox("Live")
        self.chk_live.setChecked(True)
        self.chk_live.setToolTip("Hiển thị ảnh camera liên tục khi đang rảnh")
        lo.addWidget(self.chk_live)

        lo.addWidget(QLabel("Giữ KQ (s):"))
        self.sp_giu = QSpinBox()
        self.sp_giu.setRange(0, 30)
        self.sp_giu.setValue(3)
        self.sp_giu.setToolTip("Giữ ảnh kết quả bao lâu trước khi quay lại live")
        lo.addWidget(self.sp_giu)
        return g

    def _nhom_yolo(self):
        g = QGroupBox("YOLO")
        lo = QHBoxLayout(g)
        lo.addWidget(QLabel("conf:"))
        self.sp_conf = QDoubleSpinBox()
        self.sp_conf.setRange(0.05, 0.95); self.sp_conf.setSingleStep(0.05)
        self.sp_conf.setValue(0.25)
        self.sp_conf.valueChanged.connect(lambda v: setattr(self.yolo, "conf", v))
        lo.addWidget(self.sp_conf)

        lo.addWidget(QLabel("imgsz:"))
        self.cbo_imgsz = QComboBox()
        for v in (320, 416, 512, 640, 800, 960):
            self.cbo_imgsz.addItem(str(v), v)
        self.cbo_imgsz.setCurrentText("640")
        self.cbo_imgsz.currentIndexChanged.connect(
            lambda: setattr(self.yolo, "imgsz", self.cbo_imgsz.currentData()))
        lo.addWidget(self.cbo_imgsz)

        self.chk_luu = QCheckBox("Lưu ảnh kết quả")
        self.chk_luu.setChecked(True)
        lo.addWidget(self.chk_luu)
        return g

    def _nhom_chup(self):
        g = QGroupBox("Chụp ảnh (chống nhoè)")
        lo = QGridLayout(g)

        lo.addWidget(QLabel("Chờ ổn định (ms):"), 0, 0)
        self.sp_delay = QSpinBox()
        self.sp_delay.setRange(0, 2000)
        self.sp_delay.setSingleStep(50)
        self.sp_delay.setValue(300)
        self.sp_delay.setToolTip("Chờ băng chuyền dừng hẳn hết rung trước khi chụp")
        lo.addWidget(self.sp_delay, 0, 1)

        lo.addWidget(QLabel("Xả bộ đệm (frame):"), 1, 0)
        self.sp_xa = QSpinBox()
        self.sp_xa.setRange(0, 10)
        self.sp_xa.setValue(2)
        self.sp_xa.setToolTip("Bỏ N frame cũ trong bộ đệm camera — bắt buộc >0 "
                              "nếu không ảnh vẫn là lúc đang chạy")
        lo.addWidget(self.sp_xa, 1, 1)

        lo.addWidget(QLabel("Chọn nét nhất từ:"), 2, 0)
        self.sp_chon = QSpinBox()
        self.sp_chon.setRange(1, 10)
        self.sp_chon.setValue(3)
        self.sp_chon.setToolTip("Chụp N frame rồi giữ frame sắc nét nhất "
                                "(đo bằng phương sai Laplacian)")
        lo.addWidget(self.sp_chon, 2, 1)

        self.lbl_net = QLabel("độ nét: —")
        self.lbl_net.setFont(QFont("Consolas", 9))
        lo.addWidget(self.lbl_net, 3, 0, 1, 2)
        return g

    def _nhom_trang_thai(self):
        g = QGroupBox("Trạng thái máy (đọc từ PLC)")
        lo = QGridLayout(g)
        self.lbl_may = QLabel("—")
        self.lbl_may.setFont(QFont("Segoe UI", 11, QFont.Bold))
        lo.addWidget(self.lbl_may, 0, 0, 1, 4)

        self.lbl_dem_tong = QLabel("0")
        self.lbl_dem_pass = QLabel("0")
        self.lbl_dem_fail = QLabel("0")
        for i, (ten, lbl, mau) in enumerate((
                ("Tổng", self.lbl_dem_tong, "#333"),
                ("PASS", self.lbl_dem_pass, MAU_OK),
                ("FAIL", self.lbl_dem_fail, MAU_NG))):
            lo.addWidget(QLabel(f"<b>{ten}</b>"), 1, i * 2)
            lbl.setStyleSheet(f"color: {mau}; font-weight: bold; font-size: 14px;")
            lo.addWidget(lbl, 1, i * 2 + 1)

        self.lbl_co = QLabel("")
        self.lbl_co.setFont(QFont("Consolas", 9))
        lo.addWidget(self.lbl_co, 2, 0, 1, 4)
        return g

    def _nhom_bang_kq(self):
        g = QGroupBox("Chi tiết linh kiện")
        lo = QVBoxLayout(g)
        self.bang = QTreeWidget()
        self.bang.setHeaderLabels(["Linh kiện", "Tìm thấy", "Kỳ vọng", "Trạng thái"])
        self.bang.setRootIsDecorated(False)
        lo.addWidget(self.bang)
        return g

    # ------------------------------------------------------------------
    # PLC
    # ------------------------------------------------------------------
    def _plc_ket_noi(self):
        mo_phong = self.chk_mo_phong.isChecked()
        if not mo_phong and not HAS_SNAP7:
            QMessageBox.critical(self, "Thiếu thư viện", "Chưa cài python-snap7.")
            return
        self.plc.yeu_cau_ket_noi(self.txt_ip.text().strip(),
                                 self.sp_rack.value(), self.sp_slot.value(), mo_phong)

    def plc_ngat(self):
        self.plc.yeu_cau_ngat()

    def _plc_ket_noi_doi(self, ok):
        self.btn_plc_kn.setEnabled(not ok)
        self.btn_plc_ngat.setEnabled(ok)
        self.chk_mo_phong.setEnabled(not ok)
        if ok:
            mp = " (mô phỏng)" if self.plc.mo_phong else ""
            self.lbl_plc.setText(f"Đã kết nối{mp}")
            self.lbl_plc.setStyleSheet(f"color: {MAU_OK}; font-weight: bold;")
            self._ghi_log(f"Kết nối PLC thành công{mp}")
        else:
            self.lbl_plc.setText("Chưa kết nối")
            self.lbl_plc.setStyleSheet(f"color: {MAU_NG}; font-weight: bold;")

    def _cap_nhat_trang_thai(self, tt):
        s = tt["trang_thai_may"]
        self.lbl_may.setText(f"S{s} — {TEN_TRANG_THAI.get(s, '?')}")
        if tt["may_loi"] or tt["estop"]:
            mau = MAU_NG
        elif tt["may_chay"]:
            mau = MAU_OK
        else:
            mau = "#666"
        self.lbl_may.setStyleSheet(f"color: {mau};")
        self.lbl_dem_tong.setText(str(tt["dem_tong"]))
        self.lbl_dem_pass.setText(str(tt["dem_pass"]))
        self.lbl_dem_fail.setText(str(tt["dem_fail"]))
        co = []
        if tt["trigger"]:
            co.append("TRIGGER")
        if tt["may_chay"]:
            co.append("ĐANG CHẠY")
        if tt["may_loi"]:
            co.append("LỖI")
        if tt["estop"]:
            co.append("E-STOP")
        self.lbl_co.setText("  ".join(co) if co else "—")

    def _do_net(self, bgr):
        """Do do sac net bang phuong sai Laplacian — anh nhoe cho gia tri thap.

        KHONG tinh tren toan anh: cam 2592x1944 voi CV_64F can ~38MB moi lan,
        cong them temporary cua .var() la tran bo nho. Thay vao do chi tinh tren
        ROI (neu co) hoac vung giua anh, va dung float32 + meanStdDev de khong
        sinh mang trung gian lon.
        """
        H, W = bgr.shape[:2]
        if self.roi is not None:
            x0, y0, x1, y1 = self.roi
            x0 = max(0, min(int(x0), W - 2)); y0 = max(0, min(int(y0), H - 2))
            x1 = max(x0 + 1, min(int(x1), W)); y1 = max(y0 + 1, min(int(y1), H))
        else:                                   # vung giua, toi da 800x800
            w = min(800, W); h = min(800, H)
            x0 = (W - w) // 2; y0 = (H - h) // 2
            x1, y1 = x0 + w, y0 + h

        vung = bgr[y0:y1, x0:x1]
        if vung.ndim == 3:
            vung = cv2.cvtColor(vung, cv2.COLOR_BGR2GRAY)
        lap = cv2.Laplacian(vung, cv2.CV_32F)
        _, sd = cv2.meanStdDev(lap)             # khong sinh mang trung gian lon
        return float(sd[0][0]) ** 2

    def _plc_yeu_cau_chup(self):
        """PLC set TRIGGER -> cho on dinh roi moi chup (chong nhoe)."""
        if self.dang_xu_ly:
            return
        self.dang_xu_ly = True
        self.lbl_kq.setText("ĐANG CHỜ ỔN ĐỊNH…")
        self.lbl_kq.setStyleSheet(
            f"border: 1px solid #999; background: #fff8e1; color: {MAU_CHO};")
        QTimer.singleShot(self.sp_delay.value(), self._chup_that)

    def _chup_that(self):
        """Chay SAU khi da cho on dinh: xa bo dem roi chon frame net nhat."""
        self.lbl_kq.setText("ĐANG XỬ LÝ…")

        if self.cam is not None:
            # Xa bo dem: camera chay lien tuc nen frame dau tien co the la anh
            # chup TU LUC BANG CHUYEN CON CHAY -> cho bao nhieu cung van nhoe.
            for _ in range(self.sp_xa.value()):
                self._lay_anh(im_lang=True)

            tot_nhat, net_nhat = None, -1.0
            for _ in range(self.sp_chon.value()):
                f = self._lay_anh(im_lang=True)
                if f is None:
                    continue
                n = self._do_net(f)
                if n > net_nhat:
                    tot_nhat, net_nhat = f, n
            bgr = tot_nhat
            if bgr is not None:
                self.lbl_net.setText(f"độ nét: {net_nhat:.0f}")
        else:
            bgr = self.anh_test
            if bgr is not None:
                self.lbl_net.setText(f"độ nét: {self._do_net(bgr):.0f}")

        if bgr is None:
            self._ghi_log("TRIGGER nhưng chưa có nguồn ảnh — bỏ qua")
            self.dang_xu_ly = False
            self.lbl_kq.setText("—")
            self.lbl_kq.setStyleSheet("border: 1px solid #999; background: #f0f0f0;")
            return
        self.yolo.dat_viec(bgr, self.roi)

    # ------------------------------------------------------------------
    # Nguon anh
    # ------------------------------------------------------------------
    def _cam_mo(self):
        if not HAS_CAM:
            QMessageBox.warning(self, "Không có camera",
                                "Không nạp được camera_mv / mvsdk.\n"
                                "Dùng 'Ảnh từ file…' để thử.")
            return
        try:
            self.cam = Camera()
            ten = self.cam.open()
            self.lbl_cam.setText(f"Camera: {ten}")
            self.lbl_cam.setStyleSheet(f"color: {MAU_OK}; font-weight: bold;")
            self._ghi_log(f"Mở camera: {ten}")
        except Exception as e:
            self.cam = None
            QMessageBox.critical(self, "Lỗi camera", str(e))

    def _chon_anh(self):
        p, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh test", HERE,
                                           "Ảnh (*.jpg *.png *.bmp)")
        if not p:
            return
        img = cv2.imread(p)
        if img is None:
            QMessageBox.critical(self, "Lỗi", "Không đọc được ảnh.")
            return
        self.anh_test = img
        self.anh.hien_thi(img)
        self.lbl_cam.setText(f"Ảnh file: {os.path.basename(p)}")
        self.lbl_cam.setStyleSheet(f"color: {MAU_OK}; font-weight: bold;")

    def _lay_anh(self, im_lang=False):
        if self.cam is not None:
            try:
                _, rgb = self.cam.grab()
                return np.ascontiguousarray(rgb[:, :, ::-1])
            except Exception as e:
                if not im_lang:
                    self._ghi_log(f"Lỗi chụp ảnh: {e}")
                return None
        return self.anh_test

    def _live_tick(self):
        """Hien thi anh live lien tuc. Khong chay YOLO o day — YOLO chi chay khi
        PLC set TRIGGER, de khong tranh CPU voi vong bat tay."""
        if not self.chk_live.isChecked():
            return
        if self.dang_xu_ly or time.time() < self.giu_ket_qua:
            return                              # dang giu anh ket qua, khong de
        if self.cam is None:
            return
        bgr = self._lay_anh(im_lang=True)
        if bgr is None:
            return
        if self.roi is not None:
            x0, y0, x1, y1 = self.roi
            bgr = bgr.copy()
            cv2.rectangle(bgr, (x0, y0), (x1, y1), (255, 229, 0), 2)
        self.anh.hien_thi(bgr)

    # ------------------------------------------------------------------
    # Ket qua YOLO
    # ------------------------------------------------------------------
    def _model_da_tai(self):
        self.plc.dat_san_sang(True)
        self.statusBar().showMessage("Model YOLO đã sẵn sàng.")
        self._ghi_log("Model YOLO đã tải xong")

    def _yolo_xong(self, bgr, dets, rows, ok_all, ms):
        vis = dc.draw(bgr, dets)
        self.anh.hien_thi(vis)
        self.lbl_ms.setText(f"{ms:.0f} ms")

        self.bang.clear()
        so_loi = 0
        for ten, (found, exp, ok) in rows.items():
            it = QTreeWidgetItem([ten, str(found), str(exp), "PASS" if ok else "FAIL"])
            if not ok:
                so_loi += 1
                for c in range(4):
                    it.setForeground(c, Qt.red)
            self.bang.addTopLevelItem(it)

        self.lbl_kq.setText("PASS" if ok_all else "FAIL")
        self.lbl_kq.setStyleSheet(
            f"border: 2px solid {MAU_OK if ok_all else MAU_NG}; color: white;"
            f"background: {MAU_OK if ok_all else MAU_NG};")

        # gui ket qua xuong PLC (thread PLC se ghi dung thu tu)
        self.plc.dat_ket_qua(ok_all, so_loi, 0 if ok_all else 1)
        self._ghi_log(f"Kết quả: {'PASS' if ok_all else 'FAIL'} "
                      f"({so_loi} loại lỗi, {ms:.0f} ms)")

        if self.chk_luu.isChecked():
            self._luu_anh(vis, ok_all)
        self.dang_xu_ly = False
        self.giu_ket_qua = time.time() + self.sp_giu.value()   # giu anh KQ roi tra ve live

    def _luu_anh(self, vis, ok_all):
        try:
            thu_muc = os.path.join(self.thu_muc_log, "PASS" if ok_all else "FAIL")
            os.makedirs(thu_muc, exist_ok=True)
            ten = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3] + ".jpg"
            cv2.imwrite(os.path.join(thu_muc, ten), vis)
        except Exception as e:
            self._ghi_log(f"Lỗi lưu ảnh: {e}")

    # ------------------------------------------------------------------
    def _ghi_log(self, s):
        self.log.appendPlainText(f"[{datetime.now():%H:%M:%S}] {s}")

    def closeEvent(self, e):
        self.timer_live.stop()
        self.plc.dat_san_sang(False)
        self.plc.yeu_cau_ngat()
        self.plc.dung()
        self.plc.wait(1500)
        self.yolo.dung()
        self.yolo.wait(1500)
        if self.cam is not None:
            try:
                self.cam.close()
            except Exception:
                pass
        e.accept()


def main():
    app = QApplication(sys.argv)
    win = VisionPlcWindow()
    win.resize(1250, 780)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
