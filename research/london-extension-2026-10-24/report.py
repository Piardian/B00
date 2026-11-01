"""Read completed frozen outcomes and publish a descriptive audit report."""
from pathlib import Path
import json, hashlib, csv
from collections import Counter

BASE = Path(__file__).resolve().parent
PRIOR = BASE.parent / 'london-quote-validation-2026-10-23'

def read(path):
    return json.loads(path.read_text(encoding='utf8'))

def main():
    results = read(BASE/'results.json')
    rows = read(BASE/'outcomes.json')
    declaration = read(BASE/'protocol_frozen.json')['declaration']
    integrity = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p,h in declaration['source_files'].items()}
    integrity['prior_outcomes'] = hashlib.sha256((PRIOR/'native_outcomes.json').read_bytes()).hexdigest() == declaration['prior_outcomes_sha256']
    assert all(integrity.values()), 'Frozen input changed'
    clock, native, manifest = [read(BASE/name) for name in ['clock_qa.json','native_qa.json','quote_manifest_frozen.json']]
    data = results['results']
    gates = {}
    for period in ['extension','combined']:
        primary = data[period]['CLASSIC_RVOL_GE1']
        checks = {
            'complete_coverage': results['complete_coverage'],
            'clock_qa': clock['passed'], 'native_qa': native['passed'],
            'frozen_source_integrity': all(integrity.values()),
            'at_least_100_primary_fills': primary['OBSERVED_QUOTES_1x']['fills'] >= 100,
            'positive_1_5x': primary['COST_STRESS_1.5x']['net_r'] > 0,
            'positive_2x': primary['COST_STRESS_2x']['net_r'] > 0,
            'positive_min_1pip': primary['MIN_SPREAD_1PIP']['net_r'] > 0,
            'observed_block_ci_lower_positive': primary['OBSERVED_QUOTES_1x']['block_total_ci95'][0] > 0,
        }
        gates[period] = dict(passed=all(checks.values()), checks=checks)
    (BASE/'gate_results.json').write_text(json.dumps(gates,indent=2),encoding='utf8')
    (BASE/'integrity_check.json').write_text(json.dumps(integrity,indent=2),encoding='utf8')
    flat = [{**{k:v for k,v in row.items() if k!='outcome'}, **row['outcome']} for row in rows]
    fields = sorted(set().union(*(r.keys() for r in flat)))
    with (BASE/'outcomes.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(flat)
    lines = ['# London ORB: dört yeni ay ve altı aylık birleşik denetim', '',
        '**Karar: ' + ('araştırma kapısı geçti; canlı edge onayı değildir.' if gates['extension']['passed'] and gates['combined']['passed'] else 'bu testte doğrulanmış edge yok; önceden belirlenen araştırma kapısı geçilmedi.') + '**', '',
        'Yeni dönemler sonuçlar görülmeden Nisan, Mayıs, Eylül ve Ekim 2025 olarak sabitlendi. Önceki Şubat–Mart korunarak altı aylık birleşim ayrıca hesaplandı. Altı majör: EURUSD, GBPUSD, USDJPY, USDCAD, USDCHF, NZDUSD. Tarihsel yeniden oynatma; gerçek ileri test veya bütün araştırma geçmişinden bağımsız OOS değildir.', '',
        '## Değişmeyen kurallar', '',
        'Londra yerel saatiyle 08:00–08:15 BID aralığı; açılış mumunun yönünde ilk kırılım; parite başına günde bir deneme; yeni giriş 12:00 öncesi. Stop karşı BID bantta sanal/yapısal tetik, hedef tam 2R, gün sonu çıkışı 16:00 Londra. Ana aday: ilk 15 dakika doğal broker BID tick hacmi / önceki 14 uygun gün ortalaması ≥ 1. Kontrol: aynı sistem, hacim filtresiz. Bu klasik araştırma modeli botun retest/M1 teyitli tüm üretim sistemiyle aynı değildir.', '',
        'Alış ASK, satış BID; uzun çıkış BID, kısa çıkış ASK. Komisyon 100 bin birim için tur başına 4 USD ve kayma taraf başına 0,1 pip varsayımıdır; tarihsel kişisel hesap faturasıyla doğrulanmış değildir. 1,5x/2x senaryoları gözlenen spreadi, kaymayı ve komisyonu ağırlaştırır; değişen spread çıkışları da etkileyebilir. 1 pip taban senaryosu max(gözlenen spread, 1 pip) kullanır. BID stopun özellikle kısa pozisyonda broker ASK stopuyla aynı olmadığı dikkate alınmalıdır.', '',
        '## Sonuçlar', '']
    for period,title in [('extension','Yalnız dört yeni ay'),('combined','Şubat–Mart dahil altı ay')]:
        lines += ['### '+title, '', '| Model | Maliyet | İşlem | Net R | PF | Kazanma |', '|---|---|---:|---:|---:|---:|']
        for cohort,label in [('CLASSIC_RVOL_GE1','RVOL ≥ 1'),('CLASSIC_ALL','Hacim filtresiz kontrol')]:
            for scenario,v in data[period][cohort].items():
                pf=f"{v['pf']:.3f}" if v['pf'] is not None else '—'
                lines.append(f"| {label} | {scenario} | {v['fills']} | {v['net_r']:+.2f} | {pf} | %{v['win_pct']:.1f} |")
        p=data[period]['CLASSIC_RVOL_GE1']['OBSERVED_QUOTES_1x']; ci=p['block_total_ci95']
        lines += ['', f"Ana adayın gözlenen maliyette toplam R için %95 blok bootstrap aralığı: **[{ci[0]:+.2f}, {ci[1]:+.2f}] R**. En iyi 5 işlemi çıkarınca: **{p['without_best5']:+.2f} R**. Bu çıkarma yalnız duyarlılık tanısıdır, bağımsız bir edge testi değildir.", '']
    lines += ['## Ana adayın aylık dağılımı', '', '| Ay | 1x | 1,5x | 2x | Min. 1 pip |', '|---|---:|---:|---:|---:|']
    primary=data['combined']['CLASSIC_RVOL_GE1']
    for month in primary['OBSERVED_QUOTES_1x']['by_month']:
        values=[v['by_month'][month] for v in primary.values()]
        lines.append('| '+month+' | '+' | '.join(f'{v:+.2f}' for v in values)+' |')
    lines += ['', '## Parite dağılımı (yeni dört ay, ana aday, 1,5x)', '', '| Parite | İşlem | Net R |', '|---|---:|---:|']
    for symbol in declaration['symbols']:
        closed=[r for r in rows if r['symbol']==symbol and r['scenario']=='COST_STRESS_1.5x' and r['rvol'] is not None and r['rvol']>=1 and r['outcome']['status']=='CLOSED']
        lines.append(f"| {symbol} | {len(closed)} | {sum(r['outcome']['net_r'] for r in closed):+.2f} |")
    lines += ['', 'Bu parite kırılımı sonuç sonrası betimlemedir. Zararlı pariteleri çıkararak yeni bir doğrulanmış portföy ilan edilmedi.', '',
        '## Bulguların anlamı', '',
        'Şubat–Mayıs pozitif, Eylül–Ekim negatiftir. Dört yeni ay gözlenen maliyette bile zarardadır; sorun yalnız ağır maliyet varsayımı değildir. Altı ayın gözlenen maliyetteki küçük artısı maliyet stresinde kaybolur ve güven aralığı sıfırı kapsar. RVOL filtresi kontrolün kaybını azaltmış görünür, ancak tek başına kalıcı pozitif beklenti kanıtı sağlamaz. Nedenin piyasa rejimi olduğu bu sonuçtan kanıtlanamaz.', '',
        'Bu haliyle klasik ORB + RVOL ≥ 1 adayı canlıya taşınmaz. Sonuç sonrası kötü ay/parite elemek veya eşiği kâra göre değiştirmek mevcut testi kurtarmak sayılmaz. Yeni giriş hipotezi araştırılacaksa ayrı protokol ve bu sonuçlardan bağımsız doğrulama gerektirir.', '', '## Veri, kontroller ve karar kapısı', '',
        f"- {len(manifest['files'])} parite-gün dosyası (ısınma dahil); doğal M15 hacim/tepe/dip/yön kontrolü {native['checked']} / {native['checked']} uyumlu.",
        f"- Bağımsız fiyat serisiyle saat kontrolü: {clock['strong_days']} güçlü gün, {len(clock['conflicts'])} saat çelişkisi. Dış veri yalnız saat kontrolünde kullanıldı; işlemler The5ers BID/ASK üzerinde hesaplandı.",
        f"- Kapsama durumu: {'tam' if results['complete_coverage'] else 'EKSİK; kapalı işlemlerin toplamı geçerli tam dönem sonucu sayılamaz'}. Açılış ve EOD fiyatına 5 saniye sınırı, içeride 60 saniye boşluk sınırı uygulandı.",
        '- Sabit kaynak hashleri yeniden doğrulandı. 14 odaklı test geçti. Hiçbir canlı/paper emir API çağrısı yapılmadı; üretim stratejisi bu genişletmede değiştirilmedi.',
        '- Aynı günün pariteleri birlikte toplanarak 5 gözlenen iş günlü dairesel bloklarla 10.000 örnekleme, seed 173. Ayrı takvim blokları birleşince sınırdaki bitişiklik gerçek kesintisiz takvim değildir. Güven aralığı araştırma boyunca denenmiş bütün stratejiler için çoklu deneme düzeltmesi içermez.', '',
        '| Kapı | Dört yeni ay | Altı ay birleşik |', '|---|---|---|']
    for key in gates['extension']['checks']:
        lines.append(f"| {key} | {'GEÇTİ' if gates['extension']['checks'][key] else 'KALDI'} | {'GEÇTİ' if gates['combined']['checks'][key] else 'KALDI'} |")
    lines += ['', 'R toplamları bağımsız fırsatların birim risk toplamıdır; gerçek hesap getirisi, eşzamanlı pozisyon/marjin sınırı, prop günlük zarar sınırı veya hesap drawdown ölçümü değildir. Quote kaydı emir dolum garantisi değildir. Önceki negatif mum/sentetik spread deneyleri bu farklı motorun toplamına eklenmedi; önceki araştırma sonuçları geçersiz sayılmadı.', '',
        '## Tekrar üretme', '',
        '`protocol_frozen.json`, `quote_manifest_frozen.json`, `native_qa.json`, `clock_qa.json`, `integrity_check.json` girdileri ve denetimi; `outcomes.json` / `outcomes.csv` yeni işlemleri; `results.json` yeni ve birleşik sonuçları; `gate_results.json` karar kapısını içerir. `extension.py replay` aynı hashlerle yeniden hesaplar (parite kontrol noktalarını kullanır). Kaynaklar `frozen_sources/` altında korunur.', '']
    (BASE/'SONUC.md').write_text('\n'.join(lines),encoding='utf8')
    print(json.dumps(dict(gates=gates, primary={p:data[p]['CLASSIC_RVOL_GE1'] for p in data}),indent=2))

if __name__=='__main__': main()
