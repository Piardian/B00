from pathlib import Path
import json,hashlib
import pandas as pd
BASE=Path(__file__).resolve().parent
p=json.loads((BASE/'protocol_frozen.json').read_text())
for group in ['sources','inputs']:
    for file,digest in p['declaration'][group].items():
        assert hashlib.sha256(Path(file).read_bytes()).hexdigest()==digest
assert hashlib.sha256((BASE/'audit_london.py').read_bytes()).hexdigest()==p['declaration']['code_sha256']
f=pd.read_csv(BASE/'funnel.csv');d=pd.read_csv(BASE/'crossing_diagnostics.csv')
total=f[['windows','compression_veto_windows','raw_close_crossings','london_detector_outputs']].sum()
lines=['# Begonya00 London ORB — giriş üretimi denetimi','',
'**Karar: mevcut London kolu bu örneklemde işlem adayı üretemiyor. Bu nedenle bu testten stratejinin kârlılığı veya edge yokluğu sonucu çıkarılamaz.** Önce uygulanan kurallar ile amaçlanan London açılış modeli arasındaki fark giderilmeli.','',
'## Doğrudan ölçüm','',
'Mevcut ORBDetector değiştirilmeden kullanıldı. EUR/USD, GBP/USD, USD/JPY, USD/CAD, USD/CHF ve NZD/USD; Ocak, Haziran, Kasım 2025. AUD/USD canlı konfigürasyonda dışlanmış ve normalize arşivde yoktur; başka pariteyle değiştirilmedi. Yalnız önceden var olan yerel, UTC dönüşümü belgelenmiş M15 dosyaları kullanıldı. Canlı TwelveData akışının birebir arşivi değildir; kaynak broker bid fiyatları ve tick hacmidir.','',
f"{int(total.windows):,} tamamlanmış M15 tarama penceresinde {int(total.compression_veto_windows):,} Asya filtresi vetosu var (%{100*total.compression_veto_windows/total.windows:.3f}). Mevcut aralık tanımında {len(d):,} ham kapanış kırılması bulundu. Bunların {int(d.compression_veto.sum()):,} tanesi Asya filtresine takıldı. London dedektör çıktısı: **{int(total.london_detector_outputs)}**.", '',
'| Parite | Ham aralık kırılması | London dedektör çıktısı |','|---|---:|---:|']
for symbol,g in f.groupby('symbol'):
    lines.append(f"| {symbol} | {int(g.raw_close_crossings.sum())} | {int(g.london_detector_outputs.sum())} |")
lines+=['',f"Ham kırılmaların {int(d.morning_window.sum())} tanesi bilginin kullanılabilir olduğu UTC saat 12:00 öncesindedir. {int(d.engine_session_open.sum())} tanesi mevcut üst motorun saat kapısına uygundur. Bunlar bağımsız işlem veya dolum sayısı değildir; aynı gün tekrarlayan kırılmalar olabilir. Tam motor ayrıca SFP önceliği, HTF, makro, haber, risk ve gerçekleşme kuralları uygular. Bu kapıları kapatıp sıfır adayı kâra dönüştürmedik.", '',
'## Üç uygulama farkı','',
'1. **Saat:** config Londra açılışını yıl boyunca 07:00 UTC tutuyor. London yerel 08:00 çıpası kışın 08:00 UTC, yazın 07:00 UTC olur. Bu, Londra 08:00 modeli amaçlanıyorsa kışın bir saatlik farktır. Forex merkezi borsa açılışı gibi tek bir zorunlu çıpaya sahip değildir; burada 08:00 London araştırma tanımıdır. session_anchors.json örnekleri içerir.','',
'2. **Aralık:** 15 dakikalık M15 mumlar açılış zamanıyla etiketlidir. Mevcut `>=07:00` ve `<=07:15` seçimi iki mum içerir: 07:00–07:15 ve 07:15–07:30. Böylece 15 dakika yazmasına rağmen fiilen 30 dakika kullanılır. Giriş kırılma mumu tamamlandıktan sonra bilinir; geçmiş mum başında gerçekleşme varsayılmadı.','',
'3. **Asya sıkışması:** `AsyaHigh-AsyaLow > 0.70 × son14M15 ortalama(high-low)` koşulu vetodur. Bu sağ taraf günlük ATR değildir; gerçek ATR tanımındaki önceki kapanış boşluklarını da içermez. Altı saatlik Asya aralığını tek M15 mumunun ortalama boyuyla kıyaslar. Bu örneklemde kapıyı neredeyse tamamen kapatıyor. Yalnız oranı büyüterek sonuç aramak yerine sıkışmanın neye göre tanımlandığı açıkça belirlenmeli. Günlük ATR kullanmak ayrı bir strateji hipotezidir, otomatik bir kod düzeltmesi değildir.','',
'Ek bulgu: min_vol_ratio=2.0 bir sert veto değildir. Sinyal geometri koşullarını geçtiğinde spike_ratio=1.8 ile A+ dönebilir; üst motor HTF uyumunda notu AAA yapabilir. “Her ORB mutlaka ≥2x hacimle doğrulanır” varsayımı doğru değil. Bu, ayrıca testle yeniden üretildi.','',
'## Buradan devam için sabit kapsam','',
'Çalışmanın merkezi Begonya00 London ORB olarak daraltıldı. Öncelik sırası: London yerel saat çıpası ve yarı-açık 15 dakikalık aralık uygulamasını izole araştırma sürümünde düzeltmek; Asya sıkışması için açık ve geçmişe bakmayan bir normalizasyon tanımı seçmek; gerçek üretim entry/SL/TP ve M1 takipçisiyle aynı adayların dolumlarını ölçmek. Bunlar yapılmadan yeni PF veya netR yazılmamalı.','',
'Önce mevcut kuralların sıfır adayı ürettiğini kayda aldık. Filtreleri kaldırarak, makroyu otomatik onaylayarak veya başka giriş modeli icat ederek bir pozitif backtest üretilmedi. Kullanıcının M1 tepe/dip teyidi mevcut ORB retest girişinin birebir aynısı sayılmadı; gerekirse ayrı varyant olarak tanımlanmalıdır.','',
'Bu turdaki test bir **sinyal üretimi denetimidir**, maliyetli PnL backtesti değildir. Üretim kodu, canlı süreçler, bildirimler ve emirler değiştirilmedi. Yeni servis/API çağrısı yapılmadı.','',
'## Kontroller ve dosyalar','',
'5 test geçti: iki M15 mumunun aralığa girmesi, 1.8x hacmin 2x ayarına rağmen veto olmaması, sıkışma vetosunun gerçek dedektörde uygulanması, London DST dönüşümü ve gelecekteki mumun tamamlanmış pencereye girmemesi. Protokoldeki kaynak kod ve fiyat hashleri sonuç sonrası yeniden doğrulandı. Örneklem görülmemiş OOS değildir; eksiksiz tick/aylık kapsama sertifikası verilmedi.','',
'protocol_frozen.json, funnel.csv, crossing_diagnostics.csv, candidates.json, session_anchors.json, audit_london.py ve test_london.py aynı klasördedir.']
(BASE/'SONUC.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print('Original source/data hashes unchanged; report written')
