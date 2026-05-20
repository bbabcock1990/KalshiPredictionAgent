import httpx
BASE = 'https://api.elections.kalshi.com/trade-api/v2'

def to_prob(d, base):
    v = d.get(f'{base}_dollars')
    if v not in (None, ''):
        try: return float(v)
        except: pass
    v = d.get(base)
    if v in (None, ''): return 0.0
    try: return float(v)/100.0
    except: return 0.0

# Query markets for known econ series
for series in ['KXCPIYOYBANK', 'KXFEDDECISION', 'KXCBDECISIONUS', 'KXUNEMPLOYMENT']:
    r = httpx.get(f'{BASE}/markets', params={'series_ticker':series,'status':'open','limit':100}, timeout=15)
    if r.status_code != 200:
        print(f'{series}: {r.status_code}'); continue
    ms = r.json().get('markets', [])
    print(f'\n=== {series}: {len(ms)} markets ===')
    for m in ms[:5]:
        bid = to_prob(m, 'yes_bid'); ask = to_prob(m, 'yes_ask')
        vol = int(float(m.get('volume_fp') or 0))
        print(f"  {m['ticker']:50s} bid={bid:.2f} ask={ask:.2f} vol={vol:>5} | {(m.get('title') or '')[:60]}")
