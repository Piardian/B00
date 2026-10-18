import sys, os
sys.path.insert(0, os.path.abspath("."))
import psutil
import requests
import datetime
from sfp_orb_engine.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# Check process
pids = [p.pid for p in psutil.process_iter() if 'python' in p.name().lower()]
engine_proc = None
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    cmd = ' '.join(p.info['cmdline'] or [])
    if 'run_engine' in cmd:
        engine_proc = p

print("Engine Process Found:", engine_proc.info if engine_proc else "None")

# Test Telegram connectivity
url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
try:
    res = requests.get(url, timeout=5)
    print("Telegram Bot Status:", res.status_code, res.json().get("result", {}).get("username"))
except Exception as e:
    print("Telegram Error:", e)
