import psutil

for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
    try:
        if 'python' in proc.info['name'].lower():
            print(f"PID: {proc.info['pid']}, Cmd: {proc.info['cmdline']}")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
