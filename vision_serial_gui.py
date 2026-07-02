# -*- coding: utf-8 -*-
"""
Giao dien Vision Camera - PLC (PyQt5) + YOLO dem linh kien.

- ANH TRUC TIEP: live camera MindVision, ve box YOLO, keo chuot chon ROI
- KET QUA XU LY: bang dem linh kien (found/exp) -> PASS/FAIL tung loai + OK/NG tong
- CAU HINH CAMERA (MindVision): ket noi / ngat camera
- CAU HINH PLC (S7-1200/1500): ket noi qua snap7; PLC bat bit TRIGGER -> tu dong
  chup + detect -> ghi ket qua PASS/FAIL + so loai NG xuong DB cua PLC

Vung nho DB tren PLC (mac dinh DB1, doi duoc trong o "DB" va "Byte KQ"):
  DBX{b}.0 = PASS   DBX{b}.1 = FAIL   DBX{b}.2 = TRIGGER (PLC set, PC doc & xoa)
  DBW{b+2} = so loai linh kien NG
  (TIA Portal: bat Permit PUT/GET + tat Optimized block access cho DB)

Chay:  run_gui.bat  (hoac .venv\\Scripts\\python.exe vision_serial_gui.py)
"""

import os
import sys
import time
from datetime import datetime

# QUAN TRONG: import torch/ultralytics TRUOC PyQt5. Neu PyQt5 nap DLL truoc,
# torch se loi "WinError 1114 ... c10.dll" (xung dot DLL tren Windows).
# Ngoai ra khong duoc import torch lan dau trong QThread (access violation).
import torch                             # noqa: F401
from ultralytics import YOLO             # noqa: F401

import cv2
import numpy as np

from PyQt5.QtCore import Qt, QTimer, QThread, QMutex, pyqtSignal, QRect
from PyQt5.QtGui import QFont, QImage, QPixmap, QPainter, QPen, QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QComboBox,
    QLineEdit, QTextEdit, QGroupBox, QGridLayout, QHBoxLayout, QVBoxLayout,
    QToolButton, QFrame, QSizePolicy, QStyle, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QAbstractItemView, QCheckBox,
)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "yolo_board"))

import detect_components as dc           # detect(), evaluate(), draw(), load_expected()

try:
    from plc_s7 import S7                # yolo_board/plc_s7.py (python-snap7)
    HAS_SNAP7 = True
except ImportError:
    HAS_SNAP7 = False

MAU_OK = "#1a7f1a"
MAU_NG = "#c00000"
MAU_PLC = "#0000c0"


# ----------------------------------------------------------------------
# Thread chay YOLO (khong block giao dien)
# ----------------------------------------------------------------------
class YoloWorker(QThread):
    ket_qua = pyqtSignal(list, dict, bool, float)   # dets, rows, ok_all, ms
    bao_loi = pyqtSignal(str)
    model_ok = pyqtSignal()

    def __init__(self, conf=0.25, imgsz=640, parent=None):
        super().__init__(parent)
        self.conf = conf
        self.imgsz = imgsz
        self.expected = dc.load_expected()
        self._mutex = QMutex()
        self._frame = None              # frame moi nhat cho detect
        self._roi = None
        self._chay = True

    def dua_frame(self, bgr, roi):
        """GUI goi moi khi co frame moi; worker chi xu ly frame MOI NHAT."""
        self._mutex.lock()
        self._frame = bgr
        self._roi = roi
        self._mutex.unlock()

    def dung(self):
        self._chay = False

    def run(self):
        try:
            dc.load_model()             # tai model 1 lan (cham ~vai giay)
            self.model_ok.emit()
        except Exception as e:
            self.bao_loi.emit(f"Lỗi tải model: {e}")
            return
        while self._chay:
            self._mutex.lock()
            frame, roi = self._frame, self._roi
            self._frame = None
            self._mutex.unlock()
            if frame is None:
                self.msleep(10)
                continue
            try:
                t0 = time.perf_counter()
                dets = dc.detect(frame, self.conf, roi=roi, imgsz=self.imgsz)
                ms = (time.perf_counter() - t0) * 1000
                rows, ok_all = dc.evaluate(dets, self.expected)
                self.ket_qua.emit(dets, rows, ok_all, ms)
            except Exception as e:
                self.bao_loi.emit(f"Lỗi detect: {e}")


