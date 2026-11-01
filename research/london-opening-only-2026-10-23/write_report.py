from pathlib import Path
import hashlib,json,sys
import pandas as pd
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1];sys.path.insert(0,str(ROOT))
from scripts.replay_live_system import source_hashes
p=json.loads((BASE/'protocol_frozen.json').read_text())['declaration']
assert p['source_hashes']==source_hashes()
for group in ['files','inputs']:
    for path,digest in p[group].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
r=json.loads((BASE/'results.json').read_text());out=json.loads((BASE/'outcomes.json').read_text())
pd.DataFrame([{k:v for k,v in x.items() if k!='outcome'}|{'status':x['outcome']['status']}|x['outcome']['trade'] for x in out]).to_csv(BASE/'outcomes.csv',index=False)
lines=['# London açılışı — kullanıcıya göre daraltılmış ORB','',
'## Kesin işlem kapsamı','',
'Kullanıcı: yalnız London açılışı; parite başına günde bir kez, London yerel12:00ye kadar.','',
'- ORB yalnız LONDON seansında aktiftir. NEW_YORK ve TOKYO dedektör dalları devre dışıdır. SFP seans/tetik kuralları değiştirilmedi.',
'- Açılış aralığı Europe/London08:00–08:15; sadece tamamlanmış M15 mumları. Yeni ORB sinyali/emri karar anında yerel12:00den önce olmalıdır. Yazın UTC11:00, kışın UTC12:00 sınırıdır.',
'- Bir paritenin ilk kabul edilmiş ORB limit emri o London takvim gününün hakkını tüketir. Yön değiştirmek veya emrin dolmaması yeni denemeye izin vermez. Minimum seviye/RR veya diğer kabul kapılarını geçemeyen ham aday hak tüketmez.',
'- Günlük kilit kayıt geçmişine yazılır. Yeniden başlangıçta geçmiş ve aktif/kapalı işlem defterleri kontrol edilir; yalnız45dakikalık cooldowna dayanılmaz.',
'- Yeni adayın entry_deadline_utc alanı limit takipçisine taşınır. Yerel12:00de bekleyen limit maliyetsiz TIMEOUT_NO_FILL olur; M1 kapanış saati sınırında konservatif olarak dolum yazılmaz. Dolmuş pozisyon zorla kapatılmaz; mevcut SL/TP/BE/trailing izlemesi sürer.',
'- London16:30 alanı nominal seans sonu olarak kalsa da yeni girişin son saati12:00dir. Bu ayar London seansının tamamında yeniden girişe izin vermez.','',
'## Yeni kapsamla yeniden ölçüm','',
'Aynı altı parite ve Ocak/Haziran/Kasım2025 kullanıldı. Eski102 adaydan yeni dedektörle yeniden hesaplandığında açılış penceresinde36ham aday kaldı; fiyat seviyeleri değişmedi. Ana grupta20aday yuvarlanmış minimumRR nedeniyle reddedildi,1tekrar günlük hak sınırına takıldı ve15emir denemesi seçildi.','',
'Sonuçlar bağımsız, birim riskli aday testleridir; farklı paritelerin eşzamanlı risklerini uygulayan tam bot/portföy getirisi değildir. Makro, haber, SFP önceliği ve ortak risk kapıları bu ölçümde yoktur. İkinci grup yalnız mevcut motor saatine veHTF yönüne uyan ilk geçerli adayı seçer; makro onayı varsayılmaz.','',
'| Grup | Maliyet | Emir denemesi | Dolum | NetR | PF |','|---|---:|---:|---:|---:|---:|']
labels={'OPENING_CORE':'London açılış çekirdeği','SESSION_HTF':'Motor saati + HTF uyumu'}
for name,v in r.items():
    for m in ['1.0','1.5','2.0']:
        z=v['costs'][m];lines.append(f"| {labels[name]} | {m}x | {v['accepted_attempts']} | {z['closed_filled']} | {z['net_r']:+.3f} | {z['pf']:.2f} |")
lines+=['','Ana grupta1,5xmaliyette6limit dolmadan kapandı;9dolumun7si giriş tepkisi çıkışı,1i SL,1i TP2 oldu. ÇözülmemişM1 boşluğu/açıkay sonu pozisyonu yok. Bu örneklemde12:00zaman aşımına gelmeden bütün denemeler başka nedenle dolmuş/kapanmıştı; saat sınırı yine sentetik uç durum testiyle doğrulandı.','',
'Önceki geniş London −14.53R sonucu bu dar kuralla aynı strateji sayılmaz. Yeni doğru kapsamın sonucu−2.837Rdir. Sabah grubunun eski−1.318R sonucu da aynı değildir: artık London yerel saat sınırı, tek günlük deneme ve emir son saati uygulanır.','',
'Spread+ücret stresi dolum ve çıkışları değiştirebilir;2xmaliyetin bazı gruplarda1.5xten iyi görünmesi sağlam edge kanıtı değildir. Aynı1xdolumları sabit tutup yalnız ücret artırıldığında ana grubun toplamı1x−2.814R,1.5x−3.214R,2x−3.614R olur. Bu sabit dolum kontrolü ek spread/kaymanın tam modeli değildir.','',
'Maliyetler mevcutpaper modelidir: Forex spreadoranı0.0002ve işlem başına0.08R temelücret. Gerçek broker bid/ask, kişisel komisyon/kayma ve swap doğrulanmadı. Bu üç tarihsel ay OOS değildir. Ana grubun1.5x5günlükblokbootstrap%95toplamR aralığı[-9.33,+2.84]R; HTF grubunda yalnız3dolum vardır. **Henüz doğrulanmış pozitif edge yoktur; HTF grubunun küçük örneklemi kalıcı sonuç vermeye yetmez.**','',
'## Kontroller','',
'56test geçti. Yeni kapsam testleri NY/Tokyo dışlanmasını, London yaz/kış12:00 sınırını, karar anını esas almayı, günlük kilidin yön/dolumdan bağımsızlığını, ertesi gün ve farklı parite serbestliğini, kayıtla kalıcılığı, makro/bildirim öncesi reddi, bekleyen limitin zaman aşımını ve dolmuş pozisyonun izlenmesini doğrular. MevcutM1/giriş/çıkış/replaytestleri de geçti. Kod, veri ve girdi hashleri yeniden doğrulandı.','',
'Üretim kaynakları düzenlendi; çalışan süreç yeniden başlatılmadı, canlı/paper emir veya bildirim gönderilmedi. Bir sonraki normal başlangıç güncel kuralları yükler. Önceki raporlar değiştirilmedi; bu çalışma yeni kapsam ve sürüm olarak ayrı tutuldu.','',
'Kaynaklar: sfp_orb_engine/config.py, orb_detector.py, orb_session_context.py, execution_policy.py, outcome_tracker.py, engine.py. Test: tests/test_london_opening_only.py. Bu klasörde before/, protocol_frozen.json, candidate_audit.json, outcomes.json, outcomes.csv, results.json bulunur.']
(BASE/'SONUC.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
print('Source/data hashes verified; scoped report written')
