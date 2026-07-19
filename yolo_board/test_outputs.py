#coding=utf-8
"""Tool test ngo ra (Q) cua PLC S7 de MAP lai dia chi ngo ra thuc te.

!!! CANH BAO AN TOAN !!!
Tool nay GHI truc tiep xuong vung Q -> se KICH THAT cac thiet bi dang dau noi
(relay, van khi nen, xy lanh, dong co, den...). Truoc khi dung:
  - Bao dam KHONG co nguoi dang thao tac trong vung may.
  - Nen ngat tai/khi nen neu chi muon nghe tieng relay de map dia chi.
  - Uu tien che do PULSE (bat roi tu tat) thay vi giu ON lau.

Cach dung:
    # Chay thu, KHONG ghi gi xuong PLC (an toan de lam quen truoc):
    .venv\\Scripts\\python.exe yolo_board\\test_outputs.py --ip 192.168.0.1 --dry-run

    # Chay that:
    .venv\\Scripts\\python.exe yolo_board\\test_outputs.py --ip 192.168.0.1

LUU Y KY THUAT khi CPU o che do RUN:
    Neu chuong trinh PLC co lenh ghi vao cung ngo Q do, no se GHI DE lai sau moi
    vong quet -> ngo ra co the nhap nhay hoac khong len duoc. Neu gap hien tuong
    do, chuyen CPU sang STOP (luu y: nhieu CPU tu tat ngo ra khi STOP) hoac tam
    thoi khoa doan chuong trinh dieu khien ngo ra do trong TIA Portal.
"""
import argparse
import time

import snap7
from snap7.type import Area


class OutputTester:
    def __init__(self, ip, rack=0, slot=1, dry_run=False):
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.dry_run = dry_run
        self.client = snap7.client.Client()

    def connect(self):
        if self.dry_run:
            print("[DRY-RUN] Bo qua ket noi that, khong ghi gi xuong PLC.")
            return self
        self.client.connect(self.ip, self.rack, self.slot)
        if not self.client.get_connected():
            raise ConnectionError(f"Khong ket noi duoc PLC {self.ip}")
        return self

    def disconnect(self):
        if self.dry_run:
            return
        try:
            self.client.disconnect()
        except Exception:
            pass

    # ---------- doc ----------
    def read_byte(self, byte):
        if self.dry_run:
            return 0
        return self.client.read_area(Area.PA, 0, byte, 1)[0]

    def read_bit(self, byte, bit):
        return bool(self.read_byte(byte) & (1 << bit))

    # ---------- ghi ----------
    def write_bit(self, byte, bit, value):
        """Doc-sua-ghi de khong dap cac bit khac trong cung byte."""
        if self.dry_run:
            print(f"    [DRY-RUN] se ghi Q{byte}.{bit} = {int(bool(value))}")
            return
        data = self.client.read_area(Area.PA, 0, byte, 1)
        snap7.util.set_bool(data, 0, bit, bool(value))
        self.client.write_area(Area.PA, 0, byte, data)

    def all_off(self, nbytes=8):
        """Tat toan bo ngo ra Q0..Q(nbytes-1) - dung khi can dung khan."""
        if self.dry_run:
            print(f"    [DRY-RUN] se tat toan bo Q0..Q{nbytes - 1}")
            return
        for b in range(nbytes):
            try:
                self.client.write_area(Area.PA, 0, b, bytearray([0]))
            except Exception:
                pass

    # ---------- kich ban test ----------
    def pulse(self, byte, bit, duration=1.0):
        """Bat ngo ra trong `duration` giay roi TU TAT (an toan nhat de map)."""
        print(f"  -> Q{byte}.{bit} = ON  (giu {duration}s)")
        self.write_bit(byte, bit, True)
        try:
            time.sleep(duration)
        finally:
            self.write_bit(byte, bit, False)
            print(f"  -> Q{byte}.{bit} = OFF")

    def dump(self, nbytes=4):
        print("\n--- Trang thai ngo ra hien tai ---")
        for b in range(nbytes):
            try:
                v = self.read_byte(b)
                bits = " ".join(f"Q{b}.{i}={int(bool(v & (1 << i)))}" for i in range(8))
                print(f"  QB{b} = {v:3d} (0b{v:08b})   {bits}")
            except Exception as e:
                print(f"  QB{b} -> LOI {str(e)[:60]}")
        print()


