"""Photo-scanned materials, plants, props and sky from Poly Haven (CC0) for the Software Factory scene.

Used by build_factory.py. Assets live in ../assets/polyhaven/ (see CREDITS.md).
All image textures use box (tri-planar) projection on object coordinates in metres,
so no UV unwrapping is needed: every scene object is built at the world origin.
"""
import bpy, math, os, glob, random
from mathutils import Vector

_BASE = os.path.normpath(os.path.join(os.environ.get('FACTORY_DIR') or (os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd()), '..', 'assets'))
# High-resolution set (tools/fetch_hires.py: 4K surfaces, 2K props/plants, 16K/8K sky) is used when present.
# Set FACTORY_ASSETS=std to force the original set (2K / 1K / 4K sky); FACTORY_SKY=8k|16k picks the sky.
HI = os.path.isdir(os.path.join(_BASE, 'polyhaven_hi', 'textures')) and os.environ.get('FACTORY_ASSETS', 'hi') != 'std'
ROOT = os.path.join(_BASE, 'polyhaven_hi' if HI else 'polyhaven')
TEX_RES = '4k' if HI else '2k'
SKY_DIR = ('hdri_' + os.environ.get('FACTORY_SKY', '16k')) if HI else 'hdri'
print("ASSETS", "hi" if HI else "std", TEX_RES, SKY_DIR)
# real-world tile size (m) of each texture, from the Poly Haven API
DIM = {'asphalt_02': 3.0, 'tarred_gravel': 2.2, 'concrete_floor_worn_001': 3.0, 'dirty_concrete': 3.0,
       'worn_corrugated_iron': 1.8, 'rusty_corrugated_iron': 2.0, 'corrugated_iron_02': 2.7, 'container_side': 1.94,
       'rusty_metal_02': 1.0, 'green_metal_rust': 1.0, 'rusty_metal_sheet': 2.0, 'sparse_grass': 2.0,
       'aerial_grass_rock': 15.0, 'gravel_ground_01': 3.0, 'painted_metal_shutter': 2.0, 'metal_plate': 0.5}


def have_assets():
    return os.path.isdir(os.path.join(ROOT, 'textures')) and os.path.isdir(os.path.join(ROOT, 'models'))

# --------------------------------------------------------------------------
# node helpers
# --------------------------------------------------------------------------

def _f(t, kind):
    hits = glob.glob(os.path.join(ROOT, 'textures', t, f'{t}_{kind}_{TEX_RES}.*'))
    return hits[0] if hits else None


def _img(path, data):
    im = bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = 'Non-Color' if data else 'sRGB'
    return im


class L:
    """One texture layer: color, roughness, normal (vector), height."""
    def __init__(self, color, rough, normal, height):
        self.color, self.rough, self.normal, self.height = color, rough, normal, height


def new_mat(name):
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(b.outputs[0], out.inputs[0])
    return m, nt, b


def coords(nt):
    tc = nt.nodes.new('ShaderNodeTexCoord')
    return tc.outputs['Object']


def mapping(nt, vec, size, rot=0.0, off=(0, 0, 0)):
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (1 / size, 1 / size, 1 / size)
    mp.inputs['Rotation'].default_value = (0, 0, rot)
    mp.inputs['Location'].default_value = off
    nt.links.new(vec, mp.inputs['Vector'])
    return mp.outputs[0]


def sample(nt, t, vec, size, rot=0.0, off=(0, 0, 0), blend=0.25):
    v = mapping(nt, vec, size, rot, off)
    out = {}
    for kind, data in (('diff', False), ('rough', True), ('nor_gl', True), ('disp', True)):
        p = _f(t, kind)
        if not p:
            out[kind] = None
            continue
        n = nt.nodes.new('ShaderNodeTexImage')
        n.image = _img(p, data)
        n.projection = 'BOX'
        n.projection_blend = blend
        n.interpolation = 'Cubic' if kind == 'disp' else 'Linear'
        nt.links.new(v, n.inputs['Vector'])
        out[kind] = n.outputs['Color']
    nm = None
    if out['nor_gl']:
        nmn = nt.nodes.new('ShaderNodeNormalMap')
        nmn.inputs['Strength'].default_value = 1.0
        nt.links.new(out['nor_gl'], nmn.inputs['Color'])
        nm = nmn.outputs[0]
    rough = out['rough']
    return L(out['diff'], rough, nm, out['disp'])


