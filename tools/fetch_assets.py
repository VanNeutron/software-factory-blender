"""Download the CC0 Poly Haven assets the scene uses into ../assets/polyhaven/.

    python3 tools/fetch_assets.py

About 650 MB. Standard library only. Re-running skips files that already exist.
All assets: https://polyhaven.com (CC0, no attribution required; credited in CREDITS.md anyway).
"""
import concurrent.futures as cf
import json
import os
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'polyhaven')
UA = {'User-Agent': 'software-factory-blender/1.0 (fetch_assets.py)'}

HDRI = ('belfast_sunset_puresky', '4k')
TEXTURES = ['aerial_grass_rock', 'asphalt_02', 'concrete_floor_worn_001', 'container_side', 'corrugated_iron_02',
            'dirty_concrete', 'garage_floor', 'gravel_ground_01', 'green_metal_rust', 'hangar_concrete_floor',
            'metal_plate', 'painted_metal_shutter', 'rusty_corrugated_iron', 'rusty_metal_02', 'rusty_metal_sheet',
            'sparse_grass', 'tarred_gravel', 'weathered_brown_planks', 'worn_corrugated_iron']
MODELS = ['Barrel_01', 'Barrel_02', 'cardboard_box_01', 'fir_tree_01', 'grass_medium_01',
          'industrial_pastic_container', 'metal_jerrycan', 'metal_tool_chest', 'metal_trash_can',
          'modular_chainlink_fence', 'nettle_plant', 'plastic_crate_01', 'plastic_crate_02', 'plastic_crate_03',
          'portable_welding_cart', 'shrub_02', 'shrub_04', 'tree_small_02', 'weed_plant_02', 'wooden_crate_01',
          'wooden_crate_02']
MAPS = ('Diffuse', 'nor_gl', 'Rough', 'Displacement', 'AO')


def api(path):
    with urllib.request.urlopen(urllib.request.Request('https://api.polyhaven.com/' + path, headers=UA)) as r:
        return json.load(r)


def jobs():
    out = []
    files = api('files/' + HDRI[0])
    u = files['hdri'][HDRI[1]]['exr']['url']
    out.append((u, os.path.join(ROOT, 'hdri', u.split('/')[-1])))
    for t in TEXTURES:
        files = api('files/' + t)
        for m in MAPS:
            if m in files and '2k' in files[m]:
                u = files[m]['2k']['jpg']['url']
                out.append((u, os.path.join(ROOT, 'textures', t, u.split('/')[-1])))
    for m in MODELS:
        b = api('files/' + m)['blend']['1k']['blend']
        out.append((b['url'], os.path.join(ROOT, 'models', m, f'{m}_1k.blend')))
        for rel, v in b.get('include', {}).items():
            out.append((v['url'], os.path.join(ROOT, 'models', m, rel)))
    return out


def fetch(job):
    url, path = job
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.part'
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r, open(tmp, 'wb') as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, path)
    return os.path.getsize(path)


if __name__ == '__main__':
    todo = jobs()
    with cf.ThreadPoolExecutor(8) as ex:
        total = sum(ex.map(fetch, todo))
    print(f'{len(todo)} files, {total / 1e6:.0f} MB downloaded to {os.path.normpath(ROOT)}')
