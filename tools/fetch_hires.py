#!/usr/bin/env python3
"""Download higher-resolution copies of the Poly Haven assets the scene already uses (CC0).

Reads what is in assets/polyhaven/ (2K tiling textures, 1K model blends, 4K sky) and fetches into
assets/polyhaven_hi/ with the same layout:  textures at 4K, model blends + their textures at 2K, sky at 16K and 8K.
The original folder is left untouched, so the scene can be switched back by pointing ROOT at it.
Usage: python3 tools/fetch_hires.py [--dry]
"""
import json, os, sys, urllib.request, concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'assets', 'polyhaven')
DST = os.path.join(HERE, '..', 'assets', 'polyhaven_hi')
TEX_RES, MODEL_RES, SKY_RES = '4k', '2k', ('16k', '8k')
UA = {'User-Agent': 'software-factory-blender/1.0'}


def api(path):
    with urllib.request.urlopen(urllib.request.Request('https://api.polyhaven.com' + path, headers=UA), timeout=60) as r:
        return json.load(r)


def walk_urls(node, res):
    """All {url,size} leaves under any '<res>' key."""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == res and isinstance(v, dict):
                for fmt in v.values():
                    if isinstance(fmt, dict) and 'url' in fmt:
                        out.append(fmt)
            else:
                out += walk_urls(v, res)
    return out


jobs, notes = [], []
# tiling textures: same maps and formats as the local 2K files
for t in sorted(os.listdir(os.path.join(SRC, 'textures'))):
    local = [f for f in os.listdir(os.path.join(SRC, 'textures', t)) if '_2k.' in f]
    want = {f.replace('_2k.', f'_{TEX_RES}.') for f in local}
    got = set()
    for leaf in walk_urls(api('/files/' + t), TEX_RES):
        name = leaf['url'].rsplit('/', 1)[-1]
        if name in want:
            jobs.append((leaf['url'], os.path.join(DST, 'textures', t, name), leaf.get('size', 0)))
            got.add(name)
    if want - got:
        notes.append(f'texture {t}: no {TEX_RES} for {sorted(want - got)}')
# models: the blend at MODEL_RES plus its included textures
for m in sorted(os.listdir(os.path.join(SRC, 'models'))):
    f = api('/files/' + m)
    b = f.get('blend', {})
    res = MODEL_RES if MODEL_RES in b else None
    if not res:
        notes.append(f'model {m}: no {MODEL_RES} blend (has {sorted(b)})')
        continue
    e = b[res]['blend']
    jobs.append((e['url'], os.path.join(DST, 'models', m, e['url'].rsplit('/', 1)[-1]), e.get('size', 0)))
    for rel, inc in e.get('include', {}).items():
        jobs.append((inc['url'], os.path.join(DST, 'models', m, rel), inc.get('size', 0)))
# sky
for s in os.listdir(os.path.join(SRC, 'hdri')):
    sid = s.rsplit('_', 1)[0]
    h = api('/files/' + sid).get('hdri', {})
    for res in SKY_RES:
        if res in h and 'exr' in h[res]:
            e = h[res]['exr']
            jobs.append((e['url'], os.path.join(DST, 'hdri_' + res, e['url'].rsplit('/', 1)[-1]), e.get('size', 0)))
        else:
            notes.append(f'sky {sid}: no {res} exr (has {sorted(h)})')

print(f'{len(jobs)} files, {sum(j[2] for j in jobs) / 1e6:.0f} MB')
for n in notes:
    print('NOTE', n)
if '--dry' in sys.argv:
    sys.exit(0)


def fetch(job):
    url, path, size = job
    if os.path.exists(path) and (not size or os.path.getsize(path) == size):
        return 'skip'
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600) as r, open(path + '.part', 'wb') as o:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            o.write(chunk)
    if size and os.path.getsize(path + '.part') != size:
        os.remove(path + '.part')
        return f'SIZE_MISMATCH {path}'
    os.replace(path + '.part', path)
    return 'ok'


with cf.ThreadPoolExecutor(8) as ex:
    res = list(ex.map(fetch, jobs))
bad = [r for r in res if r not in ('ok', 'skip')]
print('FETCH_DONE ok', res.count('ok'), 'skip', res.count('skip'), 'bad', len(bad))
for b in bad:
    print(b)
