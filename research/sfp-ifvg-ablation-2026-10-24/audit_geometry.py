"""Post-measurement price-grid audit. No level or outcome is changed."""
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
import run as r

def on_grid(value,step):
    units=Decimal(str(value))/Decimal(str(step))
    nearest=units.to_integral_value(rounding=ROUND_HALF_UP)
    return abs(units-nearest)<=Decimal('0.000001')

def main():
    m=r.measure();m.verify()
    fx=m.read(r.HERE/'quote_manifest_0_frozen.json')['symbol_specs']
    evidence=r.ROOT/'research/london-gold-2026-10-24/cost_evidence.json'
    gold=m.read(evidence)['symbol_spec']
    steps={s:fx[s]['trade_tick_size'] for s in ['EURUSD','GBPUSD']}
    steps['XAUUSD']=gold['trade_tick_size']
    assert steps=={'EURUSD':.00001,'GBPUSD':.00001,'XAUUSD':.01}
    assert on_grid(1.10001,.00001) and not on_grid(1.100005,.00001)
    assert on_grid(3000.01,.01) and not on_grid(3000.005,.01)
    output={}
    for name,path in [('REFERENCE',r.BASE/'signals.json'),('VARIANT',r.HERE/'signals.json')]:
        cases=m.read(path);rows=[]
        for c in cases:
            bad=[k for k in ['entry','stop_loss','tp1','tp2'] if not on_grid(c['signal'][k],steps[c['symbol']])]
            rows.append(dict(case_id=c['case_id'],symbol=c['symbol'],step=steps[c['symbol']],off_grid_fields=bad))
        output[name]=dict(total=len(cases),any_off_grid=sum(bool(v['off_grid_fields']) for v in rows),
            by_field={k:sum(k in v['off_grid_fields'] for v in rows) for k in ['entry','stop_loss','tp1','tp2']},
            by_symbol={s:dict(n=sum(v['symbol']==s for v in rows),off_grid_entry=sum(v['symbol']==s and 'entry' in v['off_grid_fields'] for v in rows)) for s in steps},
            details=rows)
    output['interpretation']='Diagnostic appended AFTER the frozen model comparison. No entries rounded, no outcomes rerun, no candidate removed. Broker2026 symbol specs, not independently archived2025 order acceptance. Off-grid nominal quote markouts are hypothetical price-level probes, NOT proof of an accepted executable limit. This arithmetic issue does not by itself establish or disprove directional alpha.'
    output['gold_symbol_spec_source_sha256']=m.sha(evidence)
    m.write(r.HERE/'price_grid_audit.json',output)
    summary=m.read(r.HERE/'summary.json')
    text=['','## Bulguların yorumu ve somut sonraki iş','',
        'iFVG şartını kaldırmak sinyal kıtlığını azalttı: 8 yerine57 sinyal. Referanstaki8 zamanın tamamı korunuyor;49 ek zaman oluşuyor. Bu, strateji edge kanıtı değil.',
        '', 'Geliştirme döneminde13 ölçülebilen dolumun gözlenen maliyetli60dk markoutu ortalama+0.00594R;1.5x maliyetle−0.00155R. Kontrolde4 dolum üç güne ait;1.5x ortalama+1.64063R. Geliştirme ve kontrol bu nedenle tekrarlanan bir avantaj göstermiyor. Bu markoutların beşinde ilk stop seviyesi bir saat dolmadan aşılmış; gerçek çıkış yönetimi olmadan bunlar işlem kârına çevrilemez.',
        '', '57 adayın17 dolumu ölçülebildi;11 emir dolmadı;29 adayın bid/ask kapsamı veya dolum+60dk sonu eksik. Dolayısıyla tüm örneklem için net kâr hesaplanmadı. Önceden kilitlenen30 dolum/15 gün/pozitif stresCI koşulları geçmedi; bu örneklemde örnek sayısı kapısını daha fazla ayar yaparak aşmak mümkün değil.',
        '', 'Altında yön puanı geliştirmede14 sinyalde+0.4431R, kontrolde8 sinyalde+0.1993R. Bu, deney sonrası görülen araştırma ipucudur; altın seçilip başarılı strateji ilan edilemez. Kotasyonla altın kontrolünde yalnızca bir dolum ölçülebildi ve bu kayıtta stop aşıldı. Forex tarafı aynı yön ölçümünü desteklemedi.',
        '', f"Ek icra denetimi: varyantta{output['VARIANT']['by_field']['entry']} giriş ve{output['VARIANT']['by_field']['stop_loss']} stop fiyatı broker fiyat adımına tam oturmuyor. Bu adımlar mevcut2026 broker metadatasından geliyor;2025 emir kabul kaydı değil. Seviyeleri sonuç lehine yuvarlamadık. Nominal limit markoutları broker tarafından kabul edilmiş emir kanıtı sayılamaz.",
        '', 'Sonraki somut geliştirme fiyat-adımı ve emir geometrisini araştırma katmanında deterministik hale getirmek; ardından eksik29 kotasyon aralığını tamamlamak. İkisinin de yeni protokolü olmalı; bu deneyin girişleri/sonuçları değiştirilmeyecek. Altın için görülen yön ipucu ancak kurallar değişmeden ayrı bir dönem ve tam stop/TP yaşam döngüsüyle sınanırsa ilerleyebilir. Yeni eşik veya TP/SL taraması önerilmiyor.',
        '', '19 birim testi geçti. Kod/gelecek-mutasyonu testleri araştırma uygulamasının doğruluğunu denetler; stratejinin kârını kanıtlamaz.']
    report=r.HERE/'REPORT.md';report.write_text(report.read_text(encoding='utf8')+'\n'.join(text)+'\n',encoding='utf8')
    m.write(r.HERE/'artifact_manifest.json',{str(p.relative_to(r.HERE)):m.sha(p) for p in r.HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in ['artifact_manifest.json','run.log','run_errors.log']})
    print({name:{k:v for k,v in output[name].items() if k!='details'} for name in ['REFERENCE','VARIANT']})

if __name__=='__main__':main()