# ----------------------------------------------------------------------
# Vung hien thi anh: keo chuot chon ROI (toa do tra ve theo anh goc)
# ----------------------------------------------------------------------
class ImageView(QLabel):
    roi_chon = pyqtSignal(tuple)        # (x0, y0, x1, y1) theo anh goc

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(380, 300)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background: #202020; border: 1px solid #999;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.CrossCursor)
        self._kich_thuoc_anh = None     # (w, h) anh goc
        self._diem_dau = None
        self._diem_cuoi = None

    def hien_thi(self, bgr):
        h, w = bgr.shape[:2]
        self._kich_thuoc_anh = (w, h)
        img = QImage(bgr.data, w, h, 3 * w, QImage.Format_BGR888)
        self.setPixmap(QPixmap.fromImage(img).scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _vung_pixmap(self):
        """QRect cua pixmap ben trong label (pixmap duoc can giua)."""
        pm = self.pixmap()
        if pm is None:
            return None
        x = (self.width() - pm.width()) // 2
        y = (self.height() - pm.height()) // 2
        return QRect(x, y, pm.width(), pm.height())

    def _sang_toa_do_anh(self, pos):
        """Doi diem chuot (label) -> toa do tren anh goc."""
        r = self._vung_pixmap()
        if r is None or self._kich_thuoc_anh is None:
            return None
        w_goc, h_goc = self._kich_thuoc_anh
        tx = (pos.x() - r.x()) * w_goc / r.width()
        ty = (pos.y() - r.y()) * h_goc / r.height()
        return (int(max(0, min(tx, w_goc - 1))), int(max(0, min(ty, h_goc - 1))))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._diem_dau = e.pos()
            self._diem_cuoi = e.pos()

    def mouseMoveEvent(self, e):
        if self._diem_dau is not None:
            self._diem_cuoi = e.pos()
            self.update()

    def mouseReleaseEvent(self, e):
        if self._diem_dau is None:
            return
        p0 = self._sang_toa_do_anh(self._diem_dau)
        p1 = self._sang_toa_do_anh(e.pos())
        self._diem_dau = self._diem_cuoi = None
        self.update()
        if p0 and p1:
            x0, x1 = sorted((p0[0], p1[0]))
            y0, y1 = sorted((p0[1], p1[1]))
            if x1 - x0 >= 8 and y1 - y0 >= 8:
                self.roi_chon.emit((x0, y0, x1, y1))

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._diem_dau is not None and self._diem_cuoi is not None:
            p = QPainter(self)
            p.setPen(QPen(QColor("#00e5ff"), 2))
            p.drawRect(QRect(self._diem_dau, self._diem_cuoi))
            p.end()


# ----------------------------------------------------------------------
# Cua so chinh
# ----------------------------------------------------------------------
class VisionSerialWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vision Camera - PLC  |  YOLO đếm linh kiện")
        self.resize(1280, 660)

        self.cam = None                 # camera_mv.Camera (da mo)
        self.plc = None                 # plc_s7.S7 (da ket noi)

        self.frame_hien_tai = None      # frame BGR moi nhat
        self.dets_cuoi = []             # ket qua YOLO cuoi (ve overlay)
        self.rows_cuoi = {}
        self.ok_cuoi = None
        self.roi = None                 # (x0,y0,x1,y1) theo anh goc
        self.cho_gui_plc = False        # True: gui ket qua xuong PLC ngay khi detect xong
        self._trigger_truoc = False     # chong lap trigger (canh len)

        self._build_ui()

        # worker YOLO chay nen
        self.worker = YoloWorker(conf=0.25, imgsz=640)
        self.worker.ket_qua.connect(self._nhan_ket_qua)
        self.worker.bao_loi.connect(lambda m: self.ghi_log("VISION", m, MAU_NG))
        self.worker.model_ok.connect(
            lambda: self.ghi_log("VISION", "Model YOLO sẵn sàng", MAU_OK))
        self.worker.start()
        self.ghi_log("VISION", "Đang tải model YOLO (best.pt)...", "#c07000")

        # timer lay frame camera (live view)
        self.timer_cam = QTimer(self)
        self.timer_cam.timeout.connect(self._tick_camera)

        # timer doc bit trigger tu PLC
        self.timer_plc = QTimer(self)
        self.timer_plc.timeout.connect(self._doc_trigger_plc)

        # dong ho thanh trang thai
        self.timer_clock = QTimer(self)
        self.timer_clock.timeout.connect(self._cap_nhat_gio)
        self.timer_clock.start(1000)
        self._cap_nhat_gio()

    # ------------------------------------------------------------------
    # Dung giao dien
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)

        body = QHBoxLayout()
        root.addLayout(body, 1)

        # ===== Cot trai: anh truc tiep + log =====
        cot_trai = QVBoxLayout()
        body.addLayout(cot_trai, 4)

        grp_anh = self._tao_group("ẢNH TRỰC TIẾP")
        lay_anh = QVBoxLayout(grp_anh)

        thanh_cc = QHBoxLayout()
        style = self.style()

        def nut_cc(icon, tip, slot):
            nut = QToolButton()
            nut.setIcon(style.standardIcon(icon))
            nut.setToolTip(tip)
            nut.clicked.connect(slot)
            thanh_cc.addWidget(nut)
            return nut

        self.btn_live = nut_cc(QStyle.SP_MediaPlay, "Bật/tắt live camera", self.bat_tat_live)
        nut_cc(QStyle.SP_DialogYesButton, "Chụp + detect 1 lần", self.chup_va_detect)
        nut_cc(QStyle.SP_DirOpenIcon, "Mở ảnh từ file (test không cần camera)", self.mo_anh)

        btn_auto_roi = QPushButton("Auto ROI (HSV)")
        btn_auto_roi.clicked.connect(self.auto_roi_hsv)
        thanh_cc.addWidget(btn_auto_roi)
        btn_xoa_roi = QPushButton("Xóa ROI")
        btn_xoa_roi.clicked.connect(self.xoa_roi)
        thanh_cc.addWidget(btn_xoa_roi)
        thanh_cc.addStretch(1)
        lay_anh.addLayout(thanh_cc)

        self.view_anh = ImageView()
        self.view_anh.roi_chon.connect(self._dat_roi)
        lay_anh.addWidget(self.view_anh, 1)

        dong_tt = QHBoxLayout()
        dong_tt.addWidget(QLabel("Trạng thái:"))
        self.lbl_trang_thai_cam = QLabel("Sẵn sàng")
        self.lbl_trang_thai_cam.setStyleSheet(f"color: {MAU_OK}; font-weight: bold;")
        dong_tt.addWidget(self.lbl_trang_thai_cam)
        dong_tt.addStretch(1)
        dong_tt.addWidget(QLabel("Kéo chuột trên ảnh để chọn ROI"))
        lay_anh.addLayout(dong_tt)
        cot_trai.addWidget(grp_anh, 3)

        grp_log = self._tao_group("LOG HỆ THỐNG")
        lay_log = QVBoxLayout(grp_log)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("Consolas", 9))
        lay_log.addWidget(self.txt_log)
        cot_trai.addWidget(grp_log, 2)

        # ===== Cot giua: ket qua YOLO =====
        cot_giua = QVBoxLayout()
        body.addLayout(cot_giua, 3)

        grp_kq = self._tao_group("KẾT QUẢ XỬ LÝ")
        lay_kq = QVBoxLayout(grp_kq)
        lay_kq.setContentsMargins(12, 8, 12, 8)

        self.lbl_tong = QLabel("--")
        self.lbl_tong.setFont(QFont("Segoe UI", 44, QFont.Black))
        self.lbl_tong.setStyleSheet("color: #888;")
        self.lbl_tong.setAlignment(Qt.AlignCenter)
        lay_kq.addWidget(self.lbl_tong)

        # bang dem linh kien: ten | dem duoc | can | PASS/FAIL
        self.bang_kq = QTableWidget(0, 4)
        self.bang_kq.setHorizontalHeaderLabels(["Linh kiện", "Đếm", "Cần", "KQ"])
        self.bang_kq.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3):
            self.bang_kq.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.bang_kq.verticalHeader().setVisible(False)
        self.bang_kq.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.bang_kq.setSelectionMode(QAbstractItemView.NoSelection)
        self.bang_kq.setFont(QFont("Segoe UI", 10))
        lay_kq.addWidget(self.bang_kq, 1)
        cot_giua.addWidget(grp_kq, 4)

        grp_tg = self._tao_group("THỜI GIAN XỬ LÝ")
        lay_tg = QVBoxLayout(grp_tg)
        self.lbl_thoi_gian = QLabel("-- ms")
        self.lbl_thoi_gian.setFont(QFont("Segoe UI", 12, QFont.Bold))
        lay_tg.addWidget(self.lbl_thoi_gian)
        cot_giua.addWidget(grp_tg, 1)

        # ===== Cot phai: camera + PLC =====
        cot_phai = QVBoxLayout()
        body.addLayout(cot_phai, 3)

        # --- Camera MindVision ---
        grp_cam = self._tao_group("CẤU HÌNH CAMERA (MindVision)", mau=MAU_NG)
        lay_cam = QGridLayout(grp_cam)
        self.lbl_ten_cam = QLabel("--")
        self.lbl_tt_cam = QLabel("Chưa kết nối")
        self.lbl_tt_cam.setStyleSheet(f"color: {MAU_NG}; font-weight: bold;")
        lay_cam.addWidget(QLabel("Thiết bị:"), 0, 0)
        lay_cam.addWidget(self.lbl_ten_cam, 0, 1)
        lay_cam.addWidget(QLabel("Trạng thái:"), 1, 0)
        lay_cam.addWidget(self.lbl_tt_cam, 1, 1)

        self.btn_cam_ket_noi = QPushButton("KẾT NỐI CAMERA")
        self.btn_cam_ket_noi.setStyleSheet(
            f"QPushButton {{ background: #d9f2d9; border: 1px solid {MAU_OK};"
            f" padding: 5px; font-weight: bold; }}")
        self.btn_cam_ket_noi.clicked.connect(self.ket_noi_camera)
        self.btn_cam_ngat = QPushButton("NGẮT CAMERA")
        self.btn_cam_ngat.setStyleSheet("QPushButton { padding: 5px; font-weight: bold; }")
        self.btn_cam_ngat.clicked.connect(self.ngat_camera)
        dong_cam = QHBoxLayout()
        dong_cam.addWidget(self.btn_cam_ket_noi)
        dong_cam.addWidget(self.btn_cam_ngat)
        lay_cam.addLayout(dong_cam, 2, 0, 1, 2)
        cot_phai.addWidget(grp_cam)

        # --- PLC S7 ---
        grp_plc = self._tao_group("CẤU HÌNH PLC (S7-1200/1500)", mau=MAU_NG)
        lay_plc = QGridLayout(grp_plc)
        self.txt_plc_ip = QLineEdit("192.168.1.10")
        self.txt_plc_rack = QLineEdit("0")
        self.txt_plc_slot = QLineEdit("1")
        self.txt_plc_db = QLineEdit("1")
        self.txt_plc_byte = QLineEdit("0")
        for i, (nhan, w) in enumerate([
            ("IP Address:", self.txt_plc_ip),
            ("Rack:", self.txt_plc_rack),
            ("Slot:", self.txt_plc_slot),
            ("DB:", self.txt_plc_db),
            ("Byte KQ:", self.txt_plc_byte),
        ]):
            lay_plc.addWidget(QLabel(nhan), i, 0)
            lay_plc.addWidget(w, i, 1)

        self.chk_trigger = QCheckBox("Nhận trigger từ PLC (DBX.2)")
        self.chk_trigger.setChecked(True)
        lay_plc.addWidget(self.chk_trigger, 5, 0, 1, 2)

        self.btn_plc_ket_noi = QPushButton("KẾT NỐI PLC")
        self.btn_plc_ket_noi.setStyleSheet(
            f"QPushButton {{ background: #f7d9d9; border: 1px solid {MAU_NG};"
            f" color: {MAU_NG}; padding: 5px; font-weight: bold; }}")
        self.btn_plc_ket_noi.clicked.connect(self.ket_noi_plc)
        self.btn_plc_ngat = QPushButton("NGẮT PLC")
        self.btn_plc_ngat.setStyleSheet("QPushButton { padding: 5px; font-weight: bold; }")
        self.btn_plc_ngat.clicked.connect(self.ngat_plc)
        dong_plc = QHBoxLayout()
        dong_plc.addWidget(self.btn_plc_ket_noi)
        dong_plc.addWidget(self.btn_plc_ngat)
        lay_plc.addLayout(dong_plc, 6, 0, 1, 2)
        cot_phai.addWidget(grp_plc)

        # --- Thong tin ket noi PLC ---
        grp_tt = self._tao_group("THÔNG TIN KẾT NỐI PLC")
        lay_tt = QGridLayout(grp_tt)
        self.lbl_plc_trang_thai = QLabel("Disconnected")
        self.lbl_plc_trang_thai.setStyleSheet(f"color: {MAU_NG}; font-weight: bold;")
        self.lbl_plc_cpu = QLabel("--")
        self.lbl_plc_luc = QLabel("--")
        self.lbl_plc_gui_cuoi = QLabel("--")
        for i, (nhan, w) in enumerate([
            ("Trạng thái:", self.lbl_plc_trang_thai),
            ("CPU:", self.lbl_plc_cpu),
            ("Kết nối lúc:", self.lbl_plc_luc),
            ("Gửi KQ lúc:", self.lbl_plc_gui_cuoi),
        ]):
            lay_tt.addWidget(QLabel(nhan), i, 0)
            lay_tt.addWidget(w, i, 1)
        cot_phai.addWidget(grp_tt)

        # --- Lenh dieu khien ---
        grp_lenh = self._tao_group("LỆNH ĐIỀU KHIỂN")
        lay_lenh = QGridLayout(grp_lenh)
        btn_gui_plc = QPushButton("GỬI KQ → PLC")
        btn_gui_plc.setStyleSheet("QPushButton { padding: 6px; font-weight: bold; }")
        btn_gui_plc.clicked.connect(self.gui_ket_qua_plc)
        btn_xoa = QPushButton("XÓA LOG")
        btn_xoa.setStyleSheet("QPushButton { padding: 6px; font-weight: bold; }")
        btn_xoa.clicked.connect(self.txt_log.clear)
        btn_thoat = QPushButton("THOÁT")
        btn_thoat.setStyleSheet("QPushButton { padding: 6px; font-weight: bold; }")
        btn_thoat.clicked.connect(self.close)
        lay_lenh.addWidget(btn_gui_plc, 0, 0, 1, 2)
        lay_lenh.addWidget(btn_xoa, 1, 0)
        lay_lenh.addWidget(btn_thoat, 1, 1)
        cot_phai.addWidget(grp_lenh)
        cot_phai.addStretch(1)

        # ===== Thanh trang thai =====
        thanh_duoi = QFrame()
        thanh_duoi.setFrameShape(QFrame.StyledPanel)
        lay_duoi = QHBoxLayout(thanh_duoi)
        lay_duoi.setContentsMargins(8, 3, 8, 3)
        self.lbl_sb_cam = QLabel("Camera: Chưa kết nối")
        self.lbl_sb_cam.setStyleSheet(f"color: {MAU_NG}; font-weight: bold;")
        self.lbl_sb_plc = QLabel("PLC: Chưa kết nối")
        self.lbl_sb_plc.setStyleSheet(f"color: {MAU_NG}; font-weight: bold;")
        self.lbl_sb_gio = QLabel("")
        lay_duoi.addWidget(self.lbl_sb_cam)
        lay_duoi.addWidget(QLabel("|"))
        lay_duoi.addWidget(self.lbl_sb_plc)
        lay_duoi.addStretch(1)
        lay_duoi.addWidget(self.lbl_sb_gio)
        root.addWidget(thanh_duoi)

    @staticmethod
    def _tao_group(tieu_de, mau=MAU_OK):
        grp = QGroupBox(tieu_de)
        grp.setStyleSheet(
            f"QGroupBox {{ font-weight: bold; color: {mau}; border: 1px solid #bbb;"
            f" border-radius: 4px; margin-top: 8px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 3px; }}")
        return grp

    # ------------------------------------------------------------------
    # Log + trang thai
    # ------------------------------------------------------------------
    def ghi_log(self, nguon, thong_diep, mau="#000000"):
        gio = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.txt_log.append(
            f'[{gio}] <span style="color:{mau}; font-weight:bold;">{nguon}:</span> {thong_diep}')

    def _cap_nhat_gio(self):
        self.lbl_sb_gio.setText(datetime.now().strftime("%H:%M:%S"))

    # ------------------------------------------------------------------
    # Camera MindVision
    # ------------------------------------------------------------------
    def ket_noi_camera(self):
        if self.cam is not None:
            self.ghi_log("CAMERA", "Camera đã kết nối rồi", "#c07000")
            return
        try:
            from camera_mv import Camera
            self.cam = Camera()
            ten = self.cam.open()
        except Exception as e:
            self.cam = None
            self.ghi_log("CAMERA", f"Không mở được camera: {e}", MAU_NG)
            self.ghi_log("CAMERA", "Dùng nút 'Mở ảnh' để test không cần camera", "#c07000")
            return
        self.lbl_ten_cam.setText(ten)
        self.lbl_tt_cam.setText("Connected")
        self.lbl_tt_cam.setStyleSheet(f"color: {MAU_OK}; font-weight: bold;")
        self.lbl_sb_cam.setText(f"Camera: {ten} - Connected")
        self.lbl_sb_cam.setStyleSheet(f"color: {MAU_OK}; font-weight: bold;")
        self.ghi_log("CAMERA", f"Đã kết nối: {ten}", MAU_OK)

    def ngat_camera(self):
        if self.timer_cam.isActive():
            self.timer_cam.stop()
            self.lbl_trang_thai_cam.setText("Đã dừng live")
        if self.cam is not None:
            try:
                self.cam.close()
            except Exception:
                pass
            self.cam = None
            self.ghi_log("CAMERA", "Đã ngắt camera", "#c07000")
        self.lbl_ten_cam.setText("--")
        self.lbl_tt_cam.setText("Chưa kết nối")
        self.lbl_tt_cam.setStyleSheet(f"color: {MAU_NG}; font-weight: bold;")
        self.lbl_sb_cam.setText("Camera: Chưa kết nối")
        self.lbl_sb_cam.setStyleSheet(f"color: {MAU_NG}; font-weight: bold;")

    def bat_tat_live(self):
        if self.timer_cam.isActive():
            self.timer_cam.stop()
            self.lbl_trang_thai_cam.setText("Đã dừng live")
            self.ghi_log("VISION", "Dừng live view", "#c07000")
            return
        if self.cam is None:
            self.ket_noi_camera()       # tu ket noi neu chua
            if self.cam is None:
                return
        self.timer_cam.start(30)
        self.lbl_trang_thai_cam.setText("Đang live")
        self.ghi_log("VISION", "Bắt đầu live view", MAU_OK)

    def _tick_camera(self):
        try:
            _, rgb = self.cam.grab(timeout_ms=500)
        except Exception:
            return                      # frame loi/timeout -> bo qua
        self.frame_hien_tai = np.ascontiguousarray(rgb[:, :, ::-1])
        self.worker.dua_frame(self.frame_hien_tai, self.roi)
        self._ve_hien_thi()

    def mo_anh(self):
        duong_dan, _ = QFileDialog.getOpenFileName(
            self, "Chọn ảnh board", HERE, "Ảnh (*.jpg *.jpeg *.png *.bmp)")
        if not duong_dan:
            return
        bgr = cv2.imread(duong_dan)
        if bgr is None:
            self.ghi_log("VISION", f"Không đọc được ảnh: {duong_dan}", MAU_NG)
            return
        self.frame_hien_tai = bgr
        self.ghi_log("VISION", f"Đã mở ảnh: {os.path.basename(duong_dan)}", MAU_OK)
        self.worker.dua_frame(bgr, self.roi)
        self._ve_hien_thi()

    def chup_va_detect(self):
        """Chup 1 frame (hoac dung frame hien tai) va detect 1 lan."""
        if self.cam is not None and not self.timer_cam.isActive():
            try:
                _, rgb = self.cam.grab(timeout_ms=1000)
                self.frame_hien_tai = np.ascontiguousarray(rgb[:, :, ::-1])
            except Exception as e:
                self.ghi_log("VISION", f"Lỗi chụp ảnh: {e}", MAU_NG)
        if self.frame_hien_tai is None:
            self.ghi_log("VISION", "Chưa có ảnh (kết nối camera hoặc mở ảnh trước)", MAU_NG)
            return
        self.ghi_log("VISION", "Chụp ảnh thành công", MAU_OK)
        self.worker.dua_frame(self.frame_hien_tai, self.roi)

    # ------------------------------------------------------------------
    # ROI
    # ------------------------------------------------------------------
    def _dat_roi(self, roi):
        self.roi = roi
        self.ghi_log("VISION", f"ROI = {roi}", MAU_PLC)
        self._ve_hien_thi()

    def xoa_roi(self):
        self.roi = None
        self.ghi_log("VISION", "Đã xóa ROI", MAU_PLC)
        self._ve_hien_thi()

    def auto_roi_hsv(self):
        """Tu dong dat ROI quanh board bang nguong HSV (segment_board)."""
        if self.frame_hien_tai is None:
            self.ghi_log("VISION", "Chưa có ảnh để tìm ROI", MAU_NG)
            return
        try:
            from segment_board import board_bbox
        except ImportError as e:
            self.ghi_log("VISION", f"Không import được segment_board: {e}", MAU_NG)
            return
        bgr = self.frame_hien_tai
        H, W = bgr.shape[:2]
        bb = board_bbox(bgr, margin=80, scale=1.0)
        if bb is None:
            self.ghi_log("VISION", "HSV: không tách được board", MAU_NG)
            return
        x, y, w, h = bb
        ex, ey = int(w * 0.08), int(h * 0.08)   # noi rong de khong cat linh kien mep
        self._dat_roi((max(0, x - ex), max(0, y - ey),
                       min(W, x + w + ex), min(H, y + h + ey)))

    # ------------------------------------------------------------------
    # Nhan ket qua tu worker YOLO
    # ------------------------------------------------------------------
    def _nhan_ket_qua(self, dets, rows, ok_all, ms):
        self.dets_cuoi = dets
        self.rows_cuoi = rows
        self.ok_cuoi = ok_all
        self.lbl_thoi_gian.setText(f"{ms:.1f} ms  (~{1000 / ms:.1f} FPS)" if ms > 0 else "-- ms")

        self.lbl_tong.setText("OK" if ok_all else "NG")
        self.lbl_tong.setStyleSheet(f"color: {MAU_OK if ok_all else MAU_NG};")

        self.bang_kq.setRowCount(len(rows))
        for i, (ten, (found, exp, ok)) in enumerate(rows.items()):
            for j, gia_tri in enumerate([ten, str(found), str(exp),
                                         "PASS" if ok else "FAIL"]):
                item = QTableWidgetItem(gia_tri)
                if j:
                    item.setTextAlignment(Qt.AlignCenter)
                item.setBackground(QColor("#c8e6c9" if ok else "#ffcdd2"))
                self.bang_kq.setItem(i, j, item)

        if not self.timer_cam.isActive():
            self._ve_hien_thi()         # dang xem anh tinh -> ve lai overlay

        if self.cho_gui_plc:            # detect nay do PLC trigger -> tra ket qua ngay
            self.cho_gui_plc = False
            self.gui_ket_qua_plc()

    def _ve_hien_thi(self):
        if self.frame_hien_tai is None:
            return
        vis = dc.draw(self.frame_hien_tai, self.dets_cuoi)
        if self.roi:
            x0, y0, x1, y1 = self.roi
            cv2.rectangle(vis, (x0, y0), (x1, y1), (255, 229, 0), 2)   # ROI mau cyan (BGR)
        self.view_anh.hien_thi(vis)

    # ------------------------------------------------------------------
    # PLC S7 (snap7)
    # ------------------------------------------------------------------
    def _plc_dia_chi(self):
        """Doc DB va byte ket qua tu o nhap lieu."""
        return int(self.txt_plc_db.text().strip()), int(self.txt_plc_byte.text().strip())

    def ket_noi_plc(self):
        if not HAS_SNAP7:
            QMessageBox.warning(self, "Thiếu thư viện",
                                "Chưa cài python-snap7:  pip install python-snap7")
            return
        if self.plc is not None and self.plc.connected:
            self.ghi_log("PLC", "PLC đã kết nối rồi", "#c07000")
            return
        ip = self.txt_plc_ip.text().strip()
        try:
            rack = int(self.txt_plc_rack.text().strip())
            slot = int(self.txt_plc_slot.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Lỗi", "Rack/Slot không hợp lệ")
            return
        self.ghi_log("PLC", f"Đang kết nối {ip} (rack={rack}, slot={slot})...", MAU_PLC)
        QApplication.processEvents()    # hien log truoc vi connect co the cho vai giay
        try:
            self.plc = S7(ip, rack, slot).connect()
        except Exception as e:
            self.plc = None
            self.ghi_log("PLC", f"Lỗi kết nối: {e}", MAU_NG)
            return

        cpu = "--"
        try:
            info = self.plc.client.get_cpu_info()
            cpu = info.ModuleTypeName.decode(errors="ignore").strip("\x00")
        except Exception:
            pass
        self.lbl_plc_trang_thai.setText("Connected")
        self.lbl_plc_trang_thai.setStyleSheet(f"color: {MAU_OK}; font-weight: bold;")
        self.lbl_plc_cpu.setText(cpu)
        self.lbl_plc_luc.setText(datetime.now().strftime("%H:%M:%S"))
        self.lbl_sb_plc.setText(f"PLC: {ip} - Connected")
        self.lbl_sb_plc.setStyleSheet(f"color: {MAU_OK}; font-weight: bold;")
        self.ghi_log("PLC", f"Đã kết nối PLC {ip} ({cpu})", MAU_OK)

        self._trigger_truoc = False
        self.timer_plc.start(100)       # doc bit trigger 10 lan/giay

    def ngat_plc(self):
        self.timer_plc.stop()
        if self.plc is not None:
            self.plc.disconnect()
            self.plc = None
            self.ghi_log("PLC", "Đã ngắt kết nối PLC", "#c07000")
        self.lbl_plc_trang_thai.setText("Disconnected")
        self.lbl_plc_trang_thai.setStyleSheet(f"color: {MAU_NG}; font-weight: bold;")
        self.lbl_plc_cpu.setText("--")
        self.lbl_plc_luc.setText("--")
        self.lbl_sb_plc.setText("PLC: Chưa kết nối")
        self.lbl_sb_plc.setStyleSheet(f"color: {MAU_NG}; font-weight: bold;")

    def _doc_trigger_plc(self):
        """PLC set DBX{byte}.2 = 1 -> PC chup + detect + ghi ket qua, roi xoa bit."""
        if self.plc is None or not self.chk_trigger.isChecked():
            return
        try:
            db, byte = self._plc_dia_chi()
            trigger = self.plc.read_bool(db=db, byte=byte, bit=2)
        except Exception as e:
            self.ghi_log("PLC", f"Lỗi đọc trigger: {e}", MAU_NG)
            self.ngat_plc()
            return
        if trigger and not self._trigger_truoc:     # canh len
            self.ghi_log("PLC", "Nhận TRIGGER từ PLC", MAU_PLC)
            try:
                self.plc.write_bool(db=db, byte=byte, bit=2, value=False)  # xoa trigger
            except Exception as e:
                self.ghi_log("PLC", f"Lỗi xóa bit trigger: {e}", MAU_NG)
            self.cho_gui_plc = True     # detect xong se tu gui ket qua
            self.chup_va_detect()
        self._trigger_truoc = trigger

    def gui_ket_qua_plc(self):
        """Ghi ket qua hien tai xuong PLC:
        DBX{b}.0 = PASS, DBX{b}.1 = FAIL, DBW{b+2} = so loai linh kien NG."""
        if self.ok_cuoi is None:
            self.ghi_log("PLC", "Chưa có kết quả để gửi", "#c07000")
            return
        if self.plc is None or not self.plc.connected:
            self.ghi_log("PLC", "Chưa kết nối PLC", MAU_NG)
            return
        so_ng = sum(1 for _, (_f, _e, ok) in self.rows_cuoi.items() if not ok)
        try:
            db, byte = self._plc_dia_chi()
            self.plc.send_result(self.ok_cuoi, so_ng, db=db, byte=byte,
                                 bit_pass=0, bit_fail=1, byte_count=byte + 2)
        except Exception as e:
            self.ghi_log("PLC", f"Lỗi ghi kết quả: {e}", MAU_NG)
            return
        self.lbl_plc_gui_cuoi.setText(datetime.now().strftime("%H:%M:%S"))
        self.ghi_log("PLC", f"Gửi kết quả: {'PASS' if self.ok_cuoi else 'FAIL'}"
                            f" (số loại NG = {so_ng}) - OK", MAU_PLC)

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self.timer_cam.stop()
        self.timer_plc.stop()
        self.worker.dung()
        self.worker.wait(2000)
        if self.cam is not None:
            try:
                self.cam.close()
            except Exception:
                pass
        if self.plc is not None:
            self.plc.disconnect()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = VisionSerialWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
