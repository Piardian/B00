"""Publish completed month results from saved original-engine replay artifacts."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT/'data/full_2025_study'
SOURCES = {
    '2025-01': ['replay_attempts/20261023T064213/2025-01',
                'january_completed_new_project_cost_1_5', 'january_completed_new_project_cost_2'],
    '2025-11': ['replay_attempts/20261023T064501/2025-11',
                'november_completed_new_project_cost_1_5', 'november_completed_new_project_cost_2'],
}


def main():
    payload = {'status':'COMPLETED_CURRENT_ENGINE_PAPER_REPLAY', 'research_project_id':'101716527360',
               'primary_requested_month':'2025-01', 'additional_retrospective_month':'2025-11',
               'edge_proven':False, 'broker_costs_verified':False, 'untouched_oos_completed':False,
               'original_2025_macro_archive':False, 'paid_use_authorized':False, 'months':{}}
    lines = ['# Yeni araştırma anahtarıyla tamamlanan ay testleri — 23 Ekim 2026', '',
             'Yeni proje anahtarı gerçek makro çıktısı üretti. Ocak 2025 ve ek kontrol olarak Kasım 2025, '
             'asıl giriş ve işlem takip motoruyla ay sonuna kadar yeniden oynatıldı. Yeni entry mekanizması eklenmedi.', '',
             '**Sonuç: bu iki dönem pozitif ve kalıcı edge kanıtlamıyor.**', '',
             '| Dönem | Paper maliyet çarpanı | Dolmuş/kapanmış işlem | Net R | Makro risk çarpanlı net R |',
             '|---|---:|---:|---:|---:|']
    fingerprint = None
    for month, folders in SOURCES.items():
        payload['months'][month] = []
        for folder in folders:
            result_path = STUDY/folder/'result.json'
            r = json.loads(result_path.read_text())
            if r['status'] != 'REPLAY_COMPLETED' or not r['complete_return_coverage']:
                raise ValueError('Incomplete month cannot be published as completed: '+folder)
            if r['open_at_month_end'] or r['unresolved_gaps'] or r['unpriced_active_tails']:
                raise ValueError('Unresolved tracked position: '+folder)
            fingerprint = fingerprint or r['source_sha256']
            if r['source_sha256'] != fingerprint:
                raise ValueError('Strategy versions differ across scenarios')
            for name, digest in fingerprint.items():
                if hashlib.sha256((ROOT/'sfp_orb_engine'/f'{name}.py').read_bytes()).hexdigest() != digest:
                    raise ValueError('Current source differs: '+name)
            trades = json.loads((STUDY/folder/'state/closed.json').read_text())
            row = {'result_path':str(result_path.relative_to(ROOT)),
                   'result_sha256':hashlib.sha256(result_path.read_bytes()).hexdigest(),
                   'result':r, 'trades':trades}
            payload['months'][month].append(row)
            lines.append(f'| {month} | {r["friction_assumptions"]["multiplier"]:.1f}x | '
                         f'{r["closed_filled_trades"]} | {r["net_r"]:+.6f} | {r["weighted_net_r"]:+.6f} |')
    lines += ['', 'Ocakta üç gerçekleşmiş işlem EURUSD ORB; Kasımda tek gerçekleşmiş işlem EURUSD SFP/iFVG/Breaker. '
              'GBPUSD ve XAUUSD bu iki ayda dolmuş işlem üretmedi. Dört temel senaryo işlemi istatistiksel üstünlük göstermek için yeterli değildir. '
              '1.5x ve 2x aynı işlemlerin bağımsız tekrarları sayılmaz.', '',
              'Normal net R, eşit birim riskle işlem toplamıdır. Diğer sütun her işlemin makro risk çarpanını uygular; '
              'gerçek hesap yüzdesi veya gerçekleşmiş para getirisi değildir. Bu nedenle Ocak normal toplamı hafif negatifken risk çarpanlı toplam hafif pozitiftir.', '',
              '## Kapsam ve sınırlar', '',
              '- Aynı BegonyaEngine, SFP/ORB dedektörleri, makro/haber kapıları, risk frenleri ve passive-limit-v3 takipçisi kullanıldı. '
              'Tüm senaryolarda kaynak kod SHA256 değerleri aynı ve mevcut kaynaklarla eşleşiyor.',
              '- Makro çıktılar orijinal 2025 LLM arşivi değildir; gerçek tarihsel girdilerle güncel üretim grafiğinden yeniden üretildi. '
              'Yalnız olası girişlerin tükettiği görüntüler hesaplandı. Kullanılmayan ara analizlerin ardışık rejim durumu taşıması birebir modellenmedi. '
              'Dolayısıyla 2025 canlı davranışının birebir kanıtı veya makro motorunun bütün tarihsel akışının eksiksiz testi denemez.',
              '- Paper gideri sabit 0.08R, spread eşiği fiyat oranıdır; stres çarpanı ikisini de değiştirir. '
              'Böylece dolum zamanı ve kapanış da değişebilir. Gerçek bid/ask, hesaba ait tarihsel komisyon, swap ve kayma doğrulanmadı.',
              '- Her senaryoda ay sonunda açık işlem, çözülmemiş takip boşluğu ve fiyatlanmamış aktif kuyruk yok. '
              'Bu, veri dosyalarında piyasanın açık olduğu her dakikanın kesin mevcut olduğuna dair genel bir sertifika değildir.',
              '- Kasım 2025 eski varlık seçimi taramasına dahildi; görülmemiş örneklem dışı veri değildir. '
              '36 dosyalık protokolde kaydedilen gerçek ileri dönem Kasım 2026 henüz yaşanmadı.',
              '- Canlı paper süreç yeniden başlatılmadı; gerçek para emri verilmedi ve otomatik devam kurulmadı.', '',
              'Önceki kota engeli yeni projeyle aşıldı. API yanıtları ve gerçek karar dosyaları çalışma klasöründe korunuyor. '
              'Anahtar metni rapora eklenmedi.', '',
              '## Kaynak sonuç dosyaları', '']
    for month in payload['months'].values():
        for row in month:
            lines.append(f'- `{row["result_path"]}`; SHA256 `{row["result_sha256"]}`')
    target = STUDY/'completed_validation_new_project_20261023.json'
    target.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    (ROOT/'docs/COMPLETED_BACKTEST_2025_JAN_NOV_2026-10-23.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('Six completed scenarios reconciled; monthly paper results published; edge_proven=false.')


if __name__ == '__main__':
    main()
