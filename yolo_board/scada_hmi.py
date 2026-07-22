#coding=utf-8
"""SCADA HMI cho day chuyen kiem tra PCB — PyQt5 + YOLO + PLC S7.

Giao dien kieu SCADA (nen toi): so do quy trinh ve DONG trang thai tung co cau,
day tile thong so, panel canh bao, va LIVE CAM giu nguyen nhu ban cu.

TAI SU DUNG cau truc cu: import thang PlcWorker / YoloWorker / ImageView / Camera
tu vision_plc_gui.py — khong viet lai logic bat tay PLC (DB1) hay YOLO. File nay
chi thay lop trinh bay.

Trang thai phan cung suy tu:
  - TRANG_THAI_MAY (S0..S8, S99) trong DB1  -> co cau nao dang bat theo ladder
  - byte ngo ra Q va ngo vao I doc them tu PLC (neu doc duoc) -> trang thai THAT
  (khi khong doc duoc / mo phong: suy tu TRANG_THAI_MAY)

Chay:
    .venv\\Scripts\\python.exe yolo_board\\scada_hmi.py
"""
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np
import cv2

# vision_plc_gui da lo thu tu import torch/PyQt5 (Windows), cung cap cac worker.
import vision_plc_gui as vpg
from vision_plc_gui import PlcWorker, YoloWorker, ImageView, dc, TEN_TRANG_THAI

from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QPolygonF, QPainterPath,
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QFrame, QLineEdit,
    QCheckBox, QComboBox, QDoubleSpinBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSizePolicy, QMessageBox, QScrollArea,
)

# ----- Bang mau (dark SCADA) -----
NEN = "#0e1b2a"          # nen sau nhat
PANEL = "#152636"        # nen panel
PANEL2 = "#1b3047"       # panel nhat hon
VIEN = "#26405c"
CHU = "#cdd8e3"
CHU_MO = "#7f95aa"
ACCENT = "#2b9be0"
XANH = "#22c55e"         # dang chay / OK
VANG = "#f5b400"         # cho / canh bao
DO = "#ef4444"           # loi / NG / E-Stop
XAM = "#3a4a5a"          # tat / khong hoat dong

# ----- Ban do bit ngo ra Q (theo PLC_LADDER.md muc 8-9) -----
Q_DEN_XANH, Q_DEN_VANG, Q_DEN_DO, Q_COI = 0, 1, 2, 3
Q_XYLANH1, Q_BANG_CHUYEN, Q_XYLANH2 = 4, 5, 6
# ----- Ban do bit ngo vao I (theo PLC_SETUP / ladder) -----
I_STOP, I_START, I_S2, I_S3, I_S1, I_ESTOP = 0, 1, 2, 3, 4, 5


def q_tu_trang_thai(s, estop=False):
    """Suy byte ngo ra Q tu so hieu trang thai may (dung khi khong doc duoc Q that
    hoac dang mo phong). Bam theo bang trang thai + FC3 trong PLC_LADDER.md."""
    q = 0
    if s in (1, 2, 3, 6, 7):
        q |= 1 << Q_BANG_CHUYEN
    if s == 1:
        q |= 1 << Q_XYLANH1
    if s == 8:
        q |= 1 << Q_XYLANH2
    if 1 <= s <= 6:
        q |= 1 << Q_DEN_XANH
    if s == 0:
        q |= 1 << Q_DEN_VANG
    if s >= 7 or estop:
        q |= 1 << Q_DEN_DO
        q |= 1 << Q_COI
    return q


def _bit(byte_val, bit):
    return bool((byte_val or 0) & (1 << bit))


# ======================================================================
# Cac widget nho
# ======================================================================
class Den(QWidget):
    """Den LED: cham tron mau + nhan + dia chi. set(on, mau)."""
    def __init__(self, nhan, dia_chi="", parent=None):
        super().__init__(parent)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(2, 2, 2, 2)
        lo.setSpacing(6)
        self.cham = QLabel()
        self.cham.setFixedSize(14, 14)
        self._dat_mau(XAM)
        lo.addWidget(self.cham)
        t = QLabel(nhan if not dia_chi else f"{nhan}  <span style='color:{CHU_MO}'>{dia_chi}</span>")
        t.setStyleSheet(f"color: {CHU}; font-size: 12px;")
        lo.addWidget(t, 1)

    def _dat_mau(self, mau):
        self.cham.setStyleSheet(
            f"background: {mau}; border-radius: 7px; border: 1px solid rgba(0,0,0,0.35);")

    def set(self, on, mau_on=XANH):
        self._dat_mau(mau_on if on else XAM)


