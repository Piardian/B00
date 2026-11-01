from pathlib import Path
import json
import numpy as np

BASE=Path(__file__).resolve().parent
def main():
    results=json.loads((BASE/'results.json').read_text())
    paths=json.loads((BASE/'paths.json').read_text())
    p=results['COST_STRESS_1.5x']['primary'];s=p['stopped']
    lines=['# London ORB: girişten sonraki fiyat yolu denetimi','',
        '**Karar: çoğu stop işleminde korunacak büyük bir kâr oluşmamış. Basit bant teması da kazananı kaybedenden ayırmıyor. Yeni bir çıkış kuralının edge sağladığı gösterilmedi.**','',
        'Önceden görülmüş Şubat, Mart, Nisan, Mayıs, Eylül ve Ekim 2025; altı majör parite. Sabit ana grup RVOL ≥ 1, ana maliyet 1,5x. Hiçbir işlem sonucu, stop/hedef, gün veya parite değiştirilmedi. Bu, strateji testi değil geriye dönük betimleyici teşhistir.','',
        '## Ana grubun 254 işlemi (1,5x)','',
        '| Sonuç | İşlem |','|---|---:|']
    names={'TP2':'2R fiyat hedefine ulaşan','EOD_positive':'Gün sonunda net pozitif kapanan','SL_without_0.5netR':'Stop: öncesinde +0,5R nete ulaşmayan','SL_after_0.5netR':'Stop: öncesinde +0,5R nete ulaşan','EOD_nonpositive':'Gün sonunda net pozitif olmayan'}
    for key,n in p['categories'].items():lines.append(f'| {names[key]} | {n} |')
    lines += ['',f"156 stopun **99’u (%{99/156*100:.1f})** +0,5R net kâr görmedi. Stop işlemlerinde medyan en yüksek geçici net kâr yalnız **{s['median_mfe_net_r']:.3f}R**. Sadece **{s['reached']['1.0']}/156** stop öncesinde +1R nete ulaştı. Bu bulgu, sorunu yalnız TP1/BE ekleyerek çözebileceğimizi desteklemez; böyle bir kuralın kazananları ne kadar keseceği ayrıca nedensel replay gerektirir.",'',
        '| Grup | İşlem | Net R | Stop sayısı | Stop öncesi +0,5R net | Stop öncesi +1R net |','|---|---:|---:|---:|---:|---:|']
    for scenario,label in [('COST_STRESS_1.5x','1,5x'),('OBSERVED_QUOTES_1x','Gözlenen 1x')]:
        for cohort,title in [('primary','RVOL ≥ 1'),('control','Hacim filtresiz')]:
            r=results[scenario][cohort];a=r['all'];st=r['stopped']
            lines.append(f"| {title}, {label} | {a['n']} | {a['net_r']:+.2f} | {st['n']} | {st['reached']['0.5']} | {st['reached']['1.0']} |")
    lines += ['', '## Stopa gidiş süresi', '', '| Girişten sonra | Kümülatif stop |', '|---|---:|']
    for minutes,n in p['stopped_by_minutes'].items():lines.append(f'| ≤ {minutes} dakika | {n} / 156 |')
    lines += ['',f"Stop medyan süresi **{s['median_held_minutes']:.1f} dakika**; stopların yalnız 6’sı ilk 5 dakika içinde. Hepsini anlık sahte kırılım diye adlandırmak doğru olmaz.",'',
        '## Retest teması seçici mi?','',
        '254 işlemin tamamında çıkıştan önce fiyat kırılan BID bandının içine en az bir kez döndü. Kazanan 93/93 ve kaybeden 161/161 işlemde bu dönüş var. Bu olay, tamamlanmış mumla teyitli retest değildir; tek ticklik içeri dönüşü de sayar. Sonuç sonrası açıklayıcı süre kırılımı:','',
        '| Grup | İşlem | İlk içeri dönüş medyanı (saniye) | İlk 5 saniyede içeri dönüş |','|---|---:|---:|---:|']
    selected=[r for r in paths if r['primary'] and r['scenario']=='COST_STRESS_1.5x']
    for title,g in [('Tümü',selected),('Kazananlar',[r for r in selected if r['net_r']>0]),('Kaybedenler',[r for r in selected if r['net_r']<0])]:
        median=np.median([r['first_return_minutes']*60 for r in g]);count=sum(r['first_return_minutes']<=5/60 for r in g)
        lines.append(f'| {title} | {len(g)} | {median:.3f} | {count} |')
    lines += ['', 'Sadece temas beklemek için burada ayırt edici kanıt çıkmadı. Bu raporun protokolündeki basit retest gerekçesi kapısı karşılanmadı. Ayrı `london-confirmed-retest-2026-10-24` denemesi, bu bulguyla desteklendiği iddia edilen bir doğrulama değildir: kullanıcının izin verdiği sınırlı araştırma kapsamında, mum kapanışıyla anlamlı kırılımı tek tick temasından ayıran tek bir **keşif hipotezi** olarak ayrıca sabitlenmiştir. Eski negatif M1 sonuçları geçerliliğini korur.','',
        '## Stop sonrasını kâr saymadık','',
        f"Stop olan {s['n']} işlemin {p['stopped_then_target_later']} tanesinde fiyat aynı gün daha sonra orijinal hedef koşuluna ulaştı. Bu, stopu yok sayarak elde edilebilecek kâr değildir: aradaki risk ve kayıp yolu korunur. Bu sayıdan stop genişletme veya stop kaldırma kararı çıkarılamaz.",'',
        '## Hesaplama ve doğrulama','',
        '- MFE/MAE: girişten **gerçek çıkışa kadar**, o anda pozisyon kapatılsa oluşacak BID/ASK, varsayılan kayma ve tam tur komisyon sonrası net R uçları. Giriş tickindeki anlık geri kapama maliyeti dahil. Hedef çıkış tickinde olumlu gap kârı verilmez; kaydedilmiş hedef dolumu kullanılır.',
        '- MFE geçmiş yolun en iyi noktasıdır; önceden bilinen sinyal veya o fiyattan otomatik çıkış garantisi değildir. +0,5R eşiği optimizasyonla seçilmedi. Net eşikler, nominal 2R fiyat hedefiyle aynı şey değildir.',
        '- 701 ayrı quote dosyası üzerinde 1x ve 1,5x toplam 1.402 kapalı replay’in giriş/çıkış zamanı, fiyatı, risk, hedef, komisyon ve net sonucu eski motorla birebir eşleşti. Aynı milisaniyedeki kayıt sırası korundu. Kaynak ve kullanılan quote hashleri başta/sonda doğrulandı.',
        '- Altı odaklı test geçti: kısa ASK hedefi, hedef gap sınırı, aynı zaman damgası sırası, stop sonrasının ayrılması, komisyon ve referans değişiminin yakalanması.',
        '- MT5/veri indirme veya emir API çağrısı yok. Üretim kodu ve çalışan süreçler değiştirilmedi. R toplamları hesap getirisi değildir.', '',
        'Dosyalar: `protocol_frozen.json`, `paths.json`, `paths.csv`, `results.json`, `integrity_check.json`; kaynaklar `frozen_sources/` altında. Sonuç sonrası retest zaman kırılımı, temel protokoldeki kategorilere ek betimlemedir ve filtre olarak kullanılmadı.','']
    (BASE/'SONUC.md').write_text('\n'.join(lines),encoding='utf8')

if __name__=='__main__':main()
