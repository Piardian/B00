"""Report frozen XAUUSD development outcomes without changing any strategy rule."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,shutil
import numpy as np

BASE=Path(__file__).resolve().parent
def read(name):return json.loads((BASE/name).read_text(encoding='utf-8-sig'))
def main():
    result=read('results.json');rows=read('outcomes.json');manifest=read('quote_manifest_frozen.json');native=read('native_qa.json');clock=read('clock_qa.json');cost=read('cost_evidence.json');declaration=read('protocol_frozen.json')['declaration']
    checks={p:hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in declaration['hashes'].items()};assert all(checks.values())
    data=result['results'];complete=result['complete_coverage'];n=data['STRESS_1.5x']['fills'];primary=data['STRESS_1.5x']
    details={}
    for name,s in data.items():
        closed=sorted([r['outcome'] for r in rows if r['scenario']==name and r['outcome']['status']=='CLOSED'],key=lambda x:x['exit_time'])
        v=np.array([x['net_r'] for x in closed]);curve=np.r_[0.,v.cumsum()]
        details[name]=dict(unit_r_max_drawdown=float((np.maximum.accumulate(curve)-curve).max()),
            mean_assumed_commission_usd_per_lot_roundtrip=float(np.mean([x['assumed_commission_usd_per_lot_roundtrip'] for x in closed])) if closed else None,
            outcome_reasons={reason:sum(x['reason']==reason for x in closed) for reason in ['TP2','SL','EOD']})
    (BASE/'report_diagnostics.json').write_text(json.dumps(details,indent=2),encoding='utf8')
    words='Geliştirme kapısını geçen araştırma adayı; henüz edge veya canlı onayı değil.' if result['gate']['passed'] else 'Önceden belirlenen geliştirme kapısı geçilmedi; bu uygulamada edge doğrulanmadı.'
    lines=['# XAUUSD London ORB — sabit kurallı geliştirme testi','', '**Karar: '+words+'**','',
        'Ocak–Haziran 2025, tek enstrüman ve tek giriş/çıkış modeli. Tarihler ve kurallar sonuçlar görülmeden donduruldu. Bu dönemler önceki geniş araştırmalarda kullanılmıştı; yeni modelin gerçek ileri testi veya bütün geçmiş denemelerden bağımsız OOS verisi değildir.','',
        ('**Kapsama tam.** Bilinmeyen fiyat günü yok; doğrulanmış iki piyasa tatili işlem fırsatı sayılmadı.' if complete else '**Kapsama EKSİK.** Aşağıdaki değerler yalnız bilinen kapalı işlemlerin alt toplamıdır; tam dönem getirisi veya güven aralığı iddiası yok. Eksik günlere sıfır/kâr atanmadı.'),'',
        '## Sabit kurallar','',
        'London yerel 08:00–08:15 yarı açık BID aralığı. İlk mumun yönünde, 08:15 sonrasında bandın ilk BID teması/kırılımı; giriş 12:00’den kesin önce. Günde tek deneme. Stop karşı BID bantta sanal/yapısal tetik; pozisyonun tamamı yeni giriş riskinden 2R hedefte veya 16:00 London ilk quote’unda kapanır. Hacim filtresi, retest, M1 teyidi, TP1, BE ve trailing yok.','',
        'Alış ASK + kayma, satış BID − kayma. Uzun çıkış BID, kısa çıkış ASK. Kısa stop tetikleyicisi de BID bandıdır; gerçek broker ASK stop emriyle aynı değildir. Giriş quote’unda çıkış yok; aynı zaman damgasındaki sonraki kayıt kullanılabilir. Stop gap’inde kötü fiyat, hedef gap’inde hedefle sınırlı fiyat kullanılır. 16:00 itibarıyla EOD önceliklidir. R tek işlem başına ilk fiyat riskidir; gerçek hesap/prop kuralı veya bileşik sermaye getirisi değildir.','',
        '## Maliyet ve kanıt sınırı','',
        'Broker sembolü XAUUSD: kontrat 100 ons, fiyat adımı 0,01 USD, minimum lot ve adım 0,01. [The5ers resmî komisyon açıklaması](https://the5ers.com/faqs/what-are-the-spreads-and-commissions/) altın için yüzde formülü veriyor; sayısal oran yayımlamıyor. [Resmî kontrat tablosu](https://lp.the5ers.com/hub-assets-specifications/) 100 onsu doğruluyor.','',
        'Mevcut hesaptaki dokuz Ekim 2026 dolumu taraf başına lot başına 4 USD’ye denk geliyor. Küçük lotlarda taraf başına %0,001 de cent yuvarlamasıyla bu ücretleri açıklıyor. Bu örnekler sayısal yüzdeyi tekil belirlemiyor ve 2025 tarifesini doğrulamıyor. Gözlenen BID/ASK geçmiş quote’tur; emir dolum garantisi değildir.','',
        'Baştan sabitlenen ihtiyatlı varsayım: lot başına tur ücreti `max(8 USD, 2 × giriş fiyatı × 100 ons × %0,001)`; risk hesabı için 100’e bölünerek ons başına çevrilir. Kayma taraf başına 0,05 USD/ons (5 fiyat adımı). 1,5x/2x senaryoları gözlenen spreadi, komisyonu ve kaymayı birlikte artırır; bu yüzden giriş riskini ve çıkış yolunu da değiştirebilir. FX’in 4 USD tur komisyonu altına kopyalanmadı.','',
        '## Sonuçlar'+('' if complete else ' — yalnız bilinen kapalı işlemler'),'',
        '| Gider | İşlem | Net R | PF | Kazanma | Aynı dolumlar: komisyon öncesi R | Birim R max DD |','|---|---:|---:|---:|---:|---:|---:|']
    for name,s in data.items():
        pf=f"{s['pf']:.3f}" if s['pf'] is not None else '—';win=f"%{s['win_pct']:.1f}" if s['win_pct'] is not None else '—'
        lines.append(f"| {name} | {s['fills']} | {s['net_r']:+.2f} | {pf} | {win} | {s['price_net_r_before_commission']:+.2f} | {details[name]['unit_r_max_drawdown']:.2f} |")
    ci=primary['block_total_ci95']
    lines += ['',f"1,5x ana senaryo: **{n} işlem, {primary['net_r']:+.2f}R**. "+(f"Toplam R için 5 günlük blok bootstrap %95 aralığı **[{ci[0]:+.2f}, {ci[1]:+.2f}]R**." if complete else 'Kapsama eksik olduğundan JSON’daki CI tam dönem doğrulamasında kullanılmaz.'),'',
        'Komisyon öncesi R, aynı giriş/çıkışlarda yalnız ücretin çıkarılmadığı tanıdır; spread ve kayma hâlâ fiyatların içindedir. Tam sürtünmesiz model veya farklı dolum yolları üzerinde matematiksel üst sınır değildir.', '',
        '## Aylık dağılım','', '| Ay | 1x | 1,5x | 2x |','|---|---:|---:|---:|']
    for month in declaration['development_months']:
        lines.append('| '+month+' | '+' | '.join(f"{s['by_month'][month]:+.2f}" for s in data.values())+' |')
    lines += ['',f"En iyi 5 kapalı işlem çıkarılınca 1,5x tanısı: **{primary['without_best5']:+.2f}R**." if primary['without_best5'] is not None else 'Beş işlem çıkarma tanısı için örnek yetersiz.','',
        f"2x stresinde en iyi 5 işlem çıkarılınca **{data['STRESS_2x']['without_best5']:+.2f}R**. 1,5x toplamının **%{primary['by_month']['2025-05']/primary['net_r']*100:.1f}** kadarı Mayıs 2025'ten geliyor." if primary['net_r'] else 'Mayıs kâr yoğunlaşması oranı toplam sıfır olduğu için tanımsız.','',
        'Bunlar yoğunlaşma tanılarıdır; sonradan kazanan gün/parite seçmek veya yeni filtre belirlemek için kullanılmadı. Tek ay yoğunlaşması, nedenin hangi piyasa rejimi olduğu hakkında tek başına nedensel kanıt değildir.','',
        '## Veri ve karar kapısı','',
        f"- Manifest: {len(manifest['files'])} hafta içi gün. Kullanılabilir quote dosyası {sum(v['status']=='AVAILABLE' for v in manifest['files'].values())}; doğrulanmış tatil {sum(v['status']=='CONFIRMED_HOLIDAY_CLOSED' for v in manifest['files'].values())}.",
        f"- İlk 15 dakika doğal M15 fiyat/yön uyumu: {sum(x['price_direction_match'] for x in native['rows'])}/{len(native['rows'])}. BID bayraklı tick sayısı ile doğal hacim uyumu {sum(x['volume_match'] for x in native['rows'])}/{len(native['rows'])}; hacim girişte kullanılmadı.",
        f"- Bağımsız TwelveData EURUSD ile aynı broker saati kontrolü {clock['strong_days']} güçlü gün, {len(clock['conflicts'])} çelişki; ABD/Avrupa DST farkında {len(clock['us_eu_dst_gap_days'])} gün. Bu, bağımsız altın fiyat serisiyle doğrudan korelasyon testi değildir.",
        '- Açılış/EOD quote’u 5 saniye içinde; seans içi en büyük boşluk 60 saniye. Doji veya öğlene kadar giriş olmaması stratejinin belirli no-entry sonuçlarıdır; veri eksikliği değildir. Bilinmeyenler ayrıca işaretlenir.', '',
        '| Kontrol | Sonuç |','|---|---|']
    for key,value in result['gate']['checks'].items():lines.append(f"| {key} | {'GEÇTİ' if value else 'KALDI'} |")
    if (BASE/'repair_result.json').exists():
        repair=read('repair_result.json')
        lines += ['', '## Eksik günün ayrı sürümde tamamlanması','',
            f"İlk 2025-01-02 API çağrısı `(-1, Terminal: Call failed)` döndürmüştü. İlk hesapta kapalı alt toplamlar pozitifti; bu sonuçlar görülmüşken yalnız eksik veri onarımı için `repair_protocol_frozen.json` yazıldı. İlk manifest, rapor ve sonuçlar **attempt_01_incomplete/** içinde hashleriyle saklandı. Sıcak Ocak önbelleğinde yeniden sorgu {repair['rows']:,} quote verdi; diğer bütün günlerin manifest kayıtları ve strateji/gider kaynak hashleri aynı kaldı. Onarılan gün bir kaybeden işlemdir ve buradaki tam dönem toplamına dahil edildi. Bu işlem, sonuçlara göre gün eleme veya yeni OOS testi değildir."]
    lines += ['', '## Araştırma kararı','']
    if not result['gate']['passed']:
        lines += ['Bu tek model geliştirme kapısını geçmedi. Başlangıçta belirlenen politika gereği Temmuz–Ağustos rezervinde performans aranmadı; kapıyı geçmek için tarih, saat, stop/hedef veya filtre değiştirilmedi. Bu London FX/altın ORB araştırma kolu mevcut haliyle canlı adaylığından çıkarılır. Sonuç bütün ORB ailesinin her piyasada çalışamayacağını kanıtlamaz.']
        if primary['price_net_r_before_commission']<0:
            lines += ['', '1,5x senaryoda aynı dolumların komisyon öncesi toplamı da negatiftir. Varsayılan komisyonu sıfıra indirmek bu işlem yolunu kârlı hale getirmiyor; sorun yalnız sayısal altın tarifesinin belirsizliği değildir.']
    else:
        lines += ['Yalnız geliştirme kapısı geçti. Temmuz–Ağustos rezervi ayrı protokol/girdi ile, aynı kurallar korunarak değerlendirilmeli. 2025 komisyonu ve gerçek dolum/slippage belirsizliği çözülmeden canlıya geçiş yok.']
    available=[v for v in manifest['files'].values() if v['status']=='AVAILABLE'];total_ticks=sum(v['rows'] for v in available);zero=sum(v['rows']*v['zero_spread_fraction'] for v in available)/total_ticks if total_ticks else 0
    lines += ['', '## Tekrar üretim ve sınırlamalar','',
        f"- Toplam saklanan quote: {total_ticks:,}; ağırlıklı sıfır spread oranı %{zero*100:.2f}. Brokerın tarihsel sıfır spread kaydı gelecekte/gerçekte aynı dolum garantisi değildir.",
        f"- {len(checks)} dondurulmuş kaynak/referans hash’i ve kullanılan quote dosyaları başta/sonda doğrulandı. 9 odaklı test geçmişti; kurallar değiştirilmedi.",
        '- Bootstrap 10.000 dairesel 5 hafta içi gün bloğu, seed 173. Tek enstrüman ve görülmüş altı aylık örneklem; önceki strateji/piyasa seçimleri için çoklu deneme düzeltmesi içermez. Pozitif tarihsel toplam tek başına edge değildir.',
        '- İlk veri toplama girişimi disk yüzünden durmuştu. Bu devamda dış disk koruması kullanıldı; mevcut bağlı The5ers oturumuna yalnız tarihsel okuma yapıldı. Mevcut oturumun global otomatik işlem izni açıktı; bu çalışma onu veya başka çalışan botların ayarını değiştirmedi. Araştırma kaynaklarında order_send/order_check/position değiştirme çağrısı yok. Bu çalışmadan canlı/paper emir gönderilmedi.',
        '- `protocol_frozen.json`, `quote_manifest_frozen.json`, `clock_qa.json`, `native_qa.json`, `cost_evidence.json`, `outcomes.json`/CSV, `results.json`, `integrity_check.json` ve `report_diagnostics.json` delil zincirini içerir. Sonuçlar frozen_sources altında korunan tek model içindir.', '']
    (BASE/'SONUC.md').write_text('\n'.join(lines),encoding='utf8')
    status=read('execution_status.json');status.update(status='DEVELOPMENT_COMPLETE' if complete else 'DEVELOPMENT_INCOMPLETE_COVERAGE',test_executed=True,completed_utc=datetime.now(timezone.utc).isoformat(),reason=None if complete else 'unknown quote/native feature days',reserve_evaluated=result['reserve_evaluated'],orders_sent=False,free_bytes=shutil.disk_usage(BASE).free)
    (BASE/'execution_status.json').write_text(json.dumps(status,indent=2),encoding='utf8')
    print(json.dumps(dict(complete=complete,results=data,gate=result['gate']),indent=2))

if __name__=='__main__':main()
