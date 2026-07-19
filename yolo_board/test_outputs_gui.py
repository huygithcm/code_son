#coding=utf-8
"""GUI test/map ngo ra (Q) cua PLC S7 - PyQt5.

!!! CANH BAO AN TOAN !!!
Chuong trinh nay GHI truc tiep xuong vung Q -> KICH THAT thiet bi dang dau noi
(relay, van khi nen, xy lanh, dong co, den...). Truoc khi bat che do ghi:
  - Bao dam KHONG co nguoi dang thao tac trong vung may.
  - Nen ngat tai/khi nen neu chi muon nghe tieng relay de map dia chi.

Chay:
    .venv\\Scripts\\python.exe yolo_board\\test_outputs_gui.py

Chuc nang:
  - Luoi nut Q0.0 .. Q3.7, bam de XUNG (bat roi tu tat) hoac GIU ON.
  - O ghi chu ben canh moi ngo -> go ten thiet bi de MAP lai ngo ra.
  - Luu / mo bang map ra file JSON, xuat CSV.
  - Nut TAT TOAN BO (dung khan) va tu tat het khi thoat.
  - Che do DRY-RUN de tap thao tac ma khong ghi gi xuong PLC.

LUU Y khi CPU o RUN: neu chuong trinh PLC cung ghi vao ngo Q do, no se ghi de
sau moi vong quet -> ngo ra co the nhap nhay. Khi do can chuyen CPU sang STOP
hoac tam khoa doan chuong trinh dieu khien ngo ra trong TIA Portal.
"""
import csv
import json
import os
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

try:
    import snap7
    from snap7.type import Area
    HAS_SNAP7 = True
except ImportError:
    HAS_SNAP7 = False

MAU_OK = "#1a7f1a"
MAU_NG = "#c00000"
MAU_ON = "#e08000"

SO_BYTE = 4                 # so byte Q hien thi (Q0..Q3 = 32 ngo ra)
FILE_MAP_MAC_DINH = os.path.join(os.path.dirname(__file__), "output_map.json")


# ----------------------------------------------------------------------
# Lop giao tiep PLC (tach rieng de de test / de thay the)
# ----------------------------------------------------------------------
class PlcOut:
    def __init__(self):
        self.client = None
        self.dry_run = False

    @property
    def connected(self):
        if self.dry_run:
            return True
        try:
            return self.client is not None and self.client.get_connected()
        except Exception:
            return False

    def connect(self, ip, rack=0, slot=1, dry_run=False):
        self.dry_run = dry_run
        if dry_run:
            self.client = None
            return
        self.client = snap7.client.Client()
        self.client.connect(ip, rack, slot)
        if not self.client.get_connected():
            raise ConnectionError(f"Khong ket noi duoc PLC {ip}")

    def disconnect(self):
        if self.client is not None:
            try:
                self.client.disconnect()
            except Exception:
                pass
        self.client = None
        self.dry_run = False

    def read_byte(self, byte):
        if self.dry_run:
            return 0
        return self.client.read_area(Area.PA, 0, byte, 1)[0]

    def write_bit(self, byte, bit, value):
        """Doc-sua-ghi de khong dap cac bit khac trong cung byte."""
        if self.dry_run:
            return
        data = self.client.read_area(Area.PA, 0, byte, 1)
        snap7.util.set_bool(data, 0, bit, bool(value))
        self.client.write_area(Area.PA, 0, byte, data)

    def all_off(self, nbytes=SO_BYTE):
        if self.dry_run:
            return
        for b in range(nbytes):
            try:
                self.client.write_area(Area.PA, 0, b, bytearray([0]))
            except Exception:
                pass


