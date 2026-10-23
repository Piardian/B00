from pathlib import Path
import json,hashlib,sys
import pandas as pd
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
sys.path.insert(0,str(ROOT))
from scripts.replay_live_system import source_hashes
from sfp_orb_engine.execution_policy import NO_FILL_REASONS
p=json.loads((BASE/'protocol_frozen.json').read_text())['declaration']
assert p['source_hashes']==source_hashes()
for group in ['files','inputs']:
    for path,digest in p[group].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
assert hashlib.sha256((BASE.parent/'london-orb-fix-2026-10-23/candidates.json').read_bytes()).hexdigest()==p['candidates_sha256']
r=json.loads((BASE/'results.json').read_text());out=json.loads((BASE/'outcomes.json').read_text())
flat=[]
for x in out:
    flat.append({k:v for k,v in x.items() if k!='outcome'}|{'status':x['outcome']['status']}|x['outcome']['trade'])
pd.DataFrame(flat).to_csv(BASE/'outcomes.csv',index=False)
labels={'ALL_LONDON':'Bütün London seansı','MORNING_UTC_BEFORE12':'UTC12:00 öncesi','SESSION_AND_HTF_ALIGNED':'Motor saati + HTF uyumlu'}
lines=['# Begonya00 London ORB — M1 gerçekleşme ve maliyet ölçümü','',
'**Sonuç: mevcut ORB retest giriş / tepki çıkışı sürümünde bu üç aylık örneklem pozitif edge göstermedi.** Aşağıdaki bağımsız aday ölçümleri tam bot veya gerçekleşmiş hesap getirisi değildir. Makro/haber/SFP önceliği, sinyal cooldown ve portföy risk etkileşimi ayrıca ölçülmeden aynı sonuçlar tam sisteme atfedilemez.','',
'## Ne ölçüldü?','',
'Düzeltilmiş London dedektörünün altı paritedeki102 adayının tamamı incelendi: EUR/USD, GBP/USD, USD/JPY, USD/CAD, USD/CHF, NZD/USD; Ocak/Haziran/Kasım2025. Her aday kendi boş takip defteri ve birimR riskiyle başladı; aynı gün veya sembolde çakışan adaylar olabilir. Sonuçları toplamak uygulanabilir bir portföy eğrisi oluşturmaz.','',
'Doğrudan orijinal OutcomeTracker.register_trade ve check_trade_progress çağrıldı. Limit penetrasyonu, giriş mumunda stop önceliği, aynı mumda hedef yazılmaması, tepki başarısızsa dolumu silmek yerine kapanışta çıkış, TP1 kısmi çıkış, BE ve trailing kuralları değişmedi. Gerçek kayıt dosyalarına yazma ve bildirim yöntemleri test içinde izole edildi; ağ/model çağrısı yapılmadı.','',
'Bu giriş, kullanıcının ayrıca belirttiği M1 tepe/dip kırılması teyidinin tanımlanmış bir testi değildir. Mevcut botun ORB midpoint/retest limit mekanizmasının ölçümüdür.','',
'## 1,5x paper maliyet sonucu','',
'| Grup | Toplam aday | Seviye/RR reddi | Dolmadan kapanan | Dolmuş/kapanmış | NetR | PF | Net kazanan oranı |','|---|---:|---:|---:|---:|---:|---:|---:|']
for name,c in r.items():
    v=c['1.5'];total=v['candidates']+v['geometry_rejected']
    lines.append(f"| {labels[name]} | {total} | {v['geometry_rejected']} | {v['closed_unfilled']} | {v['closed_filled']} | {v['net_r']:+.3f} | {v['pf']:.2f} | %{v['win_pct']:.1f} |")
lines+=['','Her grupta çözülmemişM1 boşluğu veya ay sonunda açık kalan aday sayısı sıfırdır. Geçmiş boşluklar sonuca sıfır olarak eklenmedi. Motor saati+HTF grubu, o anda tamamlanmışH1 verisinden mevcut1000mum görünümüyle hesaplandı; AAA uyumunun aday altkümesidir, makro onayı değildir. Sabah sınırı UTC12:00’dır; DST nedeniyle yerel London08:00’dan itibaren sabit4saatlik pencere sayılmaz.','',
'### Aylık netR — 1,5x','',
'| Grup | Ocak | Haziran | Kasım |','|---|---:|---:|---:|']
for name,c in r.items():
    v=c['1.5']['by_month'];lines.append(f"| {labels[name]} | {v['2025-01']:+.3f} | {v['2025-06']:+.3f} | {v['2025-11']:+.3f} |")
