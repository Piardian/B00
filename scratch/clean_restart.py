import psutil
import os
import time

target_cmds = ['sfp_orb_engine.run_engine', 'start_begonya.py']
for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmdline = ' '.join(proc.info['cmdline'] or [])
        if any(t in cmdline for t in target_cmds):
            pid = proc.info['pid']
            print(f"Terminating PID {pid}: {cmdline[:60]}...")
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

time.sleep(1)

for p in ['orchestrator/begonya00_orchestrator.lock', 'data/runtime.lock']:
    if os.path.exists(p):
        try:
            os.remove(p)
            print(f"Removed {p}")
        except Exception as e:
            print(f"Failed to remove {p}: {e}")

print("Clean termination complete.")
