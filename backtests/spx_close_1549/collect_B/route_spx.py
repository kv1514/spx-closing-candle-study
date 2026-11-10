"""Route saved Robinhood SPX minute-bar tool results into raw/<date>/spx_1m.json
(date detected from the file content, not from call order) and report coverage + K0."""
import json, shutil, sys, os
from datetime import datetime, timezone, timedelta
RAW = '/Users/kv15/trading/data/spx_1549/robinhood/raw'
ET = timedelta(hours=-4)  # all chunk-B days are EDT

def bars_of(path):
    d = json.load(open(path))
    res = d['data']['results']
    assert len(res) == 1 and res[0]['symbol'] == 'SPX', path
    return res[0]['bars']

def route(paths):
    for p in paths:
        b = bars_of(p)
        dates = sorted({x['begins_at'][:10] for x in b})
        assert len(dates) == 1, (p, dates)
        dst = os.path.join(RAW, dates[0], 'spx_1m.json')
        if os.path.exists(dst):
            print('exists, not overwriting', dst); continue
        shutil.copyfile(p, dst); print(p.split('/')[-1], '->', dst)

def summary(day):
    b = bars_of(os.path.join(RAW, day, 'spx_1m.json'))
    by = {}
    for x in b:
        t = datetime.strptime(x['begins_at'], '%Y-%m-%dT%H:%M:%SZ') + ET
        by[t.strftime('%H:%M')] = x
    real = {k for k, v in by.items() if not v.get('interpolated')}
    need = [f'15:{m:02d}' for m in range(19, 60)]
    missing_1519 = [k for k in need if k not in real]
    o1549 = float(by['15:49']['open_value']) if '15:49' in real else None
    k0 = int(5 * round(o1549 / 5)) if o1549 else None
    return dict(date=day, n=len(b), n_interp=len(b) - len(real), first=min(by), last=max(by),
                real_1549=('15:49' in real), missing_1519_1559=missing_1519, open_1549=o1549, K0=k0)

if __name__ == '__main__':
    if sys.argv[1] == 'route':
        route(sys.argv[2:])
    else:
        for d in sys.argv[2:]:
            print(summary(d))
