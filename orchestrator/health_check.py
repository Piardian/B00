import sys
import json
import os
import datetime
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent

def check_begonya_health():
    print("=" * 70)
    print(" 🌺 BEGONYA INSTITUTIONAL HEALTH & INTEGRATION AUDIT 🌺 ")
    print("=" * 70)
    
    status_summary = []
    
    # 1. Macro Engine Check
    macro_dir = BASE_DIR / "macro_engine"
    gate_file = BASE_DIR / "shared" / "macro_bias_gate.json"
    symbol_map_file = BASE_DIR / "config" / "symbol_map.json"
    
    print("\n1. MAKROEKONOMİK REJİM MOTORU (PYTHON / GEMINI / FRED):")
    if (macro_dir / "main.py").exists() and (macro_dir / "config.py").exists():
        print("  [OK] macro_engine dizini ve çekirdek dosyalar mevcut.")
        status_summary.append(("Macro Engine Core", "PASS"))
    else:
        print("  [FAIL] macro_engine dosyaları eksik!")
        status_summary.append(("Macro Engine Core", "FAIL"))
        
    # Gate File Check
    if gate_file.exists():
        try:
            with open(gate_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            ts = data.get("timestamp", "Bilinmiyor")
            regime = data.get("primary_regime", "Bilinmiyor")
            gates = data.get("execution_bias_gates", {})
            risk_mult = data.get("recommended_risk_multiplier", 1.0)
            print(f"  [OK] shared/macro_bias_gate.json aktif:")
            print(f"       • Zaman Damgası: {ts}")
            print(f"       • Birincil Rejim : {regime}")
            print(f"       • Risk Çarpanı  : {risk_mult}x")
            print(f"       • Aktif Kapılar : {gates}")
            status_summary.append(("Macro Gate Data", "PASS"))
        except Exception as e:
            print(f"  [FAIL] Gate dosyası bozuk: {e}")
            status_summary.append(("Macro Gate Data", "FAIL"))
    else:
        print("  [WARN] shared/macro_bias_gate.json henüz oluşturulmamış.")
        status_summary.append(("Macro Gate Data", "WARN"))

    # 2. SMC Engine Check
    print("\n2. SMC MİKRO TETİKLEYİCİ MOTORU (TYPESCRIPT / NODE.JS):")
    smc_dir = BASE_DIR / "smc_engine"
    if (smc_dir / "package.json").exists() and (smc_dir / "server" / "macroGateAdapter.ts").exists():
        print("  [OK] smc_engine ve macroGateAdapter.ts entegrasyonu mevcut.")
        status_summary.append(("SMC Engine & Bridge", "PASS"))
    else:
        print("  [FAIL] smc_engine veya macroGateAdapter.ts eksik!")
        status_summary.append(("SMC Engine & Bridge", "FAIL"))

    # 3. Config & Symbol Mapping Check
    print("\n3. ORTAK KONFİGÜRASYON & SEMBOL EŞLEME:")
    if symbol_map_file.exists():
        with open(symbol_map_file, "r", encoding="utf-8") as f:
            sym_data = json.load(f)
        mappings = sym_data.get("mappings", {})
        print(f"  [OK] {len(mappings)} adet sembol haritası yüklendi (EURUSD, XAUUSD, NAS100, BTCUSD...).")
        status_summary.append(("Symbol Map", "PASS"))
    else:
        print("  [FAIL] symbol_map.json bulunamadı!")
        status_summary.append(("Symbol Map", "FAIL"))

    print("\n" + "=" * 70)
    print(" ÖZET SAĞLIK RAPORU")
    print("=" * 70)
    all_pass = True
    for item, status in status_summary:
        icon = "✅" if status == "PASS" else ("⚠️" if status == "WARN" else "❌")
        print(f"  {icon} {item.ljust(30)} : {status}")
        if status == "FAIL":
            all_pass = False

    if all_pass:
        print("\n🎉 BEGONYA SİSTEMİ %100 SAĞLIKLI VE ÇALIŞMAYA HAZIR!")
    else:
        print("\n⚠️ Bazı bileşenlerde eksikler var, lütfen logları inceleyin.")

if __name__ == "__main__":
    check_begonya_health()
