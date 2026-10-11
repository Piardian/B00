"""
🌺 Begonya 00 - Telegram Kanal / Chat ID Tespit Edici
Kullanıcı @Begonya00_bot'u kanala ekleyip bir mesaj attığında veya /start dediğinde
otomatik olarak chat ID'yi tespit eder ve .env dosyasını günceller.
"""

import os
import sys
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8607750064:AAHFMpGgOwfzRdz1W5LGPg72hzQ82GCXSvM")

def check_updates():
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if not data.get("ok"):
            print("Telegram API Hatası:", data)
            return None
        results = data.get("result", [])
        if not results:
            return None
        
        # En son güncellemeyi al
        last = results[-1]
        chat = None
        if "channel_post" in last:
            chat = last["channel_post"]["chat"]
        elif "message" in last:
            chat = last["message"]["chat"]
        elif "my_chat_member" in last:
            chat = last["my_chat_member"]["chat"]

        return chat
    except Exception as e:
        print("Hata:", e)
        return None

if __name__ == "__main__":
    print(f"🤖 @Begonya00_bot dinleniyor...")
    print(f"Lütfen Telegram'da @Begonya00_bot'u 'begonya00' kanalına YÖNETİCİ olarak ekleyin ve kanala bir mesaj yazın.")
    print(f"(Veya bota özelden /start yazın)")
    
    chat = check_updates()
    if chat:
        cid = str(chat.get("id"))
        title = chat.get("title") or chat.get("username") or chat.get("first_name")
        ctype = chat.get("type")
        print(f"✅ BULUNDU! Chat ID: {cid} | Başlık: {title} | Tür: {ctype}")
    else:
        print("Henüz bir mesaj veya kanal ekleme kaydı bulunamadı.")