class The(QFrame):
    """Tile thong so: gia tri lon + don vi + nhan + cham trang thai."""
    def __init__(self, nhan, don_vi="", parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: {PANEL2}; border: 1px solid {VIEN};"
            f" border-radius: 8px; }}")
        lo = QVBoxLayout(self)
        lo.setContentsMargins(12, 8, 12, 8)

        dau = QHBoxLayout()
        self.nhan = QLabel(nhan)
        self.nhan.setStyleSheet(f"color: {CHU_MO}; font-size: 11px; border: none;")
        dau.addWidget(self.nhan)
        dau.addStretch(1)
        self.cham = QLabel()
        self.cham.setFixedSize(10, 10)
        self.cham.setStyleSheet(f"background: {XAM}; border-radius: 5px;")
        dau.addWidget(self.cham)
        lo.addLayout(dau)

        self.gia_tri = QLabel("—")
        self.gia_tri.setStyleSheet(
            f"color: {CHU}; font-size: 26px; font-weight: bold; border: none;")
        lo.addWidget(self.gia_tri)

        self.don_vi = QLabel(don_vi)
        self.don_vi.setStyleSheet(f"color: {CHU_MO}; font-size: 11px; border: none;")
        lo.addWidget(self.don_vi)

    def dat(self, gia_tri, mau_cham=None, mau_gia_tri=None):
        self.gia_tri.setText(str(gia_tri))
        if mau_gia_tri:
            self.gia_tri.setStyleSheet(
                f"color: {mau_gia_tri}; font-size: 26px; font-weight: bold; border: none;")
        if mau_cham:
            self.cham.setStyleSheet(f"background: {mau_cham}; border-radius: 5px;")


