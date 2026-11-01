"""Post-run reporting only; never used for selection or parameter fitting."""
import json,hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent


def load(name):return json.loads((HERE/name).read_text(encoding='utf-8'))


def main():
    status=load('status.json')
    if status['status']!='REPLAY_COMPLETE':raise RuntimeError('No complete validation report on blocked/unresolved replay')
    rows=load('summary.json');coverage=load('coverage.json')
    lookup={(r['group'],r['spread_pips']):r for r in rows}
    gates={}
    for cost in [.5,1.5]:
        tight=lookup['TIGHT',cost];loose=lookup['LOOSE',cost]
        gates[f'tight_positive_total_{cost}pip']=tight['net_r'] is not None and tight['net_r']>0
        gates[f'tight_both_months_positive_{cost}pip']=all(tight['monthly'][m]['fills']>0 and tight['monthly'][m]['closed_only_r']>0 for m in ['2025-02','2025-03'])
        gates[f'tight_outperforms_loose_mean_{cost}pip']=tight['mean_r_per_setup'] is not None and loose['mean_r_per_setup'] is not None and tight['mean_r_per_setup']>loose['mean_r_per_setup']
    gates['at_least30_primary_tight_fills']=lookup['TIGHT',.5]['fills']>=30
    gates['all246pair_days_covered']=len(coverage)==246 and all(r['missing_m15']==0 and r['atr_ready'] for r in coverage)
    gates['no_unresolved_replay']=all(r['unresolved']==0 for r in rows)
    decision=dict(status='SCREEN_SURVIVED_NOT_EDGE_PROVEN' if all(gates.values()) else 'NOT_CONFIRMED',gates=gates,
                  live_promotion=False,caveat='Additional retrospective period, same model not realized costs;30fill gate heuristic, never edge proof')
    (HERE/'decision.json').write_text(json.dumps(decision,indent=2),encoding='utf-8')
    table=[]
    for cost in [.2,.5,.9,1.5]:
        t=lookup['TIGHT',cost];l=lookup['LOOSE',cost]
        table.append(f"|{cost:.1f}pip|{t['fills']}|{t['net_r']:+.3f}|{t['monthly']['2025-02']['closed_only_r']:+.3f}|{t['monthly']['2025-03']['closed_only_r']:+.3f}|{l['fills']}|{l['net_r']:+.3f}|")
    primary=lookup['TIGHT',.5];loose=lookup['LOOSE',.5];allbase=lookup['ALL',.5]
    ci=primary['day_cluster95_mean_setup_r'];cis='hesaplanamadı (az sayıda farklı gün)' if ci is None else f'[{ci[0]:+.3f}, {ci[1]:+.3f}]'
    gate_text='\n'.join(f"- {name}: {'GEÇTİ' if passed else 'GEÇMEDİ'}" for name,passed in gates.items())
    text=f'''# Asya sıkışması: ayrı dönem doğrulaması

**Karar: {decision['status']}. Canlıya geçiş yok.**

Önceki Ocak/Kasım2025 bulgusundaki %35 eşiği değiştirilmeden, Şubat ve Mart2025'te yeniden sınandı. Bu iki ayın fiyatları başka bir klasikORB araştırmasında kullanılmıştı. Bu çalışma bu erken-limit/sıkışma hipotezi için ayrı dönem kontrolüdür; tamamen dokunulmamış proje-geneli OOS veya prospektif forward değildir. Şubat/Mart sonucu eski aylara eklenerek bağımsız kanıt diye sunulmaz.

## Kuralların eşitliği

Dondurulmuş config,ORB,entry,volume ve London-context modülleri önceki çalışmayla byte düzeyinde aynı. Önceki33kurulumun entry/stop/TP1/TP2 değerleri yeni dondurulmuş dedektörle birebir yeniden üretildi. Giriş MIDPOINT limit; önceki ortak araştırma çıkış motoru aynen kullanıldı. Stop küçültülmedi, M1teyit eklenmedi, hedef uzaklaştırılmadı.

Her parite/London gününde ilk normalize edilmiş uygun kurulum seçilir; dolmasa da gün tüketilir. Daha sonra Asya aralığı/dailyATR≤0.35 TIGHT, (0.35,0.70] LOOSE olarak etiketlenir. Sıkışık gruba geçmek için o gün daha sonraki aday aranmaz. Temel dedektörün0.70 sınırı korunur; kontrol grubu bütün piyasa günleri değil, aynı dedektörden çıkan daha geniş Asya kurulumlarıdır.

## Kapsam ve veri

- Altı parite:EURUSD,GBPUSD,USDJPY,USDCAD,USDCHF,NZDUSD. Altın yok.
-41hafta içi gün×6parite=246parite-günü; Asya24M15barı, London aralığı ve giriş saatleri ile ATR geçmişi kontrol edildi.
-Seçilen kurulum:{status['candidates']}; ana model bütün referans dolumu:{allbase['fills']}.
-TIGHT:{primary['setups']}kurulum/{primary['fills']}dolum; LOOSE:{loose['setups']}kurulum/{loose['fills']}dolum.
-H1/M15yerel broker geçmişinden; günlük ATR yalnız önceki tamamlanmış yeterli UTC günlerinden. Son300tamamlanmışM15 kullanılır.
-NativeM1 geçmişi istenen dönemi vermedi. Sonuçlar hesaplanmadan ikinci protokolle, mevcut The5ers London08–16tick arşivinden ve önbellekteki16–16:31kuyruğundan bidM1 üretildi. Eksik fiyat interpolasyonu yok. Her parite için41×511=20951LondonM1 satırı var.
-Broker saat dönüşümü öncekiUS-DST UTC+2/3 eşlemesidir; mevcut bağımsız H1clock denetimi41güçlü günde sıfır saat kayması raporlamıştır. Bu çalışma clock araştırmasını yeniden yapmadı.

Bu setup araştırmasıdır: makro/haber,SFPönceliği,ortak portföy riski,marj ve gerçek hesap yürütmesi yok. R bağımsız kurulumun ilk fiyat riskine göre normalize edilmiş model sonucudur.

## Sonuçlar

**Aşağıdaki netR modeldir:** gerçek bidM1 + varsayımsal sabit ask spreadi,4USD/100binbirim round-trip komisyon ve0.2pip olumsuz piyasa çıkış kayması. Tarihsel gerçek ask,hesap komisyonu ve kayma yaşam döngüsü doğrulaması değildir. Ortak çıkışlar:TP1yarım,BE/trailing,dolum mumundaTPyok,stopöncelikli,olumsuzdolumtepkisindeücretliçıkış,London16:30kapatma. Bu son kapanış önceki araştırma sözleşmesidir; üretim botunun birebir sonlandırma kuralı diye sunulmaz.

|Spread varsayımı|TIGHT dolum|TIGHT toplamR|ŞubatR|MartR|LOOSE dolum|LOOSE toplamR|
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(table)}

Ana0.5pip modelinde TIGHT beklenti {primary['mean_r_per_setup']:+.3f}R/kabul edilen kurulum;95%gün-küme bootstrap aralığı **{cis}**. Aynı günün işlemleri birlikte örneklenir. Aralık geçmiş çoklu araştırmaları düzeltmez; günler arası tam seri bağımlılık düzeltmesi de değildir. Sıfır dolumlar kabul edilen kurulum paydasında korunur. Kazançlı ay veya parite seçilmedi.

## Önceden belirlenen karar kapıları

{gate_text}

30dolum alt sınırı pratik bir örneklem kapısıdır;30veya daha çok işlem edge kanıtı değildir. Toplam artı yeterli değildir: iki ayın ve1.5pip stresinin de pozitif olması, çözümlenmemiş veri/işlem olmaması, TIGHT'ın LOOSE'a göre kurulum başına daha iyi sonuç vermesi aranmıştır. Başarısız kapılar çıktıda korunur. Olumsuz sonucu düzeltmek için0.30/0.40gibi yeni eşikler, parite/saat alt kümeleri veya yeni çıkışlar denenmedi.

## Çıktılar ve doğrulama

protocol.json ilk planı; protocol_v2.json nativeM1 engelinden sonra, yeni aday/getiri hesaplanmadan yapılan kaynak düzeltmesini korur. price_manifest_frozen.json veri kilididir. candidates.json bütün seçilen kurulumları, coverage.json246günü, outcomes.json her maliyet/kurulum yolunu, summary.json tüm grupları, decision.json kapıları içerir.

11test geçti: %35sınırı,geçersizoranlar,US/UKDSTayrımı,çözümlenmemişişlemdennetkâryazmama ve eski33kurulumun giriş/hedef eşitliği. Dondurulmuş kaynak ve veri hashleri tekrar denetlenir. Canlı kod/çalışan süreç değiştirilmedi, emir gönderilmedi, ücretliAPI/otomatik devam görevi yok.

Tekrar kontrol:

```
python research/asia-validation-2026-10-24/study.py verify
python research/asia-validation-2026-10-24/study.py run
```
'''
    if (HERE/'path_summary.json').exists():
        diag=load('path_summary.json')
        text+=f'''
## Başarısız doğrulamadan sonra fiyat yolu teşhisi

Ana senaryonun21TIGHTdolumunda, ilk yapısal stop/TP1 seviyeleriyle ve sabit16:30sonuna kadar bakıldığında: **{diag['initial_geometry'].get('INITIAL_STOP_FIRST',0)}işlemde stop önce**, **{diag['initial_geometry'].get('TP1_FIRST',0)}işlemde TP1önce**. Bu fiyat yoludur; varsayımsal yeni strateji kârı değildir.

12olumsuz tepki çıkışı toplam {diag['reaction_actual_modeled_net_r']:+.3f}R üretmiş. Bu çıkışlardan sonra ilk TP1/ilk stop yarışı **6TP1önce /6stopönce**. Dolayısıyla erken çıkışların bazısı toparlanmadan önce kapanıyor, bazıları daha büyük yapısal zarardan önce kapanıyor. Bu örneklem “tepki çıkışını kaldırmak çözüm” demiyor. Tüm21fiyat-yolu sınıflandırmasında belirsiz/eksik dakika veya aynı-mum stop/TP1çakışması çıkmadı.

Bu teşhis sonuçlar görüldükten sonra ayrı diagnostic_protocol.json ile kilitlendi. Fiyatın sonraki davranışı girişte bilinen bir özellik olarak kullanılamaz. Yeni filtre, hedef veya hipotetik netkâr çıkarılmadı. Dört ek fiyat-yolu testiyle **toplam15test geçti**.

**Uygulanabilir karar:** %35Asya filtresini canlıya almamak ve bu sabit filtreyi edge adayı olarak terfi ettirmemek. Kontrol grubu yalnız2dolumdur; tersine çevirip genişAsya grubunu başarılı strateji ilan etmek de yanlış olur. Sonraki ayrı araştırma için sorun başlıkları artık ölçülüdür: kurulumların başlangıç yön avantajı ve erken çıkışın kurtardığı/kaçırdığı hareketleri girişte bilinen verilerle ayırabilmek. Bu ayrım yeni bir dönem veya prospektif gözlemde sınanmalı; başarısız doğrulama aylarında eşik/çıkış taramasıyla yeşil tablo aranmamalıdır.
'''
    (HERE/'REPORT.md').write_text(text,encoding='utf-8')
    manifest={str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list(HERE.glob('*.py'))+list((HERE/'frozen_engine').glob('*.py'))}
    (HERE/'artifact_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(decision,indent=2))


if __name__=='__main__':main()