# ----------------------------------------------------------------------
# Cua so chinh
# ----------------------------------------------------------------------
class OutputTesterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test & Map ngo ra PLC S7")
        self.plc = PlcOut()
        self.trang_thai = {}        # (byte, bit) -> bool, trang thai GIU do nguoi dung bat
        self.o_ghi_chu = {}         # (byte, bit) -> QLineEdit
        self.nut = {}               # (byte, bit) -> QPushButton
        self.den = {}               # (byte, bit) -> QLabel (den bao doc tu PLC)

        self._dung_giao_dien()
        self._nap_map(FILE_MAP_MAC_DINH, im_lang=True)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._doc_trang_thai)
        self.timer.start(300)

    # ------------------------------------------------------------------
    def _dung_giao_dien(self):
        trung_tam = QWidget()
        self.setCentralWidget(trung_tam)
        layout = QVBoxLayout(trung_tam)

        # --- Canh bao ---
        canh_bao = QLabel(
            "  CANH BAO: Thao tac o day KICH THIET BI THAT. "
            "Bao dam khong co nguoi trong vung may truoc khi bat che do ghi."
        )
        canh_bao.setStyleSheet(
            f"background: #fff3cd; color: {MAU_NG}; border: 1px solid {MAU_NG};"
            "padding: 6px; font-weight: bold;"
        )
        layout.addWidget(canh_bao)

        # --- Ket noi ---
        grp_kn = QGroupBox("Ket noi PLC")
        h = QHBoxLayout(grp_kn)
        h.addWidget(QLabel("IP:"))
        self.txt_ip = QLineEdit("192.168.0.1")
        self.txt_ip.setFixedWidth(120)
        h.addWidget(self.txt_ip)

        h.addWidget(QLabel("Rack:"))
        self.sp_rack = QSpinBox()
        self.sp_rack.setRange(0, 7)
        h.addWidget(self.sp_rack)

        h.addWidget(QLabel("Slot:"))
        self.sp_slot = QSpinBox()
        self.sp_slot.setRange(0, 31)
        self.sp_slot.setValue(1)
        h.addWidget(self.sp_slot)

        self.chk_dry = QCheckBox("DRY-RUN (khong ghi that)")
        self.chk_dry.setChecked(True)
        self.chk_dry.setToolTip("Bat de tap thao tac ma khong ghi gi xuong PLC")
        h.addWidget(self.chk_dry)

        self.btn_ket_noi = QPushButton("Ket noi")
        self.btn_ket_noi.setStyleSheet("QPushButton { padding: 5px; font-weight: bold; }")
        self.btn_ket_noi.clicked.connect(self._ket_noi)
        h.addWidget(self.btn_ket_noi)

        self.btn_ngat = QPushButton("Ngat")
        self.btn_ngat.setStyleSheet("QPushButton { padding: 5px; font-weight: bold; }")
        self.btn_ngat.clicked.connect(self._ngat)
        self.btn_ngat.setEnabled(False)
        h.addWidget(self.btn_ngat)

        self.lbl_tt = QLabel("Chua ket noi")
        self.lbl_tt.setStyleSheet(f"color: {MAU_NG}; font-weight: bold;")
        h.addWidget(self.lbl_tt)
        h.addStretch()
        layout.addWidget(grp_kn)

        # --- Che do thao tac ---
        grp_cd = QGroupBox("Che do bam nut")
        h2 = QHBoxLayout(grp_cd)
        self.cbo_che_do = QComboBox()
        self.cbo_che_do.addItems(["Xung (bat roi tu tat)", "Giu (bat/tat)"])
        self.cbo_che_do.setToolTip("Che do Xung an toan hon khi map ngo ra")
        h2.addWidget(self.cbo_che_do)

        h2.addWidget(QLabel("Thoi gian xung (ms):"))
        self.sp_xung = QSpinBox()
        self.sp_xung.setRange(50, 10000)
        self.sp_xung.setSingleStep(50)
        self.sp_xung.setValue(1000)
        h2.addWidget(self.sp_xung)
        h2.addStretch()

        btn_tat_het = QPushButton("TAT TOAN BO (dung khan)")
        btn_tat_het.setStyleSheet(
            f"QPushButton {{ padding: 8px; font-weight: bold; "
            f"background: {MAU_NG}; color: white; }}"
        )
        btn_tat_het.clicked.connect(self._tat_toan_bo)
        h2.addWidget(btn_tat_het)
        layout.addWidget(grp_cd)

        # --- Luoi ngo ra ---
        grp_q = QGroupBox(f"Ngo ra Q0.0 .. Q{SO_BYTE - 1}.7  (go ten thiet bi vao o ben phai de map)")
        luoi = QGridLayout(grp_q)
        luoi.addWidget(QLabel("<b>Dia chi</b>"), 0, 0)
        luoi.addWidget(QLabel("<b>Bam</b>"), 0, 1)
        luoi.addWidget(QLabel("<b>PLC</b>"), 0, 2)
        luoi.addWidget(QLabel("<b>Ten thiet bi / ghi chu</b>"), 0, 3)
        luoi.addWidget(QLabel("<b>Dia chi</b>"), 0, 5)
        luoi.addWidget(QLabel("<b>Bam</b>"), 0, 6)
        luoi.addWidget(QLabel("<b>PLC</b>"), 0, 7)
        luoi.addWidget(QLabel("<b>Ten thiet bi / ghi chu</b>"), 0, 8)

        font_dc = QFont("Consolas", 10)
        font_dc.setBold(True)
        tong = SO_BYTE * 8
        nua = tong // 2
        for idx in range(tong):
            byte, bit = divmod(idx, 8)
            # chia 2 cot cho gon
            if idx < nua:
                hang, cot0 = idx + 1, 0
            else:
                hang, cot0 = idx - nua + 1, 5

            lbl = QLabel(f"Q{byte}.{bit}")
            lbl.setFont(font_dc)
            luoi.addWidget(lbl, hang, cot0)

            nut = QPushButton("OFF")
            nut.setFixedWidth(64)
            nut.clicked.connect(
                lambda _, b=byte, i=bit: self._bam_ngo_ra(b, i)
            )
            self.nut[(byte, bit)] = nut
            luoi.addWidget(nut, hang, cot0 + 1)

            den = QLabel("  ")
            den.setFixedWidth(18)
            den.setAlignment(Qt.AlignCenter)
            den.setStyleSheet("background: #ccc; border: 1px solid #888;")
            den.setToolTip("Trang thai doc nguoc tu PLC")
            self.den[(byte, bit)] = den
            luoi.addWidget(den, hang, cot0 + 2)

            o = QLineEdit()
            o.setPlaceholderText("vd: Van day phoi")
            o.setMinimumWidth(180)
            self.o_ghi_chu[(byte, bit)] = o
            luoi.addWidget(o, hang, cot0 + 3)

            self.trang_thai[(byte, bit)] = False

        layout.addWidget(grp_q)

        # --- Luu / xuat ---
        h3 = QHBoxLayout()
        for ten, ham in (
            ("Luu bang map", self._luu_map),
            ("Mo bang map", self._mo_map),
            ("Xuat CSV", self._xuat_csv),
        ):
            b = QPushButton(ten)
            b.setStyleSheet("QPushButton { padding: 6px; font-weight: bold; }")
            b.clicked.connect(ham)
            h3.addWidget(b)
        h3.addStretch()
        b_thoat = QPushButton("Thoat")
        b_thoat.setStyleSheet("QPushButton { padding: 6px; font-weight: bold; }")
        b_thoat.clicked.connect(self.close)
        h3.addWidget(b_thoat)
        layout.addLayout(h3)

        self.statusBar().showMessage("San sang. Bat DRY-RUN de tap thao tac truoc.")

    # ------------------------------------------------------------------
    # Ket noi
    # ------------------------------------------------------------------
    def _ket_noi(self):
        dry = self.chk_dry.isChecked()
        if not dry:
            if not HAS_SNAP7:
                QMessageBox.critical(self, "Thieu thu vien",
                                     "Chua cai python-snap7.")
                return
            tra_loi = QMessageBox.warning(
                self, "Xac nhan che do GHI THAT",
                "Ban sap ket noi o che do GHI THAT xuong PLC.\n\n"
                "Cac thao tac sau do se KICH THIET BI THAT dang dau noi.\n\n"
                "Da bao dam KHONG co nguoi trong vung may chua?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if tra_loi != QMessageBox.Yes:
                return
        try:
            self.plc.connect(self.txt_ip.text().strip(),
                             self.sp_rack.value(), self.sp_slot.value(), dry)
        except Exception as e:
            QMessageBox.critical(self, "Loi ket noi", str(e))
            return

        self.btn_ket_noi.setEnabled(False)
        self.btn_ngat.setEnabled(True)
        self.chk_dry.setEnabled(False)
        if dry:
            self.lbl_tt.setText("DRY-RUN (khong ghi that)")
            self.lbl_tt.setStyleSheet(f"color: {MAU_ON}; font-weight: bold;")
            self.statusBar().showMessage("Che do DRY-RUN - khong co lenh nao xuong PLC.")
        else:
            self.lbl_tt.setText("DA KET NOI - GHI THAT")
            self.lbl_tt.setStyleSheet(f"color: {MAU_OK}; font-weight: bold;")
            self.statusBar().showMessage(f"Da ket noi {self.txt_ip.text().strip()}")

    def _ngat(self):
        self._tat_toan_bo(hoi=False)
        self.plc.disconnect()
        self.btn_ket_noi.setEnabled(True)
        self.btn_ngat.setEnabled(False)
        self.chk_dry.setEnabled(True)
        self.lbl_tt.setText("Chua ket noi")
        self.lbl_tt.setStyleSheet(f"color: {MAU_NG}; font-weight: bold;")
        self.statusBar().showMessage("Da ngat ket noi.")

    # ------------------------------------------------------------------
    # Thao tac ngo ra
    # ------------------------------------------------------------------
    def _bam_ngo_ra(self, byte, bit):
        if not self.plc.connected:
            QMessageBox.information(self, "Chua ket noi", "Hay ket noi PLC truoc.")
            return
        try:
            if self.cbo_che_do.currentIndex() == 0:      # xung
                self.plc.write_bit(byte, bit, True)
                self._to_nut(byte, bit, True)
                self.statusBar().showMessage(f"Xung Q{byte}.{bit}")
                QTimer.singleShot(self.sp_xung.value(),
                                  lambda: self._tat_sau_xung(byte, bit))
            else:                                        # giu
                moi = not self.trang_thai[(byte, bit)]
                self.plc.write_bit(byte, bit, moi)
                self.trang_thai[(byte, bit)] = moi
                self._to_nut(byte, bit, moi)
                self.statusBar().showMessage(
                    f"Q{byte}.{bit} = {'ON' if moi else 'OFF'}")
        except Exception as e:
            QMessageBox.critical(self, "Loi ghi PLC", str(e))

    def _tat_sau_xung(self, byte, bit):
        try:
            self.plc.write_bit(byte, bit, False)
        except Exception:
            pass
        self.trang_thai[(byte, bit)] = False
        self._to_nut(byte, bit, False)

    def _to_nut(self, byte, bit, on):
        nut = self.nut[(byte, bit)]
        nut.setText("ON" if on else "OFF")
        if on:
            nut.setStyleSheet(
                f"QPushButton {{ background: {MAU_ON}; color: white; font-weight: bold; }}")
        else:
            nut.setStyleSheet("")

    def _tat_toan_bo(self, hoi=True):
        if not self.plc.connected:
            return
        try:
            self.plc.all_off(SO_BYTE)
        except Exception as e:
            QMessageBox.critical(self, "Loi", str(e))
            return
        for khoa in self.trang_thai:
            self.trang_thai[khoa] = False
            self._to_nut(khoa[0], khoa[1], False)
        if hoi:
            self.statusBar().showMessage("Da tat toan bo ngo ra.")

    # ------------------------------------------------------------------
    # Doc nguoc trang thai tu PLC
    # ------------------------------------------------------------------
    def _doc_trang_thai(self):
        if not self.plc.connected:
            return
        for byte in range(SO_BYTE):
            try:
                v = self.plc.read_byte(byte)
            except Exception:
                continue
            for bit in range(8):
                on = bool(v & (1 << bit))
                mau = MAU_OK if on else "#ccc"
                self.den[(byte, bit)].setStyleSheet(
                    f"background: {mau}; border: 1px solid #888;")

    # ------------------------------------------------------------------
    # Luu / mo / xuat bang map
    # ------------------------------------------------------------------
    def _thu_bang_map(self):
        return {
            f"Q{b}.{i}": o.text().strip()
            for (b, i), o in sorted(self.o_ghi_chu.items())
            if o.text().strip()
        }

    def _luu_map(self):
        duong_dan, _ = QFileDialog.getSaveFileName(
            self, "Luu bang map ngo ra", FILE_MAP_MAC_DINH, "JSON (*.json)")
        if not duong_dan:
            return
        try:
            with open(duong_dan, "w", encoding="utf-8") as f:
                json.dump(self._thu_bang_map(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            QMessageBox.critical(self, "Loi luu file", str(e))
            return
        self.statusBar().showMessage(f"Da luu {duong_dan}")

    def _mo_map(self):
        duong_dan, _ = QFileDialog.getOpenFileName(
            self, "Mo bang map ngo ra", os.path.dirname(FILE_MAP_MAC_DINH),
            "JSON (*.json)")
        if duong_dan:
            self._nap_map(duong_dan)

    def _nap_map(self, duong_dan, im_lang=False):
        if not os.path.exists(duong_dan):
            if not im_lang:
                QMessageBox.warning(self, "Khong thay file", duong_dan)
            return
        try:
            with open(duong_dan, encoding="utf-8") as f:
                du_lieu = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            if not im_lang:
                QMessageBox.critical(self, "Loi doc file", str(e))
            return
        for khoa, ten in du_lieu.items():
            try:
                b, i = khoa.lstrip("Qq").split(".")
                o = self.o_ghi_chu.get((int(b), int(i)))
                if o is not None:
                    o.setText(ten)
            except (ValueError, AttributeError):
                continue
        if not im_lang:
            self.statusBar().showMessage(f"Da nap {duong_dan}")

    def _xuat_csv(self):
        duong_dan, _ = QFileDialog.getSaveFileName(
            self, "Xuat CSV", os.path.join(os.path.dirname(__file__), "output_map.csv"),
            "CSV (*.csv)")
        if not duong_dan:
            return
        try:
            with open(duong_dan, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["Dia chi", "Ten thiet bi / ghi chu"])
                for (b, i), o in sorted(self.o_ghi_chu.items()):
                    w.writerow([f"Q{b}.{i}", o.text().strip()])
        except OSError as e:
            QMessageBox.critical(self, "Loi xuat CSV", str(e))
            return
        self.statusBar().showMessage(f"Da xuat {duong_dan}")

    # ------------------------------------------------------------------
    def closeEvent(self, e):
        self.timer.stop()
        if self.plc.connected:
            try:
                self.plc.all_off(SO_BYTE)
            except Exception:
                pass
            self.plc.disconnect()
        e.accept()


def main():
    if not HAS_SNAP7:
        print("Canh bao: chua cai python-snap7, chi dung duoc che do DRY-RUN.")
    app = QApplication(sys.argv)
    win = OutputTesterWindow()
    win.resize(1100, 640)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