class Donut(QWidget):
    """Vong tron PASS/FAIL."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.pas = 0
        self.fail = 0

    def dat(self, pas, fail):
        self.pas, self.fail = pas, fail
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        d = min(w, h) - 16
        x = (w - d) / 2
        y = (h - d) / 2
        rect = QRectF(x, y, d, d)
        tong = self.pas + self.fail
        p.setPen(QPen(QColor(XAM), 16))
        p.drawArc(rect, 0, 360 * 16)
        if tong > 0:
            goc_pass = int(360 * self.pas / tong)
            p.setPen(QPen(QColor(XANH), 16))
            p.drawArc(rect, 90 * 16, -goc_pass * 16)
            p.setPen(QPen(QColor(DO), 16))
            p.drawArc(rect, (90 - goc_pass) * 16, -(360 - goc_pass) * 16)
        p.setPen(QColor(CHU))
        p.setFont(QFont("Segoe UI", 15, QFont.Bold))
        yld = (100 * self.pas / tong) if tong else 0
        p.drawText(rect, Qt.AlignCenter, f"{yld:.0f}%")
        p.end()


# ======================================================================
# So do quy trinh — ve DONG theo trang thai phan cung
# ======================================================================
class SoDoQuyTrinh(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.q = 0                 # byte ngo ra
        self.i = 0                 # byte ngo vao
        self.state = 0
        self.pha = 0.0             # pha chay bang chuyen (animation)

    def cap_nhat(self, q, i, state):
        self.q, self.i, self.state = q or 0, i or 0, state
        self.update()

    # -- tien ich ve --
    def _hop(self, p, x, y, w, h, nhan, on, mau_on=XANH, phu=""):
        mau = QColor(mau_on if on else PANEL2)
        p.setBrush(QBrush(mau))
        p.setPen(QPen(QColor(mau_on if on else VIEN), 2))
        p.drawRoundedRect(QRectF(x, y, w, h), 6, 6)
        p.setPen(QColor("#ffffff" if on else CHU))
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        p.drawText(QRectF(x, y, w, h), Qt.AlignCenter, nhan)
        if phu:
            p.setPen(QColor(CHU_MO))
            p.setFont(QFont("Consolas", 8))
            p.drawText(QRectF(x, y + h, w, 14), Qt.AlignCenter, phu)

    def _cam_bien(self, p, x, y, nhan, on):
        mau = QColor(XANH if on else XAM)
        p.setBrush(QBrush(mau))
        p.setPen(QPen(mau.darker(150), 1))
        p.drawEllipse(QPointF(x, y), 8, 8)
        p.setPen(QColor(CHU_MO))
        p.setFont(QFont("Consolas", 8))
        p.drawText(QRectF(x - 20, y + 10, 40, 12), Qt.AlignCenter, nhan)

    def _mui_ten_xuong(self, p, x, y_top, y_bot, on):
        mau = QColor(VANG if on else XAM)
        p.setPen(QPen(mau, 3))
        p.drawLine(QPointF(x, y_top), QPointF(x, y_bot - 6))
        tam = QPolygonF([QPointF(x - 6, y_bot - 8), QPointF(x + 6, y_bot - 8),
                         QPointF(x, y_bot)])
        p.setBrush(QBrush(mau))
        p.setPen(Qt.NoPen)
        p.drawPolygon(tam)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), QColor(NEN))

        # he toa do logic 1000 x 360 -> scale
        sx = W / 1000.0
        sy = H / 360.0
        p.scale(sx, sy)

        bc_on = _bit(self.q, Q_BANG_CHUYEN)
        xl1 = _bit(self.q, Q_XYLANH1)
        xl2 = _bit(self.q, Q_XYLANH2)
        s = self.state

        belt_y = 210
        # --- bang chuyen (duong dam) ---
        p.setPen(QPen(QColor(ACCENT if bc_on else XAM), 10))
        p.drawLine(QPointF(150, belt_y), QPointF(880, belt_y))
        # con lan
        for rx in range(160, 881, 60):
            p.setBrush(QBrush(QColor("#0b1622")))
            p.setPen(QPen(QColor(VIEN), 1))
            p.drawEllipse(QPointF(rx, belt_y), 6, 6)
        # dau chay tren bang
        if bc_on:
            p.setBrush(QBrush(QColor(XANH)))
            p.setPen(Qt.NoPen)
            for k in range(6):
                dx = 160 + ((self.pha * 40 + k * 120) % 720)
                p.drawEllipse(QPointF(dx, belt_y), 4, 4)

        # --- o phoi (feeder) ---
        self._hop(p, 30, 150, 90, 110, "Ổ PHÔI", False, phu="")
        # --- xy lanh 1 (day phoi) ---
        self._hop(p, 150, 95, 70, 44, "XL ĐẨY", xl1, VANG, "Q0.4")
        self._mui_ten_xuong(p, 185, 139, belt_y - 12, xl1)

        # --- cam bien S1 ---
        self._cam_bien(p, 340, belt_y, "S1 I0.4", _bit(self.i, I_S1) or s == 2)

        # --- camera + S2 (vi tri chup) ---
        chup = (s == 4)
        self._hop(p, 450, 70, 100, 50, "CAMERA", chup, ACCENT, "chụp @ S2")
        p.setPen(QPen(QColor(ACCENT if chup else XAM), 2, Qt.DashLine))
        p.drawLine(QPointF(500, 120), QPointF(500, belt_y - 10))
        self._cam_bien(p, 500, belt_y, "S2 I0.2", _bit(self.i, I_S2) or chup)

        # --- cam bien S3 ---
        self._cam_bien(p, 660, belt_y, "S3 I0.3", _bit(self.i, I_S3) or s in (6, 7))

        # --- xy lanh 2 (loai bo) ---
        self._hop(p, 730, 95, 70, 44, "XL LOẠI", xl2, DO, "Q0.6")
        self._mui_ten_xuong(p, 765, 139, belt_y - 12, xl2)

        # --- ngo ra OK (cuoi bang) ---
        self._hop(p, 890, 185, 90, 50, "OK", (s == 6), XANH)
        # --- thung NG (duoi xy lanh 2) ---
        self._hop(p, 720, 275, 90, 55, "THÙNG NG", (s == 8), DO)
        p.setPen(QPen(QColor(DO if xl2 else XAM), 2))
        p.drawLine(QPointF(765, belt_y + 5), QPointF(765, 275))

        # --- thap den + coi (goc phai tren) ---
        base_x, base_y = 930, 40
        for k, (bit, mau) in enumerate(((Q_DEN_XANH, XANH), (Q_DEN_VANG, VANG),
                                        (Q_DEN_DO, DO))):
            on = _bit(self.q, bit)
            p.setBrush(QBrush(QColor(mau if on else XAM)))
            p.setPen(QPen(QColor(mau).darker(160), 1))
            p.drawEllipse(QPointF(base_x, base_y + k * 34), 13, 13)
        coi_on = _bit(self.q, Q_COI)
        p.setBrush(QBrush(QColor(VANG if coi_on else XAM)))
        p.setPen(QPen(QColor(VIEN), 1))
        p.drawRoundedRect(QRectF(base_x - 16, base_y + 3 * 34, 32, 20), 4, 4)
        p.setPen(QColor("#000" if coi_on else CHU_MO))
        p.setFont(QFont("Consolas", 7, QFont.Bold))
        p.drawText(QRectF(base_x - 16, base_y + 3 * 34, 32, 20), Qt.AlignCenter, "CÒI")

        # --- ten trang thai ---
        p.setPen(QColor(CHU_MO))
        p.setFont(QFont("Consolas", 9))
        p.drawText(QRectF(30, 20, 600, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   f"S{s} — {TEN_TRANG_THAI.get(s, '?')}")
        p.end()


# ======================================================================
# Cua so chinh SCADA
# ======================================================================
class ScadaHmiWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SCADA HMI — Dây chuyền kiểm tra PCB (YOLO + PLC S7)")
        self.resize(1360, 820)

        self.cam = None
        self.anh_test = None
        self.roi = None
        self.dang_xu_ly = False
        self.plc_da_ket_noi = False
        self.plc_mo_phong = False
        self.thu_muc_log = os.path.join(HERE, "log_ket_qua")

        self._dung_giao_dien()
        self._ap_style()

        # --- workers (tai su dung cau truc cu) ---
        self.yolo = YoloWorker(0.25, 640)
        self.yolo.ket_qua.connect(self._yolo_xong)
        self.yolo.bao_loi.connect(self._log)
        self.yolo.model_ok.connect(self._model_da_tai)
        self.yolo.start()

        self.plc = PlcWorker()
        self.plc.yeu_cau_chup.connect(self._plc_yeu_cau_chup)
        self.plc.trang_thai.connect(self._cap_nhat_trang_thai)
        self.plc.bao_loi.connect(self._log)
        self.plc.thong_bao.connect(self._log)
        self.plc.ket_noi_doi.connect(self._plc_ket_noi_doi)
        self.plc.start()

        # live cam
        self.timer_live = QTimer(self)
        self.timer_live.timeout.connect(self._live_tick)
        self.timer_live.start(50)
        # animation bang chuyen + dong ho
        self.timer_anim = QTimer(self)
        self.timer_anim.timeout.connect(self._anim_tick)
        self.timer_anim.start(80)

    # ------------------------------------------------------------------
    def _dung_giao_dien(self):
        trung_tam = QWidget()
        self.setCentralWidget(trung_tam)
        ngoai = QVBoxLayout(trung_tam)
        ngoai.setContentsMargins(0, 0, 0, 0)
        ngoai.setSpacing(0)

        ngoai.addWidget(self._thanh_tren())

        than = QHBoxLayout()
        than.setContentsMargins(8, 8, 8, 8)
        than.setSpacing(8)
        ngoai.addLayout(than, 1)

        than.addWidget(self._sidebar())
        than.addWidget(self._khu_trung_tam(), 5)
        than.addWidget(self._khu_phai(), 2)

        ngoai.addWidget(self._thanh_dieu_khien())

    def _thanh_tren(self):
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(50)
        lo = QHBoxLayout(bar)
        lo.setContentsMargins(16, 0, 16, 0)
        tieu_de = QLabel("SCADA <span style='color:%s'>HMI</span>" % ACCENT)
        tieu_de.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        lo.addWidget(tieu_de)
        lo.addStretch(1)

        self.tt_plc = self._chip("PLC", DO)
        self.tt_cam = self._chip("CAMERA", DO)
        self.tt_may = self._chip("MÁY", XAM)
        for c in (self.tt_plc, self.tt_cam, self.tt_may):
            lo.addWidget(c)
        self.lbl_gio = QLabel("")
        self.lbl_gio.setStyleSheet(f"color: {CHU_MO};")
        lo.addWidget(self.lbl_gio)
        return bar

    def _chip(self, nhan, mau):
        w = QLabel(f"  ● {nhan}  ")
        w.setStyleSheet(
            f"color: {CHU}; background: {PANEL}; border: 1px solid {VIEN};"
            f" border-radius: 10px; padding: 3px 6px;")
        w._nhan = nhan
        self._dat_chip(w, mau)
        return w

    def _dat_chip(self, w, mau):
        w.setText(f"  <span style='color:{mau}'>●</span> {w._nhan}  ")

    def _sidebar(self):
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(56)
        lo = QVBoxLayout(bar)
        lo.setContentsMargins(6, 10, 6, 10)
        lo.setSpacing(10)
        for ky_hieu, tip in (("≡", "Menu"), ("⌂", "Tổng quan"), ("📈", "Thống kê"),
                             ("⚙", "Cấu hình"), ("🔔", "Cảnh báo")):
            b = QPushButton(ky_hieu)
            b.setFixedSize(44, 40)
            b.setToolTip(tip)
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {CHU_MO};"
                f" border: none; font-size: 18px; border-radius: 8px; }}"
                f"QPushButton:hover {{ background: {PANEL2}; color: white; }}")
            lo.addWidget(b)
        lo.addStretch(1)
        return bar

    def _khu_trung_tam(self):
        khu = QFrame()
        lo = QVBoxLayout(khu)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(8)

        so_do_khung = QFrame()
        so_do_khung.setObjectName("panel")
        sdl = QVBoxLayout(so_do_khung)
        sdl.setContentsMargins(6, 6, 6, 6)
        self.so_do = SoDoQuyTrinh()
        sdl.addWidget(self.so_do)
        lo.addWidget(so_do_khung, 3)

        # day tile thong so
        hang_tile = QHBoxLayout()
        hang_tile.setSpacing(8)
        self.tile_tt = The("TRẠNG THÁI")
        self.tile_tong = The("TỔNG KIỂM", "PCB")
        self.tile_pass = The("PASS", "PCB")
        self.tile_fail = The("FAIL", "PCB")
        self.tile_yield = The("YIELD", "%")
        for t in (self.tile_tt, self.tile_tong, self.tile_pass, self.tile_fail,
                  self.tile_yield):
            hang_tile.addWidget(t)
        lo.addLayout(hang_tile, 1)

        # panel LED thiet bi (dam bao hien TAT CA co cau)
        thiet_bi = QFrame()
        thiet_bi.setObjectName("panel")
        tg = QGridLayout(thiet_bi)
        tg.setContentsMargins(10, 8, 10, 8)
        tg.addWidget(self._tieu_de_panel("THIẾT BỊ"), 0, 0, 1, 4)
        self.den = {}
        dsach = [
            ("bang_chuyen", "Băng chuyền", "Q0.5"), ("xylanh1", "Xy lanh đẩy", "Q0.4"),
            ("xylanh2", "Xy lanh loại", "Q0.6"), ("den_xanh", "Đèn xanh", "Q0.0"),
            ("den_vang", "Đèn vàng", "Q0.1"), ("den_do", "Đèn đỏ", "Q0.2"),
            ("coi", "Còi", "Q0.3"), ("s1", "Cảm biến 1", "I0.4"),
            ("s2", "Cảm biến 2", "I0.2"), ("s3", "Cảm biến 3", "I0.3"),
            ("start", "Nút START", "I0.1"), ("estop", "E-STOP", "I0.5"),
        ]
        for k, (key, nhan, dc_addr) in enumerate(dsach):
            d = Den(nhan, dc_addr)
            self.den[key] = d
            tg.addWidget(d, 1 + k // 4, k % 4)
        lo.addWidget(thiet_bi, 1)
        return khu

    def _khu_phai(self):
        khu = QScrollArea()
        khu.setWidgetResizable(True)
        khu.setFrameShape(QFrame.NoFrame)
        khu.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        noi = QWidget()
        lo = QVBoxLayout(noi)
        lo.setContentsMargins(0, 0, 0, 0)
        lo.setSpacing(8)

        # --- live cam ---
        cam_khung = QFrame()
        cam_khung.setObjectName("panel")
        cl = QVBoxLayout(cam_khung)
        cl.setContentsMargins(8, 6, 8, 8)
        cl.addWidget(self._tieu_de_panel("CAMERA TRỰC TIẾP"))
        self.anh = ImageView()
        self.anh.setMinimumSize(240, 190)      # ghi de min 420 cua ImageView goc
        cl.addWidget(self.anh, 1)
        self.lbl_kq = QLabel("—")
        self.lbl_kq.setAlignment(Qt.AlignCenter)
        self.lbl_kq.setFixedHeight(40)
        self.lbl_kq.setStyleSheet(
            f"color: {CHU}; background: {PANEL2}; border: 1px solid {VIEN};"
            f" border-radius: 6px; font-size: 16px; font-weight: bold;")
        cl.addWidget(self.lbl_kq)
        lo.addWidget(cam_khung, 3)

        # --- donut PASS/FAIL ---
        d_khung = QFrame()
        d_khung.setObjectName("panel")
        dl = QVBoxLayout(d_khung)
        dl.setContentsMargins(8, 6, 8, 8)
        dl.addWidget(self._tieu_de_panel("TỈ LỆ ĐẠT"))
        self.donut = Donut()
        dl.addWidget(self.donut)
        self.lbl_donut = QLabel("PASS 0   ·   FAIL 0")
        self.lbl_donut.setAlignment(Qt.AlignCenter)
        self.lbl_donut.setStyleSheet(f"color: {CHU_MO};")
        dl.addWidget(self.lbl_donut)
        lo.addWidget(d_khung, 2)

        # --- canh bao ---
        a_khung = QFrame()
        a_khung.setObjectName("panel")
        al = QVBoxLayout(a_khung)
        al.setContentsMargins(8, 6, 8, 8)
        al.addWidget(self._tieu_de_panel("CẢNH BÁO"))
        self.alarm = {}
        for key, nhan in (("estop", "Dừng khẩn cấp (E-STOP)"),
                          ("may_loi", "Máy lỗi / kẹt phôi"),
                          ("mat_plc", "Mất kết nối PLC"),
                          ("mat_cam", "Chưa có camera")):
            row = QLabel("  ⚠  " + nhan)
            row.setStyleSheet(
                f"color: {CHU_MO}; background: {PANEL2}; border: 1px solid {VIEN};"
                f" border-radius: 6px; padding: 6px;")
            self.alarm[key] = row
            al.addWidget(row)
        al.addStretch(1)
        lo.addWidget(a_khung, 2)

        khu.setWidget(noi)
        khu.setFixedWidth(300)
        return khu

    def _thanh_dieu_khien(self):
        bar = QFrame()
        bar.setObjectName("controlbar")
        lo = QHBoxLayout(bar)
        lo.setContentsMargins(10, 6, 10, 6)
        lo.setSpacing(6)

        lo.addWidget(QLabel("PLC:"))
        self.txt_ip = QLineEdit("192.168.0.1")
        self.txt_ip.setFixedWidth(110)
        lo.addWidget(self.txt_ip)
        self.chk_mo_phong = QCheckBox("Mô phỏng")
        self.chk_mo_phong.setChecked(not vpg.HAS_SNAP7)
        lo.addWidget(self.chk_mo_phong)
        self.btn_plc = QPushButton("Kết nối PLC")
        self.btn_plc.clicked.connect(self._plc_toggle)
        lo.addWidget(self.btn_plc)

        self.btn_cam = QPushButton("Mở camera")
        self.btn_cam.clicked.connect(self._cam_toggle)
        lo.addWidget(self.btn_cam)
        self.btn_gia_lap = QPushButton("Giả lập TRIGGER")
        self.btn_gia_lap.clicked.connect(lambda: self.plc.kich_trigger_mo_phong())
        lo.addWidget(self.btn_gia_lap)

        lo.addWidget(self._vach())
        self.chk_dk = QCheckBox("Cho phép ĐK")
        self.chk_dk.setToolTip("⚠ Ghi thẳng ngõ ra — kích thiết bị thật")
        self.chk_dk.toggled.connect(self._doi_cho_phep)
        lo.addWidget(self.chk_dk)

        self._nut_dk = []
        b_run = QPushButton("▶ Băng chuyền")
        b_run.clicked.connect(lambda: self.plc.dat_ngo_ra(0, Q_BANG_CHUYEN, True))
        b_stop = QPushButton("■ Dừng BC")
        b_stop.clicked.connect(lambda: self.plc.dat_ngo_ra(0, Q_BANG_CHUYEN, False))
        b_xl1 = QPushButton("XL đẩy")
        b_xl1.clicked.connect(lambda: self._xung(Q_XYLANH1))
        b_xl2 = QPushButton("XL loại")
        b_xl2.clicked.connect(lambda: self._xung(Q_XYLANH2))
        b_off = QPushButton("TẮT TẤT CẢ")
        b_off.setObjectName("nguyhiem")
        b_off.clicked.connect(lambda: self.plc.tat_het_ngo_ra(8))
        for b in (b_run, b_stop, b_xl1, b_xl2):
            lo.addWidget(b)
            self._nut_dk.append(b)
        lo.addWidget(b_off)
        self.btn_tat_het = b_off
        lo.addStretch(1)
        self._cap_nhat_enable_dk()
        return bar

    def _vach(self):
        v = QFrame()
        v.setFrameShape(QFrame.VLine)
        v.setStyleSheet(f"color: {VIEN};")
        return v

    def _tieu_de_panel(self, td):
        l = QLabel(td)
        l.setStyleSheet(
            f"color: {CHU_MO}; font-size: 11px; font-weight: bold; border: none;"
            f" letter-spacing: 1px;")
        return l

    def _ap_style(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {NEN}; color: {CHU};
                font-family: 'Segoe UI'; font-size: 12px; }}
            QFrame#topbar {{ background: {PANEL}; border-bottom: 1px solid {VIEN}; }}
            QFrame#sidebar {{ background: {PANEL}; border-right: 1px solid {VIEN}; }}
            QFrame#controlbar {{ background: {PANEL}; border-top: 1px solid {VIEN}; }}
            QFrame#panel {{ background: {PANEL}; border: 1px solid {VIEN};
                border-radius: 8px; }}
            QLabel {{ color: {CHU}; }}
            QLineEdit, QComboBox, QDoubleSpinBox {{ background: {PANEL2};
                border: 1px solid {VIEN}; border-radius: 4px; padding: 3px;
                color: {CHU}; }}
            QCheckBox {{ color: {CHU}; }}
            QPushButton {{ background: {PANEL2}; border: 1px solid {VIEN};
                border-radius: 6px; padding: 5px 10px; color: {CHU}; }}
            QPushButton:hover {{ background: {ACCENT}; color: white; }}
            QPushButton:disabled {{ color: {CHU_MO}; background: {PANEL};
                border-color: {PANEL}; }}
            QPushButton#nguyhiem {{ background: {DO}; color: white;
                font-weight: bold; border: none; }}
            QScrollArea {{ border: none; }}
        """)

    # ------------------------------------------------------------------
    # Cap nhat trang thai (tin hieu tu PlcWorker) — tim cua HMI
    # ------------------------------------------------------------------
    def _cap_nhat_trang_thai(self, tt):
        s = tt["trang_thai_may"]
        q = tt.get("ngo_ra")
        i = tt.get("ngo_vao")
        if q is None:                          # khong doc duoc Q that -> suy tu state
            q = q_tu_trang_thai(s, tt["estop"])
        if i is None:
            i = 0
        self.so_do.cap_nhat(q, i, s)

        # tile
        mau_tt = DO if (tt["may_loi"] or tt["estop"] or s == 99) else (
            XANH if tt["may_chay"] else CHU_MO)
        self.tile_tt.dat(f"S{s}", mau_cham=mau_tt, mau_gia_tri=mau_tt)
        self.tile_tt.nhan.setText(TEN_TRANG_THAI.get(s, "?").split("—")[0].strip()[:18])
        tong, pas, fail = tt["dem_tong"], tt["dem_pass"], tt["dem_fail"]
        self.tile_tong.dat(tong, mau_cham=ACCENT)
        self.tile_pass.dat(pas, mau_cham=XANH, mau_gia_tri=XANH)
        self.tile_fail.dat(fail, mau_cham=DO, mau_gia_tri=DO)
        self.tile_yield.dat(f"{(100*pas/tong):.0f}" if tong else "—",
                            mau_cham=XANH if fail == 0 else VANG)

        # LED thiet bi
        self.den["bang_chuyen"].set(_bit(q, Q_BANG_CHUYEN), XANH)
        self.den["xylanh1"].set(_bit(q, Q_XYLANH1), VANG)
        self.den["xylanh2"].set(_bit(q, Q_XYLANH2), DO)
        self.den["den_xanh"].set(_bit(q, Q_DEN_XANH), XANH)
        self.den["den_vang"].set(_bit(q, Q_DEN_VANG), VANG)
        self.den["den_do"].set(_bit(q, Q_DEN_DO), DO)
        self.den["coi"].set(_bit(q, Q_COI), VANG)
        self.den["s1"].set(_bit(i, I_S1), XANH)
        self.den["s2"].set(_bit(i, I_S2), XANH)
        self.den["s3"].set(_bit(i, I_S3), XANH)
        self.den["start"].set(_bit(i, I_START), XANH)
        self.den["estop"].set(tt["estop"], DO)

        # donut
        self.donut.dat(pas, fail)
        self.lbl_donut.setText(f"PASS {pas}   ·   FAIL {fail}")

        # chip may
        self._dat_chip(self.tt_may, DO if (tt["may_loi"] or tt["estop"]) else (
            XANH if tt["may_chay"] else XAM))

        # canh bao
        self._dat_alarm("estop", tt["estop"])
        self._dat_alarm("may_loi", tt["may_loi"] or s == 99)

    def _dat_alarm(self, key, active):
        row = self.alarm[key]
        nhan = row.text().strip()[3:].strip() if row.text().strip().startswith("⚠") else row.text()
        # giu nguyen text, chi doi mau
        if active:
            row.setStyleSheet(
                f"color: white; background: {DO}; border: 1px solid {DO};"
                f" border-radius: 6px; padding: 6px; font-weight: bold;")
        else:
            row.setStyleSheet(
                f"color: {CHU_MO}; background: {PANEL2}; border: 1px solid {VIEN};"
                f" border-radius: 6px; padding: 6px;")

    def _anim_tick(self):
        if _bit(self.so_do.q, Q_BANG_CHUYEN):
            self.so_do.pha += 1
            self.so_do.update()
        self.lbl_gio.setText(datetime.now().strftime("%H:%M:%S"))

    # ------------------------------------------------------------------
    # PLC ket noi
    # ------------------------------------------------------------------
    def _plc_toggle(self):
        if self.plc_da_ket_noi:
            self.plc.yeu_cau_ngat()
            return
        mo_phong = self.chk_mo_phong.isChecked()
        if not mo_phong and not vpg.HAS_SNAP7:
            QMessageBox.critical(self, "Thiếu thư viện", "Chưa cài python-snap7.")
            return
        self.plc.yeu_cau_ket_noi(self.txt_ip.text().strip(), 0, 1, mo_phong)

    def _plc_ket_noi_doi(self, ok):
        self.plc_da_ket_noi = ok
        self.plc_mo_phong = self.plc.mo_phong
        self.btn_plc.setText("Ngắt PLC" if ok else "Kết nối PLC")
        self.chk_mo_phong.setEnabled(not ok)
        self._dat_chip(self.tt_plc, XANH if ok else DO)
        self._dat_alarm("mat_plc", not ok)
        if ok:
            self._log("Kết nối PLC thành công" + (" (mô phỏng)" if self.plc.mo_phong else ""))
        self._cap_nhat_enable_dk()

    def _model_da_tai(self):
        self.plc.dat_san_sang(True)
        self._log("Model YOLO đã sẵn sàng")

    # ------------------------------------------------------------------
    # Camera + chup + YOLO  (giu nguyen luong cu)
    # ------------------------------------------------------------------
    def _cam_toggle(self):
        if self.cam is not None:
            try:
                self.cam.close()
            except Exception:
                pass
            self.cam = None
            self.btn_cam.setText("Mở camera")
            self._dat_chip(self.tt_cam, DO)
            self._dat_alarm("mat_cam", True)
            return
        if not vpg.HAS_CAM:
            QMessageBox.warning(self, "Không có camera",
                                "Không nạp được camera_mv / mvsdk. Dùng mô phỏng.")
            return
        try:
            self.cam = vpg.Camera()
            ten = self.cam.open()
            self.btn_cam.setText("Đóng camera")
            self._dat_chip(self.tt_cam, XANH)
            self._dat_alarm("mat_cam", False)
            self._log(f"Mở camera: {ten}")
        except Exception as e:
            self.cam = None
            QMessageBox.critical(self, "Lỗi camera", str(e))

    def _lay_anh(self, im_lang=False):
        if self.cam is not None:
            try:
                _, rgb = self.cam.grab()
                return np.ascontiguousarray(rgb[:, :, ::-1])
            except Exception as e:
                if not im_lang:
                    self._log(f"Lỗi chụp ảnh: {e}")
                return None
        return self.anh_test

    def _live_tick(self):
        if self.dang_xu_ly or self.cam is None:
            return
        bgr = self._lay_anh(im_lang=True)
        if bgr is not None:
            self.anh.hien_thi(bgr)

    def _plc_yeu_cau_chup(self):
        if self.dang_xu_ly:
            return
        self.dang_xu_ly = True
        self.lbl_kq.setText("ĐANG XỬ LÝ…")
        self.lbl_kq.setStyleSheet(
            f"color: {VANG}; background: {PANEL2}; border: 1px solid {VANG};"
            f" border-radius: 6px; font-size: 16px; font-weight: bold;")
        QTimer.singleShot(300, self._chup_that)

    def _chup_that(self):
        bgr = None
        if self.cam is not None:
            for _ in range(2):                 # xa bo dem
                self._lay_anh(im_lang=True)
            tot, net = None, -1.0
            for _ in range(3):                 # chon frame net nhat
                f = self._lay_anh(im_lang=True)
                if f is None:
                    continue
                g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) if f.ndim == 3 else f
                v = cv2.Laplacian(g, cv2.CV_32F).var()
                if v > net:
                    tot, net = f, v
            bgr = tot
        else:
            bgr = self.anh_test
        if bgr is None:
            self._log("TRIGGER nhưng chưa có nguồn ảnh")
            self.dang_xu_ly = False
            self.lbl_kq.setText("—")
            return
        self.yolo.dat_viec(bgr, self.roi)

    def _yolo_xong(self, bgr, dets, rows, ok_all, ms):
        self.anh.hien_thi(dc.draw(bgr, dets))
        so_loi = sum(1 for _, (_f, _e, ok) in rows.items() if not ok)
        self.lbl_kq.setText(f"{'PASS' if ok_all else 'FAIL'}   ·   {ms:.0f} ms")
        self.lbl_kq.setStyleSheet(
            f"color: white; background: {XANH if ok_all else DO};"
            f" border: none; border-radius: 6px; font-size: 16px; font-weight: bold;")
        self.plc.dat_ket_qua(ok_all, so_loi, 0 if ok_all else 1)
        self._log(f"Kết quả: {'PASS' if ok_all else 'FAIL'} ({so_loi} loại lỗi, {ms:.0f} ms)")
        self.dang_xu_ly = False

    # ------------------------------------------------------------------
    # Dieu khien thu cong
    # ------------------------------------------------------------------
    def _cap_nhat_enable_dk(self):
        cho = self.chk_dk.isChecked() and self.plc_da_ket_noi
        for b in self._nut_dk:
            b.setEnabled(cho)
        self.btn_tat_het.setEnabled(self.plc_da_ket_noi)

    def _doi_cho_phep(self, on):
        if on and self.plc_da_ket_noi and not self.plc_mo_phong:
            if QMessageBox.warning(
                    self, "Cảnh báo an toàn",
                    "Điều khiển thủ công sẽ GHI THẲNG ngõ ra và KÍCH THIẾT BỊ THẬT.\n"
                    "Đảm bảo không có người trong vùng máy. Tiếp tục?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                self.chk_dk.setChecked(False)
                return
        self._cap_nhat_enable_dk()

    def _xung(self, bit, giay=1.0):
        self.plc.dat_ngo_ra(0, bit, True)
        QTimer.singleShot(int(giay * 1000), lambda: self.plc.dat_ngo_ra(0, bit, False))

    # ------------------------------------------------------------------
    def _log(self, s):
        print(f"[{datetime.now():%H:%M:%S}] {s}")

    def closeEvent(self, e):
        self.timer_live.stop()
        self.timer_anim.stop()
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
    win = ScadaHmiWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
