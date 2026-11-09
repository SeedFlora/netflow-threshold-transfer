"""Read-only primary metadata collection; no dataset or manuscript upload."""
import concurrent.futures
import json
from pathlib import Path
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parent
DOIS = {
    'P01': '10.1109/ACCESS.2026.3688204', 'P03': '10.3390/modelling6040165',
    'P04': '10.1016/j.ijcip.2026.100876', 'P05': '10.1371/journal.pone.0346801',
    'P07': '10.1007/978-3-030-72802-1_9', 'P08': '10.1007/s11036-021-01843-0',
    'P09': '10.1109/MilCIS.2015.7348942', 'P10': '10.1109/TNSM.2022.3157344',
    'P11': '10.1016/j.compeleceng.2023.108692', 'P13': '10.1109/SPW53761.2021.00009',
    'P15': '10.1109/EuroSP57164.2023.00042', 'P16': '10.33411/IJIST/1956',
    'P17': '10.1109/SP.2010.25', 'P18': '10.1145/357830.357849',
    'P20': '10.1371/journal.pone.0118432',
}

def fetch(item):
    pid, doi = item
    url = 'https://api.crossref.org/works/' + urllib.parse.quote(doi, safe='')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'LocalResearchAudit/1.0'})
        with urllib.request.urlopen(req, timeout=40) as response:
            message = json.load(response)['message']
        return pid, {'source': url, 'accessed': '2026-09-05', 'status': 'verified', 'metadata': message}
    except Exception as exc:
        return pid, {'source': url, 'accessed': '2026-09-05', 'status': 'not verified', 'error': str(exc)}

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        result = dict(pool.map(fetch, DOIS.items()))
    (ROOT / 'primary_metadata_crossref.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    for pid, result in sorted(result.items()):
        meta = result.get('metadata', {})
        print(pid, result['status'], json.dumps({key: meta.get(key) for key in ['title', 'author', 'published', 'container-title', 'volume', 'issue', 'page', 'article-number']}, ensure_ascii=True))
