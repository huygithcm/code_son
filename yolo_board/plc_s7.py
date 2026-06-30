#coding=utf-8
"""Ket noi PLC Siemens S7 (S7-1200/1500/300/400) qua python-snap7.

Dung de gui ket qua kiem tra (PASS/FAIL) tu detect_components xuong PLC, hoac
doc tin hieu trigger tu PLC (vd cam bien bao co board -> chup & detect).

LUU Y voi S7-1200/1500:
  - Trong TIA Portal, MO "Permit PUT/GET communication" o thuoc tinh CPU (Protection).
  - DB muon doc/ghi tu ben ngoai phai TAT "Optimized block access" (de truy cap
    theo dia chi byte/bit co dinh).

Vi du:
    from plc_s7 import S7
    plc = S7("192.168.1.10").connect()      # rack=0, slot=1 cho S7-1200/1500
    plc.write_bool(db=1, byte=0, bit=0, value=True)    # DB1.DBX0.0 = TRUE (PASS)
    plc.write_int(db=1, byte=2, value=5)               # DB1.DBW2 = 5 (so loi)
    print(plc.read_bool(db=1, byte=0, bit=1))          # doc DB1.DBX0.1
    plc.disconnect()

Test nhanh:
    fpm_core\\.venv\\Scripts\\python.exe yolo_board\\plc_s7.py --ip 192.168.1.10
"""
import struct
import argparse

import snap7


class S7:
    def __init__(self, ip, rack=0, slot=1):
        """rack/slot: S7-1200 & S7-1500 thuong la rack=0, slot=1.
        S7-300/400 thuong rack=0, slot=2."""
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.client = snap7.client.Client()

    def connect(self):
        self.client.connect(self.ip, self.rack, self.slot)
        if not self.client.get_connected():
            raise ConnectionError(f"Khong ket noi duoc PLC {self.ip}")
        return self

    def disconnect(self):
        try:
            self.client.disconnect()
        except Exception:
            pass

    @property
    def connected(self):
        try:
            return self.client.get_connected()
        except Exception:
            return False

    # ---------- doc ----------
    def read_bool(self, db, byte, bit):
        data = self.client.db_read(db, byte, 1)
        return snap7.util.get_bool(data, 0, bit)

    def read_int(self, db, byte):
        """INT 16-bit co dau (DBW)."""
        data = self.client.db_read(db, byte, 2)
        return struct.unpack(">h", bytes(data))[0]

    # ---------- ghi ----------
    def write_bool(self, db, byte, bit, value):
        data = self.client.db_read(db, byte, 1)     # doc-sua-ghi de khong dap bit khac
        snap7.util.set_bool(data, 0, bit, bool(value))
        self.client.db_write(db, byte, data)

    def write_int(self, db, byte, value):
        self.client.db_write(db, byte, bytearray(struct.pack(">h", int(value))))

    # ---------- tien ich cho inspection ----------
    def send_result(self, ok_all, n_fail=0, db=1, byte=0, bit_pass=0, bit_fail=1, byte_count=2):
        """Gui ket qua 1 lan kiem tra: bit PASS, bit FAIL, so loai NG.
        Chinh db/byte/bit cho khop dia chi DB ben PLC cua ban."""
        self.write_bool(db, byte, bit_pass, ok_all)
        self.write_bool(db, byte, bit_fail, not ok_all)
        self.write_int(db, byte_count, n_fail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--rack", type=int, default=0)
    ap.add_argument("--slot", type=int, default=1)
    args = ap.parse_args()

    plc = S7(args.ip, args.rack, args.slot)
    try:
        plc.connect()
        print(f"Da ket noi PLC {args.ip} (rack={args.rack}, slot={args.slot})")
        info = plc.client.get_cpu_info()
        print("CPU:", info.ModuleTypeName.decode(errors="ignore").strip("\x00"))
    except Exception as e:
        print("Loi:", e)
    finally:
        plc.disconnect()


if __name__ == "__main__":
    main()