HELP = """
Lenh:
  <byte>.<bit>        Xung ngo ra do (vd: 0.3  -> bat Q0.3 roi tu tat)
  <byte>.<bit> on     Bat va GIU ngo ra do
  <byte>.<bit> off    Tat ngo ra do
  scan                Quet lan luot Q0.0 -> Q0.7, moi ngo xung 1 lan (de map nhanh)
  scan <byte>         Quet lan luot 8 bit cua byte do
  read                Doc va in trang thai ngo ra hien tai
  off                 TAT TOAN BO ngo ra (dung khan)
  t <giay>            Doi thoi gian xung (mac dinh 1.0s)
  h                   In lai tro giup nay
  q                   Thoat (tu dong tat het ngo ra truoc khi thoat)
"""


def main():
    ap = argparse.ArgumentParser(description="Test/map ngo ra PLC S7")
    ap.add_argument("--ip", default="192.168.0.1")
    ap.add_argument("--rack", type=int, default=0)
    ap.add_argument("--slot", type=int, default=1)
    ap.add_argument("--bytes", type=int, default=4, help="so byte Q hien thi khi 'read'")
    ap.add_argument("--dry-run", action="store_true", help="khong ghi that xuong PLC")
    args = ap.parse_args()

    print("=" * 62)
    print(" TOOL TEST NGO RA PLC - CANH BAO: SE KICH THIET BI THAT ")
    print("=" * 62)
    print(f" PLC: {args.ip}  rack={args.rack} slot={args.slot}")
    if args.dry_run:
        print(" CHE DO: DRY-RUN (khong ghi gi xuong PLC)")
    else:
        print(" CHE DO: GHI THAT xuong PLC")
        print("\n Bao dam khong co nguoi trong vung may truoc khi tiep tuc.")
        if input(" Go 'YES' de xac nhan tiep tuc: ").strip() != "YES":
            print(" Da huy.")
            return

    tester = OutputTester(args.ip, args.rack, args.slot, args.dry_run)
    try:
        tester.connect()
    except Exception as e:
        print("Loi ket noi:", e)
        return

    print(HELP)
    tester.dump(args.bytes)

    pulse_time = 1.0
    try:
        while True:
            try:
                cmd = input(f"[xung={pulse_time}s] > ").strip().lower()
            except EOFError:
                break
            if not cmd:
                continue

            if cmd == "q":
                break
            if cmd == "h":
                print(HELP)
                continue
            if cmd == "read":
                tester.dump(args.bytes)
                continue
            if cmd == "off":
                print("  -> TAT TOAN BO ngo ra")
                tester.all_off(args.bytes)
                continue
            if cmd.startswith("t "):
                try:
                    pulse_time = float(cmd.split()[1])
                    print(f"  -> Thoi gian xung = {pulse_time}s")
                except (IndexError, ValueError):
                    print("  Cu phap: t <giay>   vd: t 0.5")
                continue

            if cmd.startswith("scan"):
                parts = cmd.split()
                byte = int(parts[1]) if len(parts) > 1 else 0
                print(f"  Quet Q{byte}.0 -> Q{byte}.7, moi ngo xung {pulse_time}s")
                for bit in range(8):
                    try:
                        input(f"    Enter de xung Q{byte}.{bit} (Ctrl+C de dung)... ")
                    except EOFError:
                        print("\n    Ket thuc nhap - dung quet.")
                        break
                    tester.pulse(byte, bit, pulse_time)
                continue

            # dang <byte>.<bit> [on|off]
            parts = cmd.split()
            try:
                byte_s, bit_s = parts[0].split(".")
                byte, bit = int(byte_s), int(bit_s)
                if not 0 <= bit <= 7:
                    print("  Bit phai trong khoang 0..7")
                    continue
            except (ValueError, IndexError):
                print("  Khong hieu lenh. Go 'h' de xem tro giup.")
                continue

            if len(parts) > 1 and parts[1] == "on":
                print(f"  -> Q{byte}.{bit} = ON (giu)")
                tester.write_bit(byte, bit, True)
            elif len(parts) > 1 and parts[1] == "off":
                print(f"  -> Q{byte}.{bit} = OFF")
                tester.write_bit(byte, bit, False)
            else:
                tester.pulse(byte, bit, pulse_time)

    except KeyboardInterrupt:
        print("\n  Ngat boi nguoi dung.")
    finally:
        print("\nDang tat toan bo ngo ra truoc khi thoat...")
        tester.all_off(args.bytes)
        tester.dump(args.bytes)
        tester.disconnect()
        print("Da ngat ket noi.")


if __name__ == "__main__":
    main()