lines+=['','## Maliyet stresinin iki ayrı anlamı','',
'Mevcut paper sürtünme modeli Forex için spread_ratio=0.0002 ve işlem başına fee_r=0.08 kullanır. Spread oranı doğrudan tarihsel bid/ask serisi değildir; pasif dolum penetrasyonu ve hedef aşım tamponudur. Komisyon/kayma sabitR varsayımıdır. Gerçek The5ers komisyonu, bid/ask ve gerçekleşme makbuzu doğrulanmamıştır. Bu sonuçlara broker maliyetleri birebir düşülmüş gerçek kâr denemez.','',
'| Bütün London grubu | 1x | 1,5x | 2x |','|---|---:|---:|---:|']
v=r['ALL_LONDON']
lines.append('| Spread+ücret birlikte stres: netR | '+' | '.join(f"{v[str(m)]['net_r']:+.3f}" for m in [1.,1.5,2.])+' |')
lines.append('| Spread+ücret birlikte stres: dolum | '+' | '.join(str(v[str(m)]['closed_filled']) for m in [1.,1.5,2.])+' |')
lines.append('| Sabit1x dolumlar, yalnız ücret artışı: netR | '+' | '.join(f"{v['frozen_fill_fee_stress'][str(m)]:+.3f}" for m in [1.,1.5,2.])+' |')
lines+=['','Spread stresi aynı işlemlerin maliyetini artırmakla kalmaz; dolan aday ve çıkışlar da değişir. Bu yüzden bazı altgruplarda1,5x sonuç1x’ten daha iyi görünebilir. Bu maliyetlere dayanıklı alfa kanıtı değildir. Sabit dolum ücret stresi ise aynı32 temel dolumun ek0.04R/0.08R ücretle nasıl değiştiğini gösterir; ilave spread/kaymayı tam modellemez.','',
'## Kaybın kaynağı ve yuvarlama engeli','']
base=[x for x in out if x['multiplier']==1.5 and x['outcome']['status']=='CLOSED']
filled=[x for x in base if x['outcome']['trade']['close_reason'] not in NO_FILL_REASONS]
f=pd.DataFrame([x['outcome']['trade'] for x in filled])
lines+=['| Kapanış nedeni | Dolum | NetR |','|---|---:|---:|']
for reason,g in f.groupby('close_reason'):
    lines.append(f"| {reason} | {len(g)} | {g.net_r.sum():+.3f} |")
lines+=['','31dolumun22’si giriş mumunda tepki yetersizliğinden kapanıyor; bu grup toplam−11.760R yazıyor. Bu mekanizmanın kayba önemli katkısını gösterir; tepki kuralını kaldırmanın net kâr sağlayacağını kanıtlamaz. Bu turda kötü sonucu kurtarmak için kurallar değiştirilmedi.','',
'48aday mevcut gerçek seviye/RR denetiminde reddediliyor:46’sında TP1 minimum1.2R altında,2’sinde TP2 minimum2R altında. Dedektör hesaplanan seviyeleri parite fiyat hassasiyetine yuvarladığı için nominal1.2R/2R hedefleri gerçek yuvarlanmış giriş-stop mesafesinde alt sınırı tutmayabiliyor. Bunlar kârsız işlem sayılmadı veya motor kontrolü aşılmadı. Daha sonra bu yuvarlama davranışı düzeltilirse yeni adayların PnL’si ayrı sürüm olarak yeniden ölçülmelidir.','',
'## Belirsizlik ve sınırlar','',
'Adayın oluştuğu güne netR atayıp63gözlem işgünü üzerinde5günlük dairesel blok-bootstrap,10.000tekrar,seed173. ToplamR için koşullu%95aralıklar:','']
for name,c in r.items():
    lo,hi=c['1.5']['block_total_r_ci95'];lines.append(f"- {labels[name]}: [{lo:+.2f}, {hi:+.2f}]R.")
lines+=['','Bunlar çoklu araştırmaları düzelten kesin p-değerleri değildir. Üç seçilmiş tarihsel ay OOS değildir. Sabah grubunda yalnız10dolum olması genelleme yapmayı engeller. Geniş London grubunda bu sürüm için sonuç belirgin biçimde olumsuzdur; LondonORB ailesinin tüm varyantları hakkında hüküm değildir.','',
'1,5x dolumlarda geceye taşınan pozisyon ve aktif stopun ötesinde açıldığı tespit edilen sonraki mum sayısı sıfırdır. Bu, modelin genelde gece/gap riski olmadığı anlamına gelmez: mevcut takipçi gapstopları her zaman gerçek açılış fiyatıyla fiyatlamaz; swap da modellenmez. Hesaplanmış kapalı sonuç dizisi düşüşü gerçek eşzamanlı hesap drawdown’ı olarak sunulmadı.','',
'## Doğrulama','',
'50 test geçti:6yeni M1 replay testi ve44mevcut London/canlı işlem/replay testi. Yeni testler gerçek takipçiyle giriş mumunda SL ve maliyet, dolmadan hedefe gitmenin kazanç sayılmaması, eksik ilk dakikanın çözülmemiş kalması, IOpatchlerinin geri yüklenmesi, minimumRR kontrolü ve spread stresinin dolum seçimini değiştirmesini doğrular. Kaynak kod, aday kümesi ve M1/H1 fiyat hashleri sonuç sonrası yeniden kontrol edildi.','',
'Dosyalar: protocol_frozen.json, results.json, outcomes.json, outcomes.csv, measure.py, test_measure.py. Bu turda üretim kodu veya çalışan süreç değiştirilmedi; canlı/paper emir ya da Telegram bildirimi gönderilmedi.']
(BASE/'SONUC.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print('Verified code/data/candidates; report and flat ledger written')