def mixc(nt, a, b, fac, kind='RGBA'):
    """Mix two sockets (or constants); kind RGBA / FLOAT / VECTOR."""
    m = nt.nodes.new('ShaderNodeMix')
    m.data_type = kind
    m.clamp_factor = True
    idx = {'FLOAT': (2, 3, 0), 'VECTOR': (4, 5, 1), 'RGBA': (6, 7, 2)}[kind]
    if isinstance(fac, (int, float)):
        m.inputs['Factor'].default_value = fac
    else:
        nt.links.new(fac, m.inputs['Factor'])
    for i, v in zip(idx[:2], (a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = v
        elif isinstance(v, tuple):
            m.inputs[i].default_value = (*v, 1) if kind == 'RGBA' else v
        else:
            nt.links.new(v, m.inputs[i])
    return m.outputs[idx[2]]


def math_(nt, op, a, b=None, clamp=False):
    m = nt.nodes.new('ShaderNodeMath')
    m.operation = op
    m.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = v
        else:
            nt.links.new(v, m.inputs[i])
    return m.outputs[0]


def noise(nt, vec, scale, detail=6, rough=0.6):
    n = nt.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail
    n.inputs['Roughness'].default_value = rough
    nt.links.new(vec, n.inputs['Vector'])
    return n.outputs['Fac']


def ramp(nt, src, a, b, ca=(0, 0, 0), cb=(1, 1, 1)):
    r = nt.nodes.new('ShaderNodeValToRGB')
    e = r.color_ramp.elements
    e[0].position, e[0].color = a, (*ca, 1)
    e[1].position, e[1].color = b, (*cb, 1)
    nt.links.new(src, r.inputs[0])
    return r.outputs[0]


def hsv(nt, col, h=0.5, s=1.0, v=1.0):
    n = nt.nodes.new('ShaderNodeHueSaturation')
    n.inputs['Hue'].default_value = h
    n.inputs['Saturation'].default_value = s
    n.inputs['Value'].default_value = v
    nt.links.new(col, n.inputs['Color'])
    return n.outputs[0]


def to_bw(nt, col):
    n = nt.nodes.new('ShaderNodeRGBToBW')
    nt.links.new(col, n.inputs[0])
    return n.outputs[0]


def blend_layers(nt, a, b, fac):
    return L(mixc(nt, a.color, b.color, fac),
             mixc(nt, to_bw(nt, a.rough) if a.rough else 0.6, to_bw(nt, b.rough) if b.rough else 0.6, fac, 'FLOAT'),
             mixc(nt, a.normal, b.normal, fac, 'VECTOR') if (a.normal and b.normal) else (a.normal or b.normal),
             mixc(nt, to_bw(nt, a.height) if a.height else 0.5, to_bw(nt, b.height) if b.height else 0.5, fac, 'FLOAT'))


def anti_tile(nt, t, vec, size, mask_scale=0.07):
    """Two samples of the same texture at different rotation/offset, blended by world noise: hides repeats."""
    a = sample(nt, t, vec, size)
    b = sample(nt, t, vec, size * 1.37, rot=0.9, off=(0.31, 0.57, 0.11))
    m = ramp(nt, noise(nt, vec, mask_scale, 3, 0.5), 0.42, 0.58)
    return blend_layers(nt, a, b, to_bw(nt, m))


def finish(nt, b, lay, rough_mul=1.0, rough_add=0.0, bump=0.4, bump_dist=0.03, macro=0.25, vec=None, metallic=0.0):
    col = lay.color
    if vec is not None and macro > 0:
        mv = ramp(nt, noise(nt, vec, 0.05, 4, 0.5), 0.3, 0.7, (1 - macro,) * 3, (1 + macro * 0.4,) * 3)
        col = _mul(nt, col, mv)
    nt.links.new(col, b.inputs['Base Color'])
    r = lay.rough
    if r is not None and not isinstance(r, (int, float)):
        r = to_bw(nt, r) if r.type == 'RGBA' else r
        r = math_(nt, 'ADD', math_(nt, 'MULTIPLY', r, rough_mul), rough_add, clamp=True)
        nt.links.new(r, b.inputs['Roughness'])
    else:
        b.inputs['Roughness'].default_value = 0.6 * rough_mul + rough_add
    nrm = lay.normal
    if lay.height is not None and bump > 0:
        bp = nt.nodes.new('ShaderNodeBump')
        bp.inputs['Strength'].default_value = bump
        bp.inputs['Distance'].default_value = bump_dist
        h = lay.height
        h = to_bw(nt, h) if getattr(h, 'type', '') == 'RGBA' else h
        nt.links.new(h, bp.inputs['Height'])
        if nrm is not None:
            nt.links.new(nrm, bp.inputs['Normal'])
        nrm = bp.outputs[0]
    if nrm is not None:
        nt.links.new(nrm, b.inputs['Normal'])
    if isinstance(metallic, (int, float)):
        b.inputs['Metallic'].default_value = metallic
    else:
        nt.links.new(metallic, b.inputs['Metallic'])


def _mul(nt, a, b):
    m = nt.nodes.new('ShaderNodeMix')
    m.data_type = 'RGBA'
    m.blend_type = 'MULTIPLY'
    m.inputs['Factor'].default_value = 1.0
    nt.links.new(a, m.inputs[6])
    nt.links.new(b, m.inputs[7])
    return m.outputs[2]


def streaks(nt, vec, strength=0.6):
    """Vertical rain/dirt streaks plus a dark splash zone near the ground. Returns a 0..1 dirt mask."""
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (2.5, 2.5, 0.1)
    nt.links.new(vec, mp.inputs['Vector'])
    s = to_bw(nt, ramp(nt, noise(nt, mp.outputs[0], 1.4, 5, 0.55), 0.48, 0.78))
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(vec, sep.inputs[0])
    low = math_(nt, 'POWER', math_(nt, 'SUBTRACT', 1.0, math_(nt, 'DIVIDE', sep.outputs[2], 3.0), clamp=True), 2.0)
    return math_(nt, 'MAXIMUM', math_(nt, 'MULTIPLY', s, strength), math_(nt, 'MULTIPLY', low, 0.6), clamp=True)


def dirty(nt, lay, mask, col=(0.045, 0.04, 0.032), amount=0.8):
    lay.color = mixc(nt, lay.color, mixc(nt, lay.color, col, 0.8), math_(nt, 'MULTIPLY', mask, amount, clamp=True))
    return lay

# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------

def m_asphalt():
    m, nt, b = new_mat("PH_Asphalt")
    v = coords(nt)
    a = anti_tile(nt, 'asphalt_02', v, DIM['asphalt_02'])
    g = anti_tile(nt, 'tarred_gravel', v, DIM['tarred_gravel'])
    patch = to_bw(nt, ramp(nt, noise(nt, v, 0.035, 5, 0.6), 0.5, 0.62))
    lay = blend_layers(nt, a, g, patch)
    # sparse puddles in clusters: low-freq cluster mask x mid-freq blobs
    cl = to_bw(nt, ramp(nt, noise(nt, v, 0.012, 2, 0.5), 0.55, 0.7))
    bl = to_bw(nt, ramp(nt, noise(nt, v, 0.11, 4, 0.55), 0.6, 0.64))
    pud = math_(nt, 'MULTIPLY', cl, bl, clamp=True)
    wet = math_(nt, 'MULTIPLY', cl, to_bw(nt, ramp(nt, noise(nt, v, 0.11, 4, 0.55), 0.5, 0.62)), clamp=True)
    lay.color = mixc(nt, lay.color, _mul(nt, lay.color, ramp(nt, wet, 0, 1, (1, 1, 1), (0.45, 0.45, 0.45))), 1.0)
    rough = mixc(nt, math_(nt, 'MULTIPLY', lay.rough, 1.0), 0.03, pud, 'FLOAT')
    rough = math_(nt, 'MULTIPLY', rough, math_(nt, 'SUBTRACT', 1.0, math_(nt, 'MULTIPLY', wet, 0.45)), clamp=True)
    lay.rough = rough
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    lay.normal = mixc(nt, lay.normal, geo.outputs['Normal'], pud, 'VECTOR')
    lay.height = mixc(nt, lay.height, 0.5, pud, 'FLOAT')
    lay.color = hsv(nt, lay.color, 0.5, 0.6, 0.42)
    finish(nt, b, lay, bump=0.35, bump_dist=0.02, vec=v, macro=0.3)
    return m


def m_concrete(name="PH_Concrete", floor=False, darker=1.0):
    m, nt, b = new_mat(name)
    v = coords(nt)
    a = anti_tile(nt, 'concrete_floor_worn_001', v, DIM['concrete_floor_worn_001'])
    d = anti_tile(nt, 'dirty_concrete', v, DIM['dirty_concrete'])
    lay = blend_layers(nt, a, d, to_bw(nt, ramp(nt, noise(nt, v, 0.06, 5, 0.6), 0.4, 0.65)))
    lay.color = hsv(nt, lay.color, 0.5, 0.8, darker * 0.72)
    if not floor:
        lay = dirty(nt, lay, streaks(nt, v, 0.55))
    finish(nt, b, lay, rough_mul=0.55 if floor else 1.0, rough_add=0.0, bump=0.3, vec=v, macro=0.2)
    return m


def m_cladding():
    m, nt, b = new_mat("PH_Cladding")
    v = coords(nt)
    a = sample(nt, 'worn_corrugated_iron', v, DIM['worn_corrugated_iron'], blend=0.1)
    r = sample(nt, 'rusty_corrugated_iron', v, DIM['rusty_corrugated_iron'], blend=0.1)
    s = streaks(nt, v, 0.7)
    rmask = math_(nt, 'MAXIMUM', to_bw(nt, ramp(nt, noise(nt, v, 0.25, 6, 0.65), 0.58, 0.7)), math_(nt, 'MULTIPLY', s, 0.55), clamp=True)
    lay = blend_layers(nt, a, r, rmask)
    lay.color = hsv(nt, lay.color, 0.5, 0.85, 0.62)
    lay = dirty(nt, lay, s, amount=0.5)
    finish(nt, b, lay, bump=0.6, bump_dist=0.04, vec=v, macro=0.15,
           metallic=math_(nt, 'MULTIPLY', math_(nt, 'SUBTRACT', 1.0, rmask), 0.6))
    return m


def m_simple(name, t, size, h=0.5, s=1.0, val=1.0, metallic=0.0, streak=0.4, rough_mul=1.0, bump=0.4):
    m, nt, b = new_mat(name)
    v = coords(nt)
    lay = sample(nt, t, v, size)
    if (h, s, val) != (0.5, 1.0, 1.0):
        lay.color = hsv(nt, lay.color, h, s, val)
    if streak > 0:
        lay = dirty(nt, lay, streaks(nt, v, streak), amount=0.6)
    finish(nt, b, lay, rough_mul=rough_mul, bump=bump, vec=v, macro=0.12, metallic=metallic)
    return m


def m_ground():
    m, nt, b = new_mat("PH_Ground")
    v = coords(nt)
    g = anti_tile(nt, 'sparse_grass', v, DIM['sparse_grass'])
    gr = anti_tile(nt, 'gravel_ground_01', v, DIM['gravel_ground_01'])
    near = blend_layers(nt, g, gr, to_bw(nt, ramp(nt, noise(nt, v, 0.04, 5, 0.6), 0.58, 0.7)))
    far = sample(nt, 'aerial_grass_rock', v, DIM['aerial_grass_rock'])
    # distance from the site centre -> far texture beyond ~120 m
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(v, sep.inputs[0])
    dx = math_(nt, 'SUBTRACT', sep.outputs[0], 8.0)
    dist = math_(nt, 'SQRT', math_(nt, 'ADD', math_(nt, 'MULTIPLY', dx, dx), math_(nt, 'MULTIPLY', sep.outputs[1], sep.outputs[1])))
    fac = math_(nt, 'DIVIDE', math_(nt, 'SUBTRACT', dist, 110.0), 80.0, clamp=True)
    lay = blend_layers(nt, near, far, fac)
    lay.color = hsv(nt, lay.color, 0.49, 0.9, 0.5)   # late-summer, slightly dry
    finish(nt, b, lay, bump=0.4, vec=v, macro=0.35)
    return m


def pbr_materials(M):
    """Replace the procedural materials in M with photo-scanned ones (same keys)."""
    if not have_assets():
        return M
    M['asphalt'] = m_asphalt()
    M['concrete'] = m_concrete()
    M['concrete_dark'] = m_concrete("PH_ConcreteDark", darker=0.55)
    M['floor'] = m_concrete("PH_Floor", floor=True, darker=0.85)
    M['cladding'] = m_cladding()
    M['roof'] = m_simple("PH_Roof", 'corrugated_iron_02', DIM['corrugated_iron_02'], val=0.7, metallic=0.6, streak=0.3, bump=0.6)
    M['galv'] = m_simple("PH_Galv", 'rusty_metal_sheet', DIM['rusty_metal_sheet'], metallic=0.7, streak=0.5, bump=0.3)
    M['server'] = m_simple("PH_Server", 'container_side', DIM['container_side'], h=0.12, s=0.25, val=0.35, metallic=0.4, streak=0.4, bump=0.5)
    M['crane'] = m_simple("PH_Crane", 'green_metal_rust', DIM['green_metal_rust'] * 2, h=0.33, s=1.4, val=1.3, metallic=0.2, streak=0.4, bump=0.3)
    M['steel'] = m_simple("PH_Steel", 'rusty_metal_02', DIM['rusty_metal_02'] * 2, s=0.6, val=0.22, metallic=0.6, streak=0.2, bump=0.3)
    M['shutter'] = m_simple("PH_Shutter", 'painted_metal_shutter', DIM['painted_metal_shutter'], val=0.6, metallic=0.4, streak=0.5)
    M['field'] = m_ground()
    return M

# --------------------------------------------------------------------------
# world: HDRI sky
# --------------------------------------------------------------------------

def hdri_world(target_az_deg=338.0, strength=1.0):
    """Use the Belfast sunset sky. Rotates it so its sun sits at target azimuth (deg, from +Y toward +X).
    Returns (sun_elevation_deg, sun_azimuth_deg)."""
    import numpy as np
    p = glob.glob(os.path.join(ROOT, SKY_DIR, '*.exr'))[0]
    im = bpy.data.images.load(p, check_existing=True)
    w, h = im.size
    px = np.empty(w * h * 4, dtype=np.float32)
    im.pixels.foreach_get(px)
    lum = px.reshape(h, w, 4)[..., :3].sum(axis=2)
    y, x = np.unravel_index(int(np.argmax(lum)), lum.shape)
    # equirect: u=x/w, v=y/h (Blender pixels start bottom row)
    u, vv = (x + 0.5) / w, (y + 0.5) / h
    elev = (vv - 0.5) * 180.0
    # Blender equirect: u=0.5 looks along -Y? direction = (-cos(phi)... ) -> azimuth in Blender world frame
    phi = (u - 0.5) * 2 * math.pi           # angle around Z, 0 = +X axis, counter-clockwise
    dir_x, dir_y = math.cos(-phi), math.sin(-phi)
    src_az = math.degrees(math.atan2(dir_x, dir_y))   # from +Y toward +X
    rot = math.radians(target_az_deg - src_az)
    scn = bpy.context.scene
    wd = scn.world or bpy.data.worlds.new("World")
    scn.world = wd
    wd.use_nodes = True
    nt = wd.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Rotation'].default_value = (0, 0, rot)
    env = nt.nodes.new('ShaderNodeTexEnvironment')
    env.image = im
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = strength
    out = nt.nodes.new('ShaderNodeOutputWorld')
    nt.links.new(tc.outputs['Generated'], mp.inputs['Vector'])
    nt.links.new(mp.outputs[0], env.inputs['Vector'])
    nt.links.new(env.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    return elev, target_az_deg, float(lum.max()), (int(x), int(y), w, h), src_az

# --------------------------------------------------------------------------
# asset libraries: append each Poly Haven blend into its own excluded collection
# --------------------------------------------------------------------------

def upgrade_model_textures():
    """Point the 1K textures of the imported Poly Haven models at the 2K files of the high-res set (same
    meshes and UVs, so the images are swapped in place). Returns (swapped, missing)."""
    if not HI:
        return (0, 0)
    n = miss = 0
    for im in bpy.data.images:
        fp = im.filepath.replace('\\', '/')
        if '/polyhaven/models/' not in fp or '_1k.' not in fp:
            continue
        rel = fp.split('/polyhaven/models/', 1)[1].replace('_1k.', '_2k.')
        new = os.path.join(ROOT, 'models', *rel.split('/'))
        if os.path.exists(new):
            im.filepath = new
            im.reload()
            n += 1
        else:
            miss += 1
            print("NO_2K", rel)
    return (n, miss)

def load_asset(name):
    cname = f"PH_{name}"
    c = bpy.data.collections.get(cname)
    if c and len(c.all_objects):
        return c
    path = glob.glob(os.path.join(ROOT, 'models', name, '*.blend'))[0]
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = list(src.objects)
    lib = bpy.data.collections.get("PH_Library")
    if lib is None:
        lib = bpy.data.collections.new("PH_Library")
        bpy.context.scene.collection.children.link(lib)
    c = c or bpy.data.collections.new(cname)
    if c.name not in lib.children:
        lib.children.link(c)
    for o in dst.objects:
        if o is None or o.type not in ('MESH', 'EMPTY'):
            continue
        c.objects.link(o)
    # exclude the library from the view layer (instances still render)
    lc = bpy.context.view_layer.layer_collection.children.get("PH_Library")
    if lc:
        lc.exclude = True
    return c


RULES = {
    'grass_medium_01': (r'^grass_medium_01_(large|mid|small|tall)_[a-c]_LOD1$', 'each'),
    'shrub_04': (r'_LOD0$', 'each'), 'shrub_02': (r'_LOD0$', 'each'),
    'nettle_plant': (r'_LOD0$', 'each'), 'weed_plant_02': (r'_LOD0$', 'each'),
    'fir_tree_01': (r'^fir_tree_01_[abc]_LOD1$', 'each'),
    'tree_small_02': (r'^tree_small_02_LOD1$', 'each'),
    'metal_tool_chest': (r'^metal_tool_chest', 'one'),
    'metal_trash_can': (r'^metal_trash_can_rust', 'one'),
    'wooden_crate_01': (r'^wooden_crate_01', 'one'),
}


def variants(name, pattern=None, mode=None, tag=''):
    """Collections of renderable parts of an asset, each with an instance offset at its base centre."""
    import re
    c = load_asset(name)
    pat, md = RULES.get(name, (r'.*', 'one'))
    pat, md = pattern or pat, mode or md
    objs = sorted([o for o in c.objects if o.type == 'MESH' and re.search(pat, o.name)], key=lambda o: o.name)
    groups = [[o] for o in objs] if md == 'each' else [objs]
    out = []
    for i, grp in enumerate(groups):
        vn = f"PHV_{name}{tag}_{i}"
        vc = bpy.data.collections.get(vn)
        if vc is None:
            vc = bpy.data.collections.new(vn)
            bpy.data.collections["PH_Library"].children.link(vc)
            pts = []
            for o in grp:
                vc.objects.link(o)
                pts += [o.matrix_world @ Vector(c_) for c_ in o.bound_box]
            vc.instance_offset = (sum(p.x for p in pts) / len(pts), sum(p.y for p in pts) / len(pts), min(p.z for p in pts))
        out.append(vc)
    return out


def place(vc, loc, rotz=0.0, scale=1.0, coll=None, name=None):
    e = bpy.data.objects.new(name or f"I_{vc.name}", None)
    e.instance_type = 'COLLECTION'
    e.instance_collection = vc
    e.location = loc
    e.rotation_euler = (0, 0, rotz)
    e.scale = (scale, scale, scale)
    (coll or bpy.context.scene.collection).objects.link(e)
    return e

# --------------------------------------------------------------------------
# grass scatter (geometry nodes)
# --------------------------------------------------------------------------

def grass_node_group(name, coll, density, scale_lo, scale_hi, patch_scale=0.05, seed=0):
    ng = bpy.data.node_groups.get(name)
    if ng:
        bpy.data.node_groups.remove(ng)
    ng = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    ng.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    N, Lk = ng.nodes, ng.links
    gi, go = N.new('NodeGroupInput'), N.new('NodeGroupOutput')
    dist = N.new('GeometryNodeDistributePointsOnFaces')
    dist.distribute_method = 'RANDOM'
    dist.inputs['Seed'].default_value = seed
    pos = N.new('GeometryNodeInputPosition')
    nz = N.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = patch_scale
    nz.inputs['Detail'].default_value = 3
    Lk.new(pos.outputs[0], nz.inputs['Vector'])
    rp = N.new('ShaderNodeValToRGB')
    rp.color_ramp.elements[0].position = 0.35
    rp.color_ramp.elements[1].position = 0.65
    Lk.new(nz.outputs['Fac'], rp.inputs[0])
    mul = N.new('ShaderNodeMath')
    mul.operation = 'MULTIPLY'
    mul.inputs[1].default_value = density
    Lk.new(rp.outputs[0], mul.inputs[0])
    Lk.new(gi.outputs[0], dist.inputs['Mesh'])
    Lk.new(mul.outputs[0], dist.inputs['Density'])
    ci = N.new('GeometryNodeCollectionInfo')
    ci.inputs['Collection'].default_value = coll
    ci.inputs['Separate Children'].default_value = True
    ci.inputs['Reset Children'].default_value = True
    iop = N.new('GeometryNodeInstanceOnPoints')
    iop.inputs['Pick Instance'].default_value = True
    rr = N.new('FunctionNodeRandomValue')
    rr.data_type = 'FLOAT_VECTOR'
    rr.inputs['Min'].default_value = (0, 0, 0)
    rr.inputs['Max'].default_value = (0, 0, 6.283)
    rs = N.new('FunctionNodeRandomValue')
    rs.data_type = 'FLOAT'
    rs.inputs['Min'].default_value = scale_lo
    rs.inputs['Max'].default_value = scale_hi
    rs.inputs['Seed'].default_value = seed + 7
    ri = N.new('FunctionNodeRandomValue')
    ri.data_type = 'INT'
    ri.inputs['Min'].default_value = 0
    ri.inputs['Max'].default_value = 999
    ri.inputs['Seed'].default_value = seed + 3
    Lk.new(dist.outputs['Points'], iop.inputs['Points'])
    Lk.new(ci.outputs[0], iop.inputs['Instance'])
    Lk.new(ri.outputs[0], iop.inputs['Instance Index'])
    Lk.new(rr.outputs[0], iop.inputs['Rotation'])
    Lk.new(rs.outputs[0], iop.inputs['Scale'])
    Lk.new(iop.outputs[0], go.inputs[0])
    return ng


def emitter_mesh(name, cells, coll):
    """cells: list of (x0, y0, size) squares at z=0.03."""
    verts, faces = [], []
    for x0, y0, s in cells:
        i = len(verts)
        verts += [(x0, y0, 0.03), (x0 + s, y0, 0.03), (x0 + s, y0 + s, 0.03), (x0, y0 + s, 0.03)]
        faces.append((i, i + 1, i + 2, i + 3))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def allowed(x, y):
    if -43 < x < 57 and -32 < y < 32:                # site
        return False

    if -50 < y < -34:                                # highway + verge
        return False
    if -16 < x < -4 and y < -30:                      # access road
        return False
    return True


def tree_ok(x, y):
    """allowed(), minus a clearing along the camera's final pullback (keeps the poster view out of the trees)."""
    if not allowed(x, y):
        return False
    px, py, qx, qy = 40.0, -40.0, 66.0, -70.0
    t = max(0.0, min(1.0, ((x - px) * (qx - px) + (y - py) * (qy - py)) / ((qx - px) ** 2 + (qy - py) ** 2)))
    return math.hypot(x - (px + t * (qx - px)), y - (py + t * (qy - py))) >= 16.0


def build_vegetation(coll, seed=3):
    rnd = random.Random(seed)
    grass = []
    grass += variants('grass_medium_01')
    gc = bpy.data.collections.get("PH_GrassMix") or bpy.data.collections.new("PH_GrassMix")
    if gc.name not in bpy.data.collections["PH_Library"].children:
        bpy.data.collections["PH_Library"].children.link(gc)
    for vc in grass:
        for o in vc.objects:
            if o.parent is None and o.name not in gc.objects:
                gc.objects.link(o)
    # near ring (dense) and far ring (sparse)
    near, far = [], []
    cx, cy = 8.0, 0.0
    for gx in range(-180, 240, 3):
        for gy in range(-200, 230, 3):
            if not allowed(gx + 1.5, gy + 1.5):
                continue
            d = math.hypot(gx - cx, gy - cy)
            if d < 70:
                near.append((gx, gy, 3))
            elif d < 230:
                far.append((gx, gy, 3))
    en = emitter_mesh("GrassNear", near, coll)
    ef = emitter_mesh("GrassFar", far, coll)
    for ob, nm, dens, lo, hi, sd in ((en, "GN_GrassNear", 20.0, 2.2, 4.5, 1), (ef, "GN_GrassFar", 5.0, 3.0, 5.5, 2)):
        md = ob.modifiers.new("Scatter", 'NODES')
        md.node_group = grass_node_group(nm, gc, dens, lo, hi, seed=sd)
    # shrubs and weeds along the site edge and building bases
    shrubs = variants('shrub_04') + variants('shrub_02')
    weeds = variants('nettle_plant') + variants('weed_plant_02')
    for k in range(260):
        side = rnd.random()
        if side < 0.3:
            x, y = rnd.uniform(-44, 58), rnd.choice((-33.5, 33.5)) + rnd.uniform(-1.5, 1.5)
        elif side < 0.5:
            x, y = rnd.choice((-44.5, 58.5)) + rnd.uniform(-1.5, 1.5), rnd.uniform(-33, 33)
        else:
            a = rnd.uniform(0, 6.283)
            r = rnd.uniform(36, 140)
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        if not allowed(x, y) and side >= 0.5:
            continue
        if -50 < y < -34 or (-16 < x < -4 and y < -30):
            continue
        place(rnd.choice(shrubs), (x, y, 0), rnd.uniform(0, 6.28), rnd.uniform(1.2, 2.6), coll)
    # weeds pushing through the cracks at the slab and curb edges
    for k in range(220):
        e = rnd.random()
        if e < 0.5:
            x, y = rnd.uniform(-36, 30), rnd.choice((-17.15, 17.15))
        elif e < 0.7:
            x, y = rnd.choice((-36.15, 30.15)), rnd.uniform(-17, 17)
        else:
            x, y = rnd.uniform(-40.5, 54.5), rnd.choice((-29.8, 29.8))
        place(rnd.choice(weeds), (x, y, 0.02), rnd.uniform(0, 6.28), rnd.uniform(0.8, 1.6), coll)
    # tree lines: firs and broadleaf, clumped, behind the site
    trees = variants('fir_tree_01') + variants('tree_small_02')
    n = 0
    while n < 1100:
        a = rnd.uniform(math.radians(40), math.radians(260))
        r = rnd.uniform(110, 520) if n > 120 else rnd.uniform(70, 120)
        x0, y0 = cx + r * math.cos(a), r * math.sin(a)
        if not allowed(x0, y0):
            continue
        for j in range(rnd.randint(4, 12)):
            vc = rnd.choice(trees)
            s = rnd.uniform(0.8, 1.3) if 'fir' in vc.name else rnd.uniform(2.2, 3.4)
            x, y = x0 + rnd.uniform(-10, 10), y0 + rnd.uniform(-10, 10)
            n += 1
            if tree_ok(x, y):
                place(vc, (x, y, 0), rnd.uniform(0, 6.28), s, coll)
    # tree belt closing the south and east sides (the orbit looks that way): dense near ring, thinner behind
    m = 0
    while m < 1300:
        a = rnd.uniform(math.radians(-110), math.radians(50))
        r = rnd.uniform(68, 110) if m < 800 else rnd.uniform(110, 260)
        x0, y0 = cx + r * math.cos(a), r * math.sin(a)
        if not allowed(x0, y0):
            continue
        for j in range(rnd.randint(5, 12)):
            vc = rnd.choice(trees)
            s = rnd.uniform(0.85, 1.4) if 'fir' in vc.name else rnd.uniform(2.4, 3.6)
            x, y = x0 + rnd.uniform(-9, 9), y0 + rnd.uniform(-9, 9)
            if not tree_ok(x, y):
                continue
            place(vc, (x, y, 0), rnd.uniform(0, 6.28), s, coll)
            m += 1
    return n + m


def build_props(coll, seed=5):
    rnd = random.Random(seed)
    def put(name, pts, scale=1.0):
        vs = variants(name)
        for (x, y, z, r) in pts:
            place(rnd.choice(vs), (x, y, z), r, scale, coll)
    # drum store at the west end and by the dock
    put('Barrel_01', [(-38.5 + (i % 3) * 0.62, -26 + (i // 3) * 0.62, 0, rnd.uniform(0, 6.28)) for i in range(9)])
    put('Barrel_02', [(-36.2 + (i % 2) * 0.55, -26 + (i // 2) * 0.55, 0, rnd.uniform(0, 6.28)) for i in range(6)])
    put('Barrel_01', [(28 + rnd.uniform(-1, 1), 24 + rnd.uniform(-2, 2), F_, rnd.uniform(0, 6.28)) for _ in range(5)])
    # crates and boxes by the racks, in the hall and on the dock
    put('wooden_crate_01', [(0.5 + i * 1.0, 7.2, F_, rnd.uniform(-0.2, 0.2)) for i in range(6)])
    put('wooden_crate_01', [(-38.6, 6 + i * 0.9, 0, 0) for i in range(4)])
    put('cardboard_box_01', [(rnd.uniform(-1, 9), rnd.uniform(6.6, 7.6), F_ + 0.35, rnd.uniform(0, 6.28)) for _ in range(8)])
    put('plastic_crate_01', [(18 + (i % 4) * 0.45, 6 + (i // 4) * 0.5, F_, 0) for i in range(8)])
    # welding carts and tool chests at the robot cells and bench
    put('portable_welding_cart', [(x + 2.6, 6.8, F_, rnd.uniform(-0.5, 0.5)) for x in (-20, -14, -8)])
    put('metal_tool_chest', [(x - 2.8, 4.0, F_, 1.57) for x in (-20, -14, -8)] + [(17.6, -10.2, F_, 0.0)])
    # chain-link fence around the deployment yard (pad top z 0.8)
    panel = variants('modular_chainlink_fence', pattern=r'^modular_chainlink_fence_double$', tag='_double')[0]
    post = variants('modular_chainlink_fence', pattern=r'^modular_chainlink_fence_post$', tag='_post')[0]
    y = -15.5
    while y < 15.5:
        place(panel, (51.6, y + 1.0, 0.8), math.pi / 2, 1.0, coll)
        place(post, (51.6, y, 0.8), 0, 1.0, coll)
        y += 2.0
    x = 33.6
    while x < 51.6:
        place(panel, (x + 1.0, -15.9, 0.8), 0, 1.0, coll)
        place(post, (x, -15.9, 0.8), 0, 1.0, coll)
        x += 2.0
    # trash cans by the gatehouse and school
    put('metal_trash_can', [(-13.6, -25.4, 0, 0.0), (5.4, -28.6, 0, 1.57), (27.5, 18.5, F_, 0.4)])


F_ = 1.83
