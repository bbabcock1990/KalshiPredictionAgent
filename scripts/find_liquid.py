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

cursor = None
all_liquid = []
pages = 0
for _ in range(8):
    params = {'status':'open','limit':1000}
    if cursor: params['cursor'] = cursor
    r = httpx.get(f'{BASE}/markets', params=params, timeout=20)
    j = r.json()
    ms = j.get('markets', [])
    pages += 1
    for m in ms:
        if 'MVE' in (m.get('event_ticker') or '') or m.get('mve_collection_ticker'):
            continue
        bid = to_prob(m, 'yes_bid'); ask = to_prob(m, 'yes_ask')
        vol_raw = m.get('volume_fp') or m.get('volume') or 0
        try: vol = int(float(vol_raw))
        except: vol = 0
        if bid > 0 and ask > 0 and vol > 100:
            all_liquid.append((vol, bid, ask, m['ticker'], m.get('title','')[:70]))
    cursor = j.get('cursor')
    if not cursor or not ms:
        break

all_liquid.sort(reverse=True)
print(f"Pages={pages}  Total liquid binary markets: {len(all_liquid)}")
for vol, bid, ask, t, title in all_liquid[:15]:
    print(f"{t:55s} bid={bid:.2f} ask={ask:.2f} vol={vol:>7} | {title}")
