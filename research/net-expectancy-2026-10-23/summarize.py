"""All predeclared variants, including missing-data failures and zero trades."""
from pathlib import Path
import json
import hashlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASELINE = {
    '2025-01': ROOT/'data/full_2025_study/january_completed_new_project_cost_1_5',
    '2025-11': ROOT/'data/full_2025_study/november_completed_new_project_cost_1_5',
}


def main():
    rows = []
    for variant in ['baseline','target_3r','half_structural_buffer','spread_risk_cap','target_grid_consistency']:
        for month in ['2025-01','2025-11']:
            folder = BASELINE[month] if variant == 'baseline' else HERE/'frozen_runs'/variant/month
            result_path = folder/'result.json'
            if result_path.exists():
                r = json.loads(result_path.read_text())
                if not r['complete_return_coverage']:
                    raise ValueError('Incomplete tracking cannot be compared as full month')
                closed = json.loads((folder/'state/closed.json').read_text()) if (folder/'state/closed.json').exists() else []
                row = dict(variant=variant,month=month,status='COMPLETED',n=r['closed_filled_trades'],
                           net_r=r['net_r'],weighted_net_r=r['weighted_net_r'],
                           stops=r['stop_losses'],wins=r['wins'],tp2=sum(t['close_reason']=='TP2_HIT' for t in closed),
                           result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest())
                if variant == 'half_structural_buffer':
                    for t in closed:
                        if 'research_original_risk' in t:
                            expected=(.08*1.5*t['research_original_risk']/t['risk_pips']) if t.get('filled_at') else 0.
                            assert abs(t['fee_r']-expected)<1e-6
            else:
                row=dict(variant=variant,month=month,status='INCOMPLETE_MISSING_GENUINE_MACRO',n=None,net_r=None)
            rows.append(row)
    diagnostics=json.loads((HERE/'candidate_quality_diagnostics.json').read_text())
    payload=dict(scope='EXIT_FILTER_RESEARCH_ON_ARCHIVED_BASELINE_NOT_CURRENT_CONCURRENT_LONDON_CHANGES',
                 cost_multiplier=1.5,real_broker_costs_verified=False,live_promotion_allowed=False,
                 validated_positive_edge_found=False,source_protocol='data/full_2025_study/validation_protocol_20261023_final/protocol.json',
                 variants=rows,quality_diagnostics=diagnostics,
                 experiment_sha256=hashlib.sha256((HERE/'experiment.py').read_bytes()).hexdigest())
    (HERE/'summary.json').write_text(json.dumps(payload,indent=2))
    labels={'baseline':'Referans','target_3r':'TP2 → 3R','half_structural_buffer':'Yapısal tampon yarım','spread_risk_cap':'Spread/stop ≤ %25','target_grid_consistency':'Hedef/fiyat adımı tutarlılığı'}
    lines=['# Net beklenti araştırması — ilk kontrollü deneyler', '',
           '23 Ekim 2026. TP/SL ve maliyet sorusu için önceki tam ay testinin dondurulmuş kaynakları kullanıldı. '
           'Çalışma sırasında ana klasörde London ORB/seans kodları değiştiği için farklı sürümlü ilk koşular karşılaştırmadan çıkarıldı. '
           'Bu rapor yeni London kodunun performans raporu değildir.', '',
           '**Maliyet sonrası pozitif ve doğrulanmış bir aday henüz yok.**', '',
           '| Deney | Ay | İşlem | Net R, 1.5x paper maliyet |', '|---|---|---:|---:|']
    for r in rows:
        lines.append(f'| {labels[r["variant"]]} | {r["month"]} | '+
                     (f'{r["n"]} | {r["net_r"]:+.6f} |' if r['net_r'] is not None else '— | Tamamlanmadı; eksik gerçek makro kararı |'))
    lines += ['', 'Sıfır işlem, kâr veya başarılı filtre kanıtı sayılmadı. Eksik ayın getirisi sıfır yazılmadı. '
              'Her deney önceden ilan edildi; sonuç gördükten sonra parametre araması yapılmadı.', '',
              '## Teşhis ve somut çıktı', '',
              '- TP2 uzatma tek başına bu ayları iyileştirmedi; işlemler hedefe varmadan çıkıyor. '
              'Stop tamponunu azaltmak, Ocak sonucunu kötüleştirdi. Mevcut yapı içinde stopu daraltmak daha az stop garantisi vermiyor.',
              '- Dar stop deneyi entry ve fiyat hedeflerini korur; yalnız mevcut yapının dışındaki tamponu yarıya indirir. '
              'Gider R, daralan stopa ters orantılı artırılarak aynı parasal masrafın yapay biçimde ucuzlaması önlenir.',
              '- 55 ham adayın 24ünde TP minimumu ile yuvarlanmış fiyatlar uyuşmuyor: 23 TP1, 1 TP2 kontrolünden geçemiyor. '
              'Örneğin EURUSD SHORT entry=1.0307, stop=1.0323, TP1=1.0288: hedef 1.2R yerine 1.1875R.',
              '- Araştırma tarafındaki price_rules.py giriş ve stopu koruyarak hedefleri son risk mesafesine göre hesaplar ve fiyat adımında dışa yuvarlar. '
              'Bu sayede seviye/trend kontrolünden geçen aday 15ten 25e çıkar. Bunlar ek işlem veya ek kâr değildir; makro, haber, dolum ve risk kapıları ayrıca çalışmalıdır.',
              '- Altının referans indeksinde 1040 uygun tarama penceresine rağmen aday yok; burada TP/SL ayarı denenebilecek işlem örneklemi oluşmamış.', '',
              '## Sınırlar ve sonraki çalışma', '',
              'Birinci teknik öncelik hedef/stop fiyat hesaplarının broker hassasiyeti ve minimum R/R ile tutarlılığıdır. '
              'Hesaplama düzeltmesi ayrı dosyada hazır ve altı test geçti; üretime bağlanmadı. '
              'Hedef tutarlılığı hipotezi tabloda ayrıca asıl motorla denendi; aday sayısı artışı doğrudan kazanç sayılmadı. '
              'Sonraki doğrulama daha geniş ve görülmemiş örneklemde, gerçek hesap maliyetleriyle yapılmalıdır. '
              'Yeni entry mekanizması oluşturulmadı, makro veto kaldırılmadı.', '',
              'İki ay daha önce görülmüş araştırma verisidir; örneklem dışı doğrulama değildir. '
              'Paper maliyetinin sabit R gideri ve fiyat oranlı spreadi gerçek hesap komisyonu, swap ve kayma doğrulaması değildir. '
              '[Güncel resmi maliyet açıklaması](https://the5ers.com/faqs/what-are-the-spreads-and-commissions/) '
              'Forex ve metal giderlerini ayrı tanımlar; güncel tarife 2025 hesabının tarifesi yerine geçirilmedi.', '',
              'Önemli kalibrasyon farkı: paper Forex spread eşiği entry×0.0002dir. EURUSD 1.03 örneğinde 2.06 pip, '
              '1.5x stresle 3.09 pip eder. Resmi sayfa normal koşullarda majörlerde 0.2–0.9 pip aralığını belirtir. '
              'Bu aralık her saat veya 2025 için gerçek spread kaydı değildir. Stres modelinde zarar görülmesi, '
              'gerçek hesap koşullarında avantajın kesin yokluğunu kanıtlamaz; sonraki öncelik bid/ask ve hesap giderlerini kalibre etmektir.', '',
              'Ücretli kullanım açılmadı. Bu deneyler canlı sürece uygulanmadı. '
              'protokol.json, summary.json ve candidate_quality_diagnostics.json tüm sonuçları ve hesaplama izini içerir.']
    (HERE/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'rows':len(rows),'completed':sum(r['status']=='COMPLETED' for r in rows),'positive_candidate_found':False}))


if __name__ == '__main__':
    main()
