"""Route saved get_option_historicals tool results into raw/<D>/options_part{1,2,3}.json
(interval 'minute') or raw/<D>/options_10m_part{n}.json (interval '10minute'), identifying the
day/part by matching the returned instrument ids to raw/<D>/instruments.csv (rows 1-10, 11-20, 21-26).
Files that match no chunk-B group exactly are ignored (other agents' pulls)."""
import json, csv, os, sys, shutil
RAW = '/Users/kv15/trading/data/spx_1549/robinhood/raw'
DAYS = ['2026-09-21', '2026-09-22', '2026-09-23', '2026-09-24', '2026-09-25', '2026-09-28',
        '2026-09-29', '2026-09-30', '2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06']
groups = {}
for d in DAYS:
    ids = [r['id'] for r in csv.DictReader(open(os.path.join(RAW, d, 'instruments.csv')))]
    for i, g in enumerate([ids[:10], ids[10:20], ids[20:]], 1):
        groups[frozenset(g)] = (d, i)
for p in sys.argv[1:]:
    try:
        dat = json.load(open(p))
        res = dat['data']['results']
    except Exception as e:
        print('skip (unreadable)', p, e); continue
    key = frozenset(r['instrument_id'] for r in res)
    if key not in groups:
        continue
    d, i = groups[key]
    ivs = {r['interval'] for r in res}
    assert len(ivs) == 1, ivs
    iv = ivs.pop()
    days_in = {b['begins_at'][:10] for r in res for b in r['bars']}
    # minute files must cover exactly day d; 10-minute part-3 files were requested from d-3 so that
    # the result is large enough to be saved to a file (it then also holds earlier-day bars)
    if iv == 'minute':
        assert days_in == {d}, (p, days_in)
    else:
        assert d in days_in and max(days_in) == d, (p, days_in)
    assert not dat['data'].get('not_found'), dat['data'].get('not_found')
    name = {'minute': f'options_part{i}.json', '10minute': f'options_10m_part{i}.json'}[iv]
    dst = os.path.join(RAW, d, name)
    if os.path.exists(dst):
        print('exists', dst); continue
    shutil.copyfile(p, dst)
    nreal = sum(1 for r in res for b in r['bars'] if not b.get('interpolated'))
    print(os.path.basename(p)[-17:], '->', d, name, 'contracts', len(res), 'real bars', nreal)
