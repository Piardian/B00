"""Summarize observed bottlenecks and declare one unexecuted follow-up."""
import study as s
import pandas as pd

def main():
    s.verify()
    coverage=s.read(s.HERE/'coverage.json');summary=s.read(s.HERE/'summary.json')
    p=s.read(s.HERE/'protocol.json')
    keys=list(coverage[0]['confirmation_diagnostics'])
    counts={k:sum(r['confirmation_diagnostics'][k] for r in coverage) for k in keys}
    byperiod={name:{k:sum(r['confirmation_diagnostics'][k] for r in coverage if r['month'] in months) for k in keys}
        for name,months in [('DEVELOPMENT',p['development']),('VALIDATION',p['validation'])]}
    s.write(s.HERE/'bottlenecks.json',dict(confirmation_checks=counts,periods=byperiod,
        interpretation='Checks are nested sweep/pool attempts, NOT unique trades. Volumes are reported by strict SFP but are not an independent veto in _detect_confirmed_sfp. IFVG absent in57/70 confirmation checks; this is a frequency bottleneck, NOT proof this filter destroys alpha. Original CE source guard rejected2 of10 structurally confirmed attempts.',
        caveat='Upstream rejection reasons (wick, pool, sweep, trend, trigger, body) not instrumented individually. No claim all lost opportunities would have been profitable.'))
    s.write(s.HERE/'next_hypothesis_predeclared.json',dict(
        status='DECLARED_NOT_EXECUTED',created_utc=str(pd.Timestamp.now(tz='UTC')),
        name='Is mandatory IFVG worth its lost opportunity frequency?',
        motivation='Baseline8signals/33assetmonths; only13of70 nested confirmation checks haveIFVG. No directional edge established. These are sample-generation diagnostics, not a profitable selection rule.',
        baseline='Byte-identical frozen baseline in protocol.json; original eight signals and observations retained.',
        research_variant='Only set USE_IFVG_ENTRY=False in an isolated research copy. REQUIRE_STRUCTURAL_BREAKER=True and REQUIRE_PRO_TREND_AAA=True remain. Use the existing calculate_ce_entry sweep-wick midpoint fallback, original asset stop buffer, TP1/TP2, session, TTL, universe. No invented entry implementation.',
        important='This flag also changes confirmation zone and CE entry geometry; it is a coupled EXISTING ENTRY MODEL comparison, NOT a pure filter-only ablation and NOT the unchanged live strategy. No outcome of the new variant has been generated or inspected.',
        sample=dict(symbols=s.SYMBOLS,development=p['development'],validation=p['validation'],
            classification='Fixed historical temporal comparison. Data and baseline outcomes previously seen; never call pristineOOS.'),
        unchanged='No TP/SL/TTL or asset/month/horizon search. Preserve fixed60min direction diagnostic; separately measure fills, time-to-fill and actual exit-side quote markouts with same cost/stress models. Missing prices remain unknown.',
        comparisons='Report perperiod signal frequency and direction CI; original strict candidates remain reference. Risks/entries may differ, so report both normalizedR and raw price movement and do not attribute changes solely to filter removal. Conditional filled markouts are not lifecyclePnL.',
        decision='No production change. More signals alone is not success. Full original lifecycle study requires resolved coverage and repeatable positive cost-aware postfill direction in both periods; uncertainty cannot be rescued by choosing a symbol/month. Otherwise stop this variant or identify a genuinely distinct hypothesis, not another parameter sweep.',
        baseline_protocol_sha256=s.sha(s.HERE/'protocol.json')))
    report=s.HERE/'REPORT.md'
    extra=['', '## Sinyal sayısını daraltan koşullar',
      '', f"Toplam {summary['coverage_totals']['expected_windows']} planlı tarama penceresi: {summary['coverage_totals']['missing_decision_bar']} pencerede tamamlanmış karar mumu yok; {summary['coverage_totals']['htf_unknown']} pencerede HTF nötr/hazır değil; {summary['coverage_totals']['scanned']} pencere gerçek SFP dedektörüne girdi.",
      '', 'Eksik160 pencere: üç varlıkta1Ocak, altında18Nisan. Bunlar hafta içi seans takvimi ile broker kapanışı arasındaki farktır; sıfır getirili işlem olarak sayılmadı. Diğer planlı karar mumları mevcut.',
      '', f"Yapı teyidine ulaşan {counts['structure_calls']} iç kontrol denemesinin {counts['breaker_pass']} tanesinde breaker, {counts['ifvg_pass']} tanesinde iFVG, {counts['both_pass']} tanesinde ikisi birlikte var. Bunlar farklı havuzları aynı mumda kontrol edebilen denemelerdir; benzersiz işlem adedi değildir. iFVG sinyal sıklığı açısından belirgin dar boğaz; kaldırılması kârlılığı artırır sonucu çıkmaz.",
      '', '10 ortak teyidin ikisi mevcut CE giriş kaynağı kontrolünü geçmedi; sekiz sinyal kaldı. Mevcut katı SFP yolunda hacim analizi çıktıya ekleniyor, ayrıca hacim veto şartı uygulanmıyor. Dolayısıyla önceki farklı hacim stratejisi raporları bu kolu kanıtlamaz.',
      '', '## Ölçümün pratik sonucu ve geliştirme',
      '', '1. Mevcut SFP için iki dönemde de pozitif bir saatlik sinyal-yön ortalaması bulunmadı. Sekiz örnek stratejiyi kesin reddetmeye de kanıtlamaya da yetmez.',
      '2. Kotasyonla üç dolumun60dk markoutu ölçülebildi; bir emir dört saatte dolmadı; dört sinyalin yeterli bid/ask arşivi yok. Pozitif altküme tüm sisteme genellenmedi. Bu aşamada TP/SL ayarı aramak için dayanak yok.',
      '3. Sonraki tek hipotez next_hypothesis_predeclared.json içinde kilitlendi: iFVG zorunluluğunun katkısını mevcut kodun kendi sweep-wick CE alternatifiyle karşılaştırmak. Bu yeni araştırma varyantıdır; henüz çalıştırılmadı. Bayrak hem teyidi hem giriş geometrisini etkilediğinden saf filtre testi diye sunulmayacak.',
      '', '## Doğrulama',
      '', '13 anlamlı birim testi geçti. Sekiz sinyal aynen yeniden üretildi; 41 prefix/gelecek-mutasyonu kontrolü geçti. 24 kotasyon senaryo kaydının muhasebesi ve kullanılan dört kotasyon dosyasının hashleri doğrulandı. Altında türetilen H1 barları örtüşen4614 doğal H1 barının OHLC değerleriyle birebir eşleşti.',
      '', 'protocol_initial.json ve study_initial.py, kotasyon sonucu görülmeden yapılan terminal-kapsam düzeltmesinin öncesini korur. integrity.json doğrulamayı; bottlenecks.json sayımları; next_hypothesis_predeclared.json sonraki deneyin sınırlarını içerir.']
    current=report.read_text(encoding='utf-8')
    if '## Sinyal sayısını daraltan koşullar' in current:raise RuntimeError('Already explained')
    report.write_text(current+'\n'.join(extra)+'\n',encoding='utf-8')
    s.write(s.HERE/'artifact_manifest.json',{p.name:s.sha(p) for p in s.HERE.glob('*') if p.is_file() and p.name not in ['artifact_manifest.json','run.log','run_errors.log']})
    print(counts)

if __name__=='__main__':main()
