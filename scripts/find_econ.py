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

# Try searching events for econ-related series
r = httpx.get(f'{BASE}/series', params={'limit': 200, 'category': 'Economics'}, timeout=15)
print('series status:', r.status_code, '- keys:', list(r.json().keys())[:5])
ser = r.json().get('series', [])
print(f'econ series: {len(ser)}')
for s in ser[:10]:
    print(' ', s.get('ticker'), '|', s.get('title','')[:70])

# Also try high-volume events
print('\n--- events ---')
r = httpx.get(f'{BASE}/events', params={'status':'open','limit': 200}, timeout=15)
ev = r.json().get('events', [])
print(f'open events: {len(ev)}')
# print a sample
for e in ev[:8]:
    print(' ', e.get('event_ticker'), '|', (e.get('title') or '')[:70])
