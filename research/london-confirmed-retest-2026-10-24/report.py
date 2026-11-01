from pathlib import Path
import json
import study

BASE=Path(__file__).resolve().parent
def main():
    result=json.loads((BASE/'results.json').read_text());data=result['results'];rows=json.loads((BASE/'outcomes.json').read_text())
    primary=data['primary']['COST_STRESS_1.5x'];ci=primary['block_total_ci95'];delta_ci=primary['paired_delta_ci95']
    old=study.read(study.PRIOR/'native_outcomes.json')+study.read(study.EXT/'outcomes.json')
    unknown={'BLOCKED_TAPE_COVERAGE','BLOCKED_FEATURE','BLOCKED_ENTRY_COVERAGE','UNPRICED_OPEN_POSITION','INVALID_ENTRY_GEOMETRY'}
    coverage={}
    for cohort in ['primary','control']:
        coverage[cohort]={}
        for scenario in data[cohort]:
            selected=[r for r in rows if r['scenario']==scenario and (cohort=='control' or r['rvol'] is not None and r['rvol']>=1)]
            bad={(r['symbol'],r['date']) for r in selected if r['outcome']['status'] in unknown}
            new_common=[r for r in selected if (r['symbol'],r['date']) not in bad]
            baseline=[r for r in old if r['scenario']==scenario and (cohort=='control' or r['rvol'] is not None and r['rvol']>=1) and (r['symbol'],r['date']) not in bad]
            comparison=study.summary(new_common,baseline)
            coverage[cohort][scenario]=dict(total_opportunity_days=len(selected),unknown_days=len(bad),common_days=len(new_common),
                common_known_net_r=comparison['net_r'],common_baseline_net_r=comparison['baseline_net_r'],
                common_delta_net_r=comparison['paired_delta_net_r'],common_delta_ci95=comparison['paired_delta_ci95'])
    study.save(BASE/'coverage_audit.json',coverage)
    lines=['# London ORB: kapanış + retest + M1 kırılım keşif denemesi','',
        '**Karar: '+('aday geliştirme kapısını geçti; ayrı doğrulama ve canlı onayı yok.' if result['gate']['passed'] else 'önceden belirlenen geliştirme kapısı geçilmedi; bu varyantta doğrulanmış edge yok.')+'**','',
        '**Kapsama eksik: iki parite-günde teyit sonrası 5 saniye içinde quote yok. Aşağıdaki R/PF değerleri yalnız çözümlenmiş kapalı işlemlerin alt toplamlarıdır; tam altı aylık sonuç değildir. Eksik günlere sıfır veya hayali dolum atanmadı.**' if not result['complete_coverage'] else 'Kapsama tam.', '',
        'Bu çalışma, kullanıcının izin verdiği sınırlı araştırma turundaki tek yeni giriş hipotezidir. Altı ayın sonuçları ve fiyat yolu teşhisi zaten görüldü. Dolayısıyla burada pozitif sonuç çıksa bile OOS/bağımsız doğrulama sayılmaz. Basit retest temasının kazananı kaybedenden ayırdığına dair teşhiste kanıt çıkmadı; bu çalışma onu başarılı kabul etmiyor. Mum kapanışıyla kırılım ve sonraki teyit, ayrı bir keşif hipotezidir.','',
        '## Sabit giriş kuralı','',
        '1. London yerel 08:00–08:15 doğal BID aralığı ve açılış yönü korunur. İlk tamamlanmış M1 mumunun bu yönde aralık dışında **kapanması** beklenir. İlk kırılım 08:15 mumundan itibaren olabilir.',
        '2. Kırılım mumu tamamlandıktan sonraki quote’larda fiyatın kırılan dış banda dönmesi beklenir. Kırılım mumundaki temas kullanılamaz.',
        '3. Retest mumundan sonraki tamamlanmış bir M1 mumu önceki tamamlanmış M1 tepe/dibini işlem yönünde kapanışla aşmalı ve açılış aralığının dışında kapanmalıdır. Bu, görsel swing seçiminin birebir taklidi değildir.',
        '4. Giriş, teyit kapanışından sonraki dakikanın ilk quote’unda (en fazla 5 saniye gecikmeyle), 12:00 London’dan kesin önce yapılır. Teyit mumunun tepe/dibi içinde geriye dönük dolum verilmez.',
        '5. İlk kapanış kırılımından girişe kadar karşı BID stop bandı bozulursa gün iptal olur; ikinci setup aranmaz. Her parite-günde tek deneme.',
        '6. Stop karşı BID bantta; hedef yeni giriş riskinden tam 2R; EOD 16:00 London. TP1/BE/trailing yok. Önceki doğrudan girişle aynı quote kaynağı ve gider varsayımları.', '',
        'Önceki negatif M1 teyit testleri orta bant/pasif limit adayları ve farklı yaşam döngülerindeydi. Bu denemede klasik dış aralık sınırı ve tam 2R çıkış kullanılır. Önceki sonuçlar silinmez ve farklı motorların R toplamları birleştirilmez.','',
        '## Altı aylık penceredeki bilinen kapalı işlemler','', '| Grup | Maliyet | Bilinen dolum | Bilinen net R | PF | Ortak çözümlenmiş günlerde doğrudan girişe fark |','|---|---|---:|---:|---:|---:|']
    for cohort,label in [('primary','RVOL ≥ 1'),('control','Hacim filtresiz kontrol')]:
        for scenario,v in data[cohort].items():
            pf=f"{v['pf']:.3f}" if v['pf'] is not None else '—'
            lines.append(f"| {label} | {scenario} | {v['fills']} | {v['net_r']:+.2f} | {pf} | {coverage[cohort][scenario]['common_delta_net_r']:+.2f} |")
    c=coverage['primary']['COST_STRESS_1.5x'];delta_ci=c['common_delta_ci95']
    lines += ['',f"Ana senaryo 1,5x: **{primary['fills']} bilinen kapalı işlemde {primary['net_r']:+.2f}R**. Toplam {c['total_opportunity_days']} uygun parite-günün {c['unknown_days']} tanesi çözümlenmedi. Yalnız ortak çözümlenmiş {c['common_days']} günde doğrudan girişe fark **{c['common_delta_net_r']:+.2f}R**; bu alt örneklem farkının %95 blok aralığı **[{delta_ci[0]:+.2f}, {delta_ci[1]:+.2f}]R**. Daha az zarar etmek pozitif edge değildir. İki girişte farklı ilk risk mesafeleri olduğundan fark dolar veya gerçek hesap getirisi değildir.",'',
        '`results.json` içindeki toplam CI ve ham paired_delta alanları bilinmeyen günlerin pozisyonları eksik olduğu için tam dönem doğrulamasında kullanılmaz. Bu rapordaki eşleştirme `coverage_audit.json` ile iki günde her iki politikayı da karşılaştırmadan çıkarır; bu seçilmiş alt örneklem de tam dönem yerine geçmez.','',
        '## Ana grubun aylık bilinen kapalı işlem alt toplamları','', '| Ay | 1x | 1,5x | 2x | En az 1 pip spread |','|---|---:|---:|---:|---:|']
    for month in data['primary']['OBSERVED_QUOTES_1x']['by_month']:
        lines.append('| '+month+' | '+' | '.join(f"{v['by_month'][month]:+.2f}" for v in data['primary'].values())+' |')
    lines += ['', 'Eylül ve Ekim alt toplamlarında birer bilinmeyen parite-gün vardır. Bu iki ay için tam aylık net getiri iddiası yok.','', '## Ana grup 1,5x: girişin oluşmama nedenleri','', '| Durum | Parite-gün |','|---|---:|---:|']
    for status,n in primary['statuses'].items():lines.append(f'| {status} | {n} |')
    lines += ['', '## Karar kapısı','', '| Kontrol | Sonuç |', '|---|---|']
    for key,passed in result['gate']['checks'].items():lines.append(f"| {key} | {'GEÇTİ' if passed else 'KALDI'} |")
    lines += ['', '## Sınırlar ve doğrulama','',
        f"- Kapsama: {'tam' if result['complete_coverage'] else 'EKSİK: kapalı işlem alt toplamı tam dönem sonucu değildir'}. İlk quote/EOD 5 saniye, seans içi boşluk 60 saniye; gerekli M1 BID barı yoksa bilinmeyen olarak bloklanır.",
        '- Gözlenen BID/ASK; 100 bin birim için tur başına 4 USD komisyon ve taraf başına 0,1 pip kayma varsayımı. Kişisel tarihsel hesap faturasıyla doğrulanmış değil. 1,5x/2x spread, komisyon ve kaymayı ağırlaştırır; en az 1 pip senaryosu max(gözlenen spread, 1 pip) kullanır. Kısa stop BID tetik/ASK çıkıştır; gerçek broker ASK stop emri değildir.',
        '- 11 odaklı test geçti: teyit sonrası giriş, aynı retest mumunda teyit yasağı, stop öncesi iptal, eksik dakika, 12:00 sınırı, kısa simetri, mevcut motorla EOD/TP/SL maliyet eşleşmesi, gap fiyatları ve salt okuma bağımlılıkları.',
        '- Kaynaklar ve kullanılan 780 quote dosyası başta/sonda SHA256 ile doğrulandı. Emir API çağrısı veya canlı/paper işlem yok. Üretim stratejisi ve çalışan süreçler değiştirilmedi.',
        '- Aynı gün bütün pariteler birlikte: 5 gözlenen iş günü blokları, 10.000 örnekleme, seed 173. Takvim blokları kesintilidir; çoklu araştırma düzeltmesi yok. R bağımsız fırsat toplamıdır; eşzamanlı risk, marjin, prop zarar sınırı veya hesap drawdown modeli değildir.', '',
        '## İki bilinmeyen girişin brokerdan tekrar kontrolü','',
        'The5ers terminalinden yalnız bu iki birer dakikalık pencere yeniden okundu. NZDUSD 2025-10-09 teyit 09:54:00 UTC: ilk quote 6,217 saniye sonra. USDCAD 2025-09-08 teyit 07:20:00 UTC: ilk quote 5,087 saniye sonra. Yeniden alınan pencereler dondurulmuş kayıtla birebir aynı (59 ve 111 quote); veri indirme hatası gösterilmedi. Bu, emirlerin gerçek dolumunu kanıtlamaz. Sabit 5 saniye kuralı gevşetilmedi; bilinmeyenler korundu. Ayrıntı `entry_coverage_verification.json`.', '',
        'Sonraki karar: bu varyant kapıyı geçmediyse bu turda eşik, saat, hedef veya parite seçerek kurtarılmayacak. Klasik London FX ORB ve bu teyit varyantı canlı adayı olarak rafa kalkar. Eksik kapsama nedeniyle tam dönem beklenen getirinin kesin olarak negatif olduğu da iddia edilmez; mevcut kanıt terfi için yetersizdir. Geçtiyse de önce ayrı, henüz bu giriş politikasıyla değerlendirilmemiş dönem protokolü gerekir.','',
        'Dosyalar: `protocol_frozen.json`, `outcomes.json` / `outcomes.csv`, `results.json`, `integrity_check.json`; kaynaklar `frozen_sources/` altında. Tekrar hesaplama: `python study.py run` (aynı klasörden).','']
    (BASE/'SONUC.md').write_text('\n'.join(lines),encoding='utf8')
    print(json.dumps(dict(primary=primary,gate=result['gate']),indent=2))

if __name__=='__main__':main()
