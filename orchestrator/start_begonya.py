import subprocess
import sys
import time
import os
import signal
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
MACRO_DIR = BASE_DIR / "macro_engine"
SFP_ORB_DIR = BASE_DIR / "sfp_orb_engine"
LOCK_FILE = BASE_DIR / "orchestrator" / "begonya00_orchestrator.lock"


def is_pid_running(pid: int, expected_image: str = "python") -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                text=True, stderr=subprocess.DEVNULL
            ).strip().lower()
            return expected_image.lower() in out
        except Exception:
            return False
    return False


def acquire_orchestrator_lock() -> bool:
    for attempt in range(2):
        try:
            fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
            return True
        except FileExistsError:
            try:
                old_pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
                if is_pid_running(old_pid, "python"):
                    print(f"[Begonya 00 Orchestrator] ℹ️ Begonya 00 zaten çalışıyor (PID: {old_pid}). Çıkılıyor.")
                    return False
                LOCK_FILE.unlink(missing_ok=True)
            except Exception:
                try:
                    LOCK_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception as e:
            print(f"[Begonya 00 Orchestrator] ⚠️ Kilit dosyası oluşturulamadı: {e}")
            return True
    return False


def release_orchestrator_lock():
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception:
        pass


def cleanup_stale_lock(engine_dir: Path, label: str):
    lock_file = engine_dir / "data" / "runtime.lock"
    if lock_file.exists():
        try:
            lock_file.unlink(missing_ok=True)
            print(f"[Begonya 00 Orchestrator] 🧹 {label} runtime.lock temizlendi.")
        except Exception as e:
            print(f"[Begonya 00 Orchestrator] ⚠️ {label} runtime.lock silinemedi: {e}")


def prevent_system_sleep():
    if sys.platform == "win32":
        try:
            import ctypes
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000040)
            print("[Begonya 00 Orchestrator] 🛡️ Windows Uyku Kilidi Aktif Edildi (İşlemler kesintisiz sürecek).")
        except Exception as e:
            print(f"[Begonya 00 Orchestrator] ⚠️ Uyku kilidi uyarısı: {e}")


def restore_system_sleep():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            print("[Begonya 00 Orchestrator] 💤 Windows Uyku Kilidi Kaldırıldı.")
        except Exception:
            pass


def run_macro_sync():
    state_file = BASE_DIR / "shared" / "macro_bias_gate.json"
    if state_file.exists():
        try:
            age_sec = time.time() - state_file.stat().st_mtime
            if age_sec < 3600:
                print(f"\n[Begonya 00 Orchestrator] ℹ️ Makro Kapı Verisi güncel ({int(age_sec // 60)} dk önce güncellendi). Servisler doğrudan başlatılıyor...")
                return
        except Exception:
            pass
    print("\n[Begonya 00 Orchestrator] 🚀 1. Makro Rejim Motoru İlk Analiz Döngüsü Çalıştırılıyor...")
    cmd = [sys.executable, str(MACRO_DIR / "main.py")]
    try:
        res = subprocess.run(cmd, cwd=str(MACRO_DIR), timeout=180)
        if res.returncode == 0:
            print("[Begonya 00 Orchestrator] ✅ Makro Kapı Verisi Başarıyla Güncellendi.")
        else:
            print(f"[Begonya 00 Orchestrator] ⚠️ Makro Motor {res.returncode} kodu ile tamamlandı.")
    except Exception as e:
        print(f"[Begonya 00 Orchestrator] ⚠️ Makro ilk döngü hatası: {e}")


def spawn_macro_daemon():
    print("[Begonya 00 Orchestrator] 📡 Makro Daemon başlatılıyor...")
    daemon_cmd = [sys.executable, str(MACRO_DIR / "daemon" / "macro_scheduler.py")]
    return subprocess.Popen(daemon_cmd, cwd=str(MACRO_DIR))


def spawn_sfp_orb_engine():
    print("[Begonya 00 Orchestrator] 🎯 SFP + Hacim Anomalisi & ORB Seans Motoru başlatılıyor...")
    cleanup_stale_lock(BASE_DIR, "Begonya 00 SFP/ORB")
    cmd = [sys.executable, "-m", "sfp_orb_engine.run_engine", "--live"]
    return subprocess.Popen(cmd, cwd=str(BASE_DIR))


def main():
    if not acquire_orchestrator_lock():
        sys.exit(0)

    print("=" * 70)
    print(" 🌺 BEGONYA 00: SFP + HACİM ANOMALİSİ & ORB OTONOM İŞLEM SİSTEMİ 🌺 ")
    print("=" * 70)
    print("Mimari: Macro Multi-AGI Army + SFP/Volume Engine + ORB Session Breakout")
    print(f"Konum: {BASE_DIR}")
    print("-" * 70)

    p_daemon = None
    p_sfp_orb = None

    try:
        # 1. Mikro Motoru ve Makro Daemon'ı Başlat
        p_daemon = spawn_macro_daemon()
        p_sfp_orb = spawn_sfp_orb_engine()

        # 2. Makro Kapı Verisini Kontrol Et
        run_macro_sync()

        print("\n" + "=" * 70)
        print(" 🟢 BEGONYA 00 AKTİF VE NÖBETTE. DURDURMAK İÇİN CTRL+C.")
        print("=" * 70)
        prevent_system_sleep()

        while True:
            time.sleep(3)

            # Makro Daemon Süpervizör Kontrolü
            if p_daemon is not None and p_daemon.poll() is not None:
                print(f"\n[Begonya 00 Orchestrator] ⚠️ Macro Daemon durdu (Kod: {p_daemon.returncode}). 5s içinde yeniden başlatılıyor...")
                time.sleep(5)
                p_daemon = spawn_macro_daemon()

            # SFP & ORB Engine Süpervizör Kontrolü
            if p_sfp_orb is not None and p_sfp_orb.poll() is not None:
                print(f"\n[Begonya 00 Orchestrator] ⚠️ SFP & ORB Motoru durdu (Kod: {p_sfp_orb.returncode}). 5s içinde yeniden başlatılıyor...")
                time.sleep(5)
                p_sfp_orb = spawn_sfp_orb_engine()

    except KeyboardInterrupt:
        print("\n[Begonya 00 Orchestrator] 🛑 Kapatma sinyali alındı...")
        for name, proc in [("Macro Daemon", p_daemon), ("SFP/ORB Engine", p_sfp_orb)]:
            if proc is not None and proc.poll() is None:
                print(f"  -> {name} sonlandırılıyor...")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print("[Begonya 00 Orchestrator] Sistem güvenle kapatıldı.")
    finally:
        restore_system_sleep()
        release_orchestrator_lock()


if __name__ == "__main__":
    main()
