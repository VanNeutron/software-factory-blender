"""The Software Factory at dusk: a realistic, grimy industrial scene.

Layout follows Fig. 1 on grunertlabs.ca (sites/home/src/scripts/fig1/geo.js),
scaled 1 Fig unit = 10 m. Fig (x, y-up, z-toward-viewer) -> Blender (X, -Z, Y).

Run inside Blender (via MCP): exec(open(PATH).read()); build_all()
Idempotent: it deletes and rebuilds the "Factory" collection.
"""
import bpy, bmesh, math, random
from mathutils import Vector, Matrix

random.seed(7)
COLL = "Factory"
F = 1.8            # slab top (m)
FRAMES = [-28.6 + 9.05 * i for i in range(7)]
USE_AO = False
A = None   # assets module namespace (Poly Haven), set by build_all
INTERIOR = False   # True when interior.py (robots, animated line) is loaded
ACCENT = (0.33, 0.39, 1.0)      # #9AA8FF in linear-ish
GREEN = (0.15, 0.62, 0.32)      # #6CCB98 in linear-ish

# --------------------------------------------------------------------------
# scene plumbing
# --------------------------------------------------------------------------

def coll():
    c = bpy.data.collections.get(COLL)
    if c is None:
        c = bpy.data.collections.new(COLL)
        bpy.context.scene.collection.children.link(c)
    return c


def clear():
    c = bpy.data.collections.get(COLL)
    if c:
        for o in list(c.all_objects):
            bpy.data.objects.remove(o, do_unlink=True)
        for ch in list(c.children):
            bpy.data.collections.remove(ch)
    for o in list(bpy.data.objects):          # the startup cube / light / camera
        if o.name in ("Cube", "Light", "Camera"):
            bpy.data.objects.remove(o, do_unlink=True)
    for blk in (bpy.data.meshes, bpy.data.lights, bpy.data.cameras):
        for d in list(blk):
            if d.users == 0:
                blk.remove(d)
    try:
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
    except Exception:
        pass


def link(obj, sub=None):
    c = coll()
    if sub:
        s = bpy.data.collections.get(sub)
        if s is None:
            s = bpy.data.collections.new(sub)
            c.children.link(s)
        c = s
    c.objects.link(obj)
    return obj


def mesh_obj(name, verts, faces, mat, sub=None, bevel=0.0, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    if mat:
        me.materials.append(mat)
    if bevel > 0:
        m = ob.modifiers.new("Bevel", 'BEVEL')
        m.width = bevel
        m.segments = 2
        m.limit_method = 'ANGLE'
    return link(ob, sub)


BOX_F = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def box(name, x0, x1, y0, y1, z0, z1, mat, sub=None, bevel=0.02):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    return mesh_obj(name, v, BOX_F, mat, sub, bevel)


def beam(name, p, q, w, h, mat, sub=None, up=Vector((0, 0, 1)), bevel=0.01):
    """Box of cross-section w x h running from p to q."""
    p, q = Vector(p), Vector(q)
    d = (q - p)
    L = d.length
    d.normalize()
    side = d.cross(up)
    if side.length < 1e-4:
        side = d.cross(Vector((1, 0, 0)))
    side.normalize()
    upv = side.cross(d).normalized()
    hw, hh = w / 2, h / 2
    vs = []
    for t in (p, q):
        for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            vs.append(tuple(t + side * a * hw + upv * b * hh))
    faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return mesh_obj(name, vs, faces, mat, sub, bevel)


def cyl(name, x, y, z0, z1, r0, r1, mat, sub=None, seg=48):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                          radius1=r0, radius2=r1, depth=z1 - z0,
                          matrix=Matrix.Translation((x, y, (z0 + z1) / 2)))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = abs(p.normal.z) < 0.9
    ob = bpy.data.objects.new(name, me)
    if mat:
        me.materials.append(mat)
    return link(ob, sub)


def prism(name, poly, axis_from, axis_to, mat, sub=None, bevel=0.02):
    """Extrude a planar polygon (list of 3D points at axis_from) by vector axis_to-axis_from."""
    off = Vector(axis_to) - Vector(axis_from)
    n = len(poly)
    vs = [tuple(Vector(p)) for p in poly] + [tuple(Vector(p) + off) for p in poly]
    faces = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    ob = mesh_obj(name, vs, faces, mat, sub, bevel)
    # fix normals
    me = ob.data
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    return ob


def light(name, kind, loc, energy, color, size=1.0, size_y=None, rot=(0, 0, 0), sub="Lights", spot=None):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    if kind == 'AREA':
        ld.shape = 'RECTANGLE' if size_y else 'SQUARE'
        ld.size = size
        if size_y:
            ld.size_y = size_y
    elif kind in ('POINT', 'SPOT'):
        ld.shadow_soft_size = size
    if kind == 'SPOT' and spot:
        ld.spot_size = spot
        ld.spot_blend = 0.6
    ob = bpy.data.objects.new(name, ld)
    ob.location = loc
    ob.rotation_euler = rot
    return link(ob, sub)

# --------------------------------------------------------------------------
# materials (procedural, Cycles)
# --------------------------------------------------------------------------

def _new_mat(name):
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    return m, nt, bsdf


def _ramp(nt, src, stops):
    r = nt.nodes.new('ShaderNodeValToRGB')
    els = r.color_ramp.elements
    els[0].position, els[0].color = stops[0][0], (*stops[0][1], 1)
    els[1].position, els[1].color = stops[-1][0], (*stops[-1][1], 1)
    for pos, col in stops[1:-1]:
        e = els.new(pos); e.color = (*col, 1)
    nt.links.new(src, r.inputs[0])
    return r


def _noise(nt, vec, scale, detail=6, rough=0.55, dim='3D'):
    n = nt.nodes.new('ShaderNodeTexNoise')
    n.noise_dimensions = dim
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail
    n.inputs['Roughness'].default_value = rough
    nt.links.new(vec, n.inputs['Vector'])
    return n


def _mix(nt, a, b, fac, mode='MIX'):
    m = nt.nodes.new('ShaderNodeMix')
    m.data_type = 'RGBA'
    m.blend_type = mode
    if isinstance(fac, float):
        m.inputs['Factor'].default_value = fac
    else:
        nt.links.new(fac, m.inputs['Factor'])
    for sock, v in ((m.inputs[6], a), (m.inputs[7], b)):
        if isinstance(v, tuple):
            sock.default_value = (*v, 1)
        else:
            nt.links.new(v, sock)
    return m.outputs[2]


def _math(nt, op, a, b=None, clamp=True):
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


def grimy(name, base, metallic=0.0, rough=0.7, var=0.35, streak=0.5, rust=0.0,
          bump=0.25, corrugate=0.0, ao_grime=0.6, corr_axis='XY', corr_pitch=0.18):
    """Weathered surface: tonal variation, vertical rain streaks, grime in crevices (AO), optional rust and corrugation."""
    m, nt, b = _new_mat(name)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    pos = tc.outputs['Object']
    # broad tonal variation
    n1 = _noise(nt, pos, 0.35, 8, 0.6)
    lo = tuple(c * (1 - var) for c in base)
    hi = tuple(min(1, c * (1 + var * 0.6)) for c in base)
    col = _ramp(nt, n1.outputs['Fac'], [(0.3, lo), (0.7, hi)]).outputs[0]
    # vertical streaks: squash noise in Z
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (3.0, 3.0, 0.12)
    nt.links.new(pos, mp.inputs['Vector'])
    n2 = _noise(nt, mp.outputs[0], 1.6, 4, 0.5)
    sk = _ramp(nt, n2.outputs['Fac'], [(0.45, (0, 0, 0)), (0.75, (1, 1, 1))]).outputs[0]
    dirt = tuple(c * 0.35 for c in base)
    col = _mix(nt, col, (0.06, 0.05, 0.04), _math(nt, 'MULTIPLY', sk, streak))
    # crevice grime
    if USE_AO and ao_grime > 0:
        ao = nt.nodes.new('ShaderNodeAmbientOcclusion')
        ao.samples = 8
        ao.inputs['Distance'].default_value = 1.2
        aor = _ramp(nt, ao.outputs['AO'], [(0.0, (0, 0, 0)), (0.85, (1, 1, 1))]).outputs[0]
        col = _mix(nt, col, _mix(nt, col, (0.05, 0.045, 0.035), 0.75), _math(nt, 'MULTIPLY', _math(nt, 'SUBTRACT', 1.0, aor), ao_grime))
    else:
        # cheap grime: darken toward the ground (splash zone) instead of ray-traced AO
        sepz = nt.nodes.new('ShaderNodeSeparateXYZ')
        nt.links.new(pos, sepz.inputs[0])
        zf = _math(nt, 'SUBTRACT', 1.0, _math(nt, 'DIVIDE', sepz.outputs[2], 3.5))
        col = _mix(nt, col, (0.05, 0.045, 0.035), _math(nt, 'MULTIPLY', _math(nt, 'POWER', zf, 2.0), 0.45))
    rough_out = None
    met_out = None
    if rust > 0:
        n3 = _noise(nt, pos, 0.9, 10, 0.7)
        rm = _ramp(nt, n3.outputs['Fac'], [(0.62 - rust * 0.15, (0, 0, 0)), (0.7 - rust * 0.12, (1, 1, 1))]).outputs[0]
        rm = _math(nt, 'MAXIMUM', rm, _math(nt, 'MULTIPLY', sk, rust * 0.8))
        rn = _noise(nt, pos, 6, 6, 0.6)
        rust_col = _ramp(nt, rn.outputs['Fac'], [(0.3, (0.12, 0.035, 0.012)), (0.7, (0.32, 0.11, 0.035))]).outputs[0]
        col = _mix(nt, col, rust_col, rm)
        rough_out = _math(nt, 'ADD', rough, _math(nt, 'MULTIPLY', rm, 0.95 - rough))
        met_out = _math(nt, 'MULTIPLY', _math(nt, 'SUBTRACT', 1.0, rm), metallic)
    nt.links.new(col, b.inputs['Base Color'])
    # roughness variation
    n4 = _noise(nt, pos, 2.5, 5, 0.6)
    rv = _math(nt, 'ADD', _math(nt, 'MULTIPLY', _math(nt, 'SUBTRACT', n4.outputs['Fac'], 0.5), 0.3),
               rough_out if rough_out is not None else rough)
    nt.links.new(rv, b.inputs['Roughness'])
    if met_out is not None:
        nt.links.new(met_out, b.inputs['Metallic'])
    else:
        b.inputs['Metallic'].default_value = metallic
    # bump
    n5 = _noise(nt, pos, 14, 8, 0.65)
    h = n5.outputs['Fac']
    if corrugate > 0:
        sep = nt.nodes.new('ShaderNodeSeparateXYZ')
        nt.links.new(pos, sep.inputs[0])
        if corr_axis == 'XY':
            u = _math(nt, 'ADD', sep.outputs[0], sep.outputs[1], clamp=False)
        elif corr_axis == 'Y':
            u = sep.outputs[1]
        else:
            u = sep.outputs[0]
        s = _math(nt, 'SINE', _math(nt, 'MULTIPLY', u, 2 * math.pi / corr_pitch, clamp=False), clamp=False)
        h = _math(nt, 'ADD', _math(nt, 'MULTIPLY', h, 0.15, clamp=False), _math(nt, 'MULTIPLY', s, corrugate, clamp=False), clamp=False)
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs['Strength'].default_value = bump
    bp.inputs['Distance'].default_value = 0.05
    nt.links.new(h, bp.inputs['Height'])
    nt.links.new(bp.outputs[0], b.inputs['Normal'])
    return m


def wet_asphalt(name="Asphalt"):
    m, nt, b = _new_mat(name)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    pos = tc.outputs['Object']
    n1 = _noise(nt, pos, 0.08, 6, 0.6)
    tone = _ramp(nt, n1.outputs['Fac'], [(0.3, (0.025, 0.025, 0.027)), (0.7, (0.075, 0.072, 0.07))]).outputs[0]
    # puddles: big low-frequency blobs
    n2 = _noise(nt, pos, 0.045, 4, 0.55)
    pud = _ramp(nt, n2.outputs['Fac'], [(0.5, (0, 0, 0)), (0.54, (1, 1, 1))]).outputs[0]
    # oil stains
    n3 = _noise(nt, pos, 0.25, 3, 0.5)
    oil = _ramp(nt, n3.outputs['Fac'], [(0.66, (0, 0, 0)), (0.75, (1, 1, 1))]).outputs[0]
    col = _mix(nt, tone, (0.015, 0.014, 0.014), oil)
    col = _mix(nt, col, (0.012, 0.012, 0.013), pud)
    nt.links.new(col, b.inputs['Base Color'])
    rough = _math(nt, 'ADD', 0.42, _math(nt, 'MULTIPLY', pud, -0.40))
    rough = _math(nt, 'SUBTRACT', rough, _math(nt, 'MULTIPLY', oil, 0.25))
    nt.links.new(rough, b.inputs['Roughness'])
    n4 = _noise(nt, pos, 40, 10, 0.75)
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs['Distance'].default_value = 0.02
    nt.links.new(_math(nt, 'MULTIPLY', _math(nt, 'SUBTRACT', 1.0, pud), 0.6), bp.inputs['Strength'])
    nt.links.new(n4.outputs['Fac'], bp.inputs['Height'])
    nt.links.new(bp.outputs[0], b.inputs['Normal'])
    return m


def field(name="Field"):
    """Dry grass and dirt beyond the site."""
    m, nt, b = _new_mat(name)
    pos = nt.nodes.new('ShaderNodeTexCoord').outputs['Object']
    n1 = _noise(nt, pos, 0.02, 6, 0.6)
    n2 = _noise(nt, pos, 0.4, 8, 0.65)
    c1 = _ramp(nt, n1.outputs['Fac'], [(0.35, (0.035, 0.032, 0.018)), (0.65, (0.09, 0.075, 0.04))]).outputs[0]
    c2 = _ramp(nt, n2.outputs['Fac'], [(0.4, (0.03, 0.035, 0.015)), (0.6, (0.07, 0.06, 0.035))]).outputs[0]
    nt.links.new(_mix(nt, c1, c2, 0.5), b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.92
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs['Strength'].default_value = 0.5
    nt.links.new(_noise(nt, pos, 6, 8, 0.7).outputs['Fac'], bp.inputs['Height'])
    nt.links.new(bp.outputs[0], b.inputs['Normal'])
    return m


def haze(name="Haze", density=0.00022):
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    v = nt.nodes.new('ShaderNodeVolumePrincipled')
    v.inputs['Density'].default_value = density
    v.inputs['Color'].default_value = (0.75, 0.72, 0.7, 1)
    v.inputs['Anisotropy'].default_value = 0.65
    nt.links.new(v.outputs[0], out.inputs['Volume'])
    return m


def glass(name="Glass", tint=(0.92, 0.9, 0.86), rough=0.02, dirt=0.1):
    m, nt, b = _new_mat(name)
    b.inputs['Base Color'].default_value = (*tint, 1)
    b.inputs['Transmission Weight'].default_value = 1.0
    b.inputs['IOR'].default_value = 1.5
    try:
        b.inputs['Thin Wall'].default_value = True
    except Exception:
        pass
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (2, 2, 0.3)
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    n = _noise(nt, mp.outputs[0], 1.2, 6, 0.6)
    r = _ramp(nt, n.outputs['Fac'], [(0.4, (rough,) * 3), (0.75, (rough + dirt * 0.5,) * 3)]).outputs[0]
    nt.links.new(r, b.inputs['Roughness'])
    # shadow rays pass straight through (lets sun and lamp light through windows without caustics)
    out = [n for n in nt.nodes if n.bl_idname == 'ShaderNodeOutputMaterial'][0]
    lp = nt.nodes.new('ShaderNodeLightPath')
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    tr.inputs['Color'].default_value = (*tint, 1)
    mx = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(lp.outputs['Is Shadow Ray'], mx.inputs['Fac'])
    nt.links.new(b.outputs[0], mx.inputs[1])
    nt.links.new(tr.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs['Surface'])
    return m


def emit(name, color, strength):
    m, nt, b = _new_mat(name)
    b.inputs['Base Color'].default_value = (0.02, 0.02, 0.02, 1)
    b.inputs['Emission Color'].default_value = (*color, 1)
    b.inputs['Emission Strength'].default_value = strength
    b.inputs['Roughness'].default_value = 0.4
    return m


def plain(name, color, metallic=0.0, rough=0.5):
    m, nt, b = _new_mat(name)
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Metallic'].default_value = metallic
    b.inputs['Roughness'].default_value = rough
    return m


def make_materials():
    M = {}
    M['asphalt'] = wet_asphalt()
    M['concrete'] = grimy("Concrete", (0.42, 0.41, 0.39), rough=0.85, var=0.3, streak=0.55, bump=0.3)
    M['concrete_dark'] = grimy("ConcreteDark", (0.22, 0.22, 0.21), rough=0.85, var=0.3, streak=0.6, bump=0.3)
    M['floor'] = grimy("FactoryFloor", (0.32, 0.33, 0.33), rough=0.28, var=0.25, streak=0.0, bump=0.08, ao_grime=0.8)
    M['cladding'] = grimy("Cladding", (0.30, 0.36, 0.40), metallic=0.55, rough=0.42, var=0.18, streak=0.4,
                          rust=0.22, bump=0.5, corrugate=1.0, corr_pitch=0.15)
    M['field'] = field()
    M['tree'] = plain("TreeDark", (0.012, 0.018, 0.010), 0, 0.9)
    M['town'] = emit("TownLights", (1.0, 0.62, 0.3), 30)
    M['roof'] = grimy("RoofSheet", (0.18, 0.2, 0.21), metallic=0.6, rough=0.45, var=0.3, streak=0.4,
                      rust=0.45, bump=0.5, corrugate=1.0, corr_axis='X', corr_pitch=0.25)
    M['steel'] = grimy("SteelDark", (0.07, 0.075, 0.08), metallic=0.85, rough=0.45, var=0.2, streak=0.3, rust=0.25, bump=0.15)
    M['galv'] = grimy("Galvanized", (0.55, 0.56, 0.56), metallic=1.0, rough=0.35, var=0.3, streak=0.6, rust=0.2, bump=0.15)
    M['crane'] = grimy("CraneYellow", (0.55, 0.38, 0.06), metallic=0.3, rough=0.45, var=0.25, streak=0.5, rust=0.35, bump=0.1)
    M['robot'] = grimy("RobotPaint", (0.62, 0.62, 0.6), metallic=0.1, rough=0.35, var=0.1, streak=0.15, bump=0.05, ao_grime=0.8)
    M['rubber'] = plain("Rubber", (0.015, 0.015, 0.015), 0, 0.75)
    M['server'] = grimy("ServerShell", (0.05, 0.055, 0.06), metallic=0.7, rough=0.4, var=0.2, streak=0.4, rust=0.15,
                        bump=0.4, corrugate=0.6, corr_axis='X', corr_pitch=0.05)
    M['glass'] = glass()
    M['glass_dark'] = glass("GlassDark", tint=(0.35, 0.42, 0.45), rough=0.03, dirt=0.3)
    M['lamp_warm'] = emit("LampWarm", (1.0, 0.78, 0.5), 25)
    M['lamp_cool'] = emit("LampCool", (0.85, 0.92, 1.0), 20)
    M['sodium'] = emit("Sodium", (1.0, 0.55, 0.18), 40)
    M['led_green'] = emit("LedGreen", GREEN, 30)
    M['accent'] = emit("Accent", ACCENT, 25)
    M['accent_soft'] = emit("AccentSoft", ACCENT, 4)
    M['screen'] = emit("Screen", (0.25, 0.32, 0.9), 0.9)
    M['red_light'] = emit("AviationRed", (1.0, 0.05, 0.02), 40)
    M['safety'] = grimy("SafetyYellow", (0.6, 0.45, 0.03), rough=0.5, var=0.2, streak=0.3, bump=0.05)
    M['crate'] = grimy("Crate", (0.3, 0.22, 0.13), rough=0.8, var=0.35, streak=0.2, bump=0.2)
    M['shutter'] = M['steel']
    if A is not None:
        A['pbr_materials'](M)
    return M

# --------------------------------------------------------------------------
# world, sun, render
# --------------------------------------------------------------------------

def setup_world(elev_deg=2.0, rot_deg=338.0):
    scn = bpy.context.scene
    w = scn.world or bpy.data.worlds.new("World")
    scn.world = w
    w.use_nodes = True
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    sky = nt.nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'MULTIPLE_SCATTERING'
    sky.sun_elevation = math.radians(elev_deg)
    sky.sun_rotation = math.radians(rot_deg)
    sky.altitude = 50
    sky.air_density = 1.0
    sky.aerosol_density = 2.2
    sky.ozone_density = 1.0
    sky.sun_disc = True
    sky.sun_intensity = 0.6
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = 0.35
    out = nt.nodes.new('ShaderNodeOutputWorld')
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    # sun lamp matched to the sky's sun
    e, r = math.radians(elev_deg), math.radians(rot_deg)
    sun_dir = Vector((math.sin(r) * math.cos(e), math.cos(r) * math.cos(e), math.sin(e)))
    ld = bpy.data.lights.new("Sun", 'SUN')
    ld.energy = 3.0
    ld.color = (1.0, 0.55, 0.28)
    ld.angle = math.radians(1.2)
    ob = bpy.data.objects.new("Sun", ld)
    ob.rotation_euler = (-sun_dir).to_track_quat('-Z', 'Y').to_euler()
    link(ob, "Lights")
    return sun_dir


def setup_render(preview=True):
    scn = bpy.context.scene
    scn.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = (d.type == 'METAL')
    scn.cycles.device = 'GPU'
    scn.cycles.samples = 64 if preview else 512
    scn.cycles.use_denoising = True
    scn.cycles.max_bounces = 8
    scn.cycles.caustics_reflective = False
    scn.cycles.caustics_refractive = False
    scn.cycles.blur_glossy = 1.0
    scn.cycles.volume_step_rate = 2.0
    scn.cycles.volume_max_steps = 256
    scn.cycles.volume_bounces = 1
    scn.render.resolution_x = 1920
    scn.render.resolution_y = 1080
    scn.render.resolution_percentage = 50 if preview else 100
    for vt in ('AgX', 'Filmic'):
        try:
            scn.view_settings.view_transform = vt
            break
        except Exception:
            pass
    for lk in ('AgX - Punchy', 'AgX - Medium High Contrast', 'Medium High Contrast'):
        try:
            scn.view_settings.look = lk
            break
        except Exception:
            pass
    scn.view_settings.exposure = 0.0


def setup_glare():
    """Compositor: subtle fog glow so sparks, arcs and lamps bloom like a real lens."""
    scn = bpy.context.scene
    try:
        ng = bpy.data.node_groups.get("FactoryComp") or bpy.data.node_groups.new("FactoryComp", 'CompositorNodeTree')
        for n in list(ng.nodes):
            ng.nodes.remove(n)
        if not ng.interface.items_tree:
            ng.interface.new_socket('Image', in_out='INPUT', socket_type='NodeSocketColor')
            ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
        rl = ng.nodes.new('CompositorNodeRLayers')
        gl = ng.nodes.new('CompositorNodeGlare')
        out = ng.nodes.new('NodeGroupOutput')
        for k, v in (('glare_type', 'FOG_GLOW'), ('quality', 'HIGH'), ('threshold', 2.5), ('mix', -0.75), ('size', 7)):
            try:
                setattr(gl, k, v)
            except Exception:
                pass
        for nm, v in (('Type', 'Fog Glow'), ('Threshold', 2.5), ('Strength', 0.35), ('Size', 0.6), ('Quality', 'High')):
            if nm in gl.inputs:
                try:
                    gl.inputs[nm].default_value = v
                except Exception:
                    pass
        ng.links.new(rl.outputs['Image'], gl.inputs['Image'])
        ng.links.new(gl.outputs['Image'], out.inputs[0])
        scn.compositing_node_group = ng
        scn.render.use_compositing = True
        return 'ok'
    except Exception as e:
        return repr(e)


def setup_camera(loc=(58, -62, 9), target=(-6, 8, 9), lens=24):
    cd = bpy.data.cameras.new("HeroCam")
    cd.lens = lens
    cd.clip_end = 3000
    ob = bpy.data.objects.new("HeroCam", cd)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    link(ob)
    bpy.context.scene.camera = ob
    return ob

# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def build_site(M):
    S = "Site"
    # ground to the horizon
    R = 1500
    mesh_obj("Ground", [(-R, -R, 0), (R, -R, 0), (R, R, 0), (-R, R, 0)], [(0, 1, 2, 3)], M['field'], S)
    box("SiteApron", -41, 55, -30.5, 30.5, 0, 0.02, M['asphalt'], S, 0)
    box("AccessRoad", -14, -6, -R, -30.5, 0, 0.02, M['asphalt'], S, 0)
    box("Highway", -R, R, -48, -36, 0, 0.02, M['asphalt'], S, 0)
    for k in range(-60, 60):
        box(f"LaneDash{k}", k * 12, k * 12 + 5, -42.15, -41.85, 0.02, 0.025, M['concrete'], S, 0)
    # 01 data foundation: the slab (two pours) and the plate
    box("Slab", -36, 30, -17, 17, 0, 1.4, M['concrete'], S, 0.06)
    box("SlabPlate", -35.4, 29.4, -16.4, 16.4, 1.4, F, M['concrete'], S, 0.03)
    # curbs around the site
    for i, (x0, x1, y0, y1) in enumerate(((-41, 55, -30.5, -30.0), (-41, 55, 30.0, 30.5), (-41, -40.5, -30.5, 30.5), (54.5, 55, -30.5, 30.5))):
        box(f"Curb{i}", x0, x1, y0, y1, 0, 0.25, M['concrete_dark'], S, 0.03)
    # 01 silos
    for i, x in enumerate((-26, -18, -10, -2)):
        cyl(f"Silo{i}", x, 24.2, 0, 10, 3, 3, M['galv'], S)
        cyl(f"SiloCone{i}", x, 24.2, 10, 11.2, 3, 1.6, M['galv'], S)
        cyl(f"SiloHatch{i}", x, 24.2, 11.2, 11.6, 0.6, 0.6, M['steel'], S, 16)
        for zb in (2.5, 5.0, 7.5):
            cyl(f"SiloBand{i}_{zb}", x, 24.2, zb - 0.08, zb + 0.08, 3.06, 3.06, M['steel'], S)
        # ladder
        for side in (-0.25, 0.25):
            beam(f"SiloLadder{i}_{side}", (x + side, 21.1, 0.5), (x + side, 21.1, 10.2), 0.06, 0.06, M['steel'], S)
        for k in range(30):
            z = 0.8 + k * 0.32
            beam(f"SiloRung{i}_{k}", (x - 0.25, 21.1, z), (x + 0.25, 21.1, z), 0.03, 0.03, M['steel'], S, bevel=0)
        # pipe from silo into the hall
        beam(f"SiloPipe{i}", (x - 0.5, 21.2, 1.0), (x - 0.5, 17, 1.0), 0.5, 0.5, M['galv'], S)
        beam(f"SiloPipeB{i}", (x - 0.5, 17, 1.0), (x - 0.5, 13.5, 3.0), 0.5, 0.5, M['galv'], S)
    # pipe rack along the back of the hall
    for k in range(9):
        x = -28 + k * 6.6
        beam(f"PipeRackPost{k}", (x, 15.5, F), (x, 15.5, 6), 0.3, 0.3, M['steel'], S)
        beam(f"PipeRackArm{k}", (x, 13.4, 6), (x, 16.2, 6), 0.25, 0.25, M['steel'], S)
    for j, (yy, rr) in enumerate(((14.0, 0.35), (14.9, 0.25), (15.7, 0.45))):
        beam(f"PipeRun{j}", (-30, yy, 6 + rr), (26, yy, 6 + rr), rr * 2, rr * 2, M['galv'] if j != 1 else M['steel'], S)


def build_hall(M):
    S = "Hall"
    x0, x1, y0, y1 = -29.0, 26.0, -13.0, 13.0
    WALL, RIDGE, t = 10.8, 13.6, 0.35
    # interior floor
    box("HallFloor", x0, x1, y0, y1, F, F + 0.03, M['floor'], S, 0)
    # aisle markings
    for yy in (-3.0, 1.0):
        box(f"AisleLine{yy}", x0 + 1, x1 - 1, yy - 0.08, yy + 0.08, F + 0.03, F + 0.035, M['safety'], S, 0)
    # back wall (+Y): cladding, window band 6.6-9.0, cladding above
    box("BackWallLow", x0, x1, y1 - t, y1, F, 6.6, M['cladding'], S)
    box("BackWallHigh", x0, x1, y1 - t, y1, 9.0, WALL, M['cladding'], S)
    box("BackWindows", x0, x1, y1 - t * 0.6, y1 - t * 0.4, 6.6, 9.0, M['glass'], S, 0)
    for xf in FRAMES:
        box(f"BackMullion{xf:.1f}", xf - 0.12, xf + 0.12, y1 - t - 0.05, y1 + 0.05, 6.6, 9.0, M['steel'], S)
    # front wall (-Y): concrete upstand to 3.4 with the entry gap at the gatehouse (x -12.8..-7.2), glass curtain above
    box("FrontUpstandA", x0, -12.8, y0, y0 + t, F, 3.4, M['concrete'], S)
    box("FrontUpstandB", -7.2, x1, y0, y0 + t, F, 3.4, M['concrete'], S)
    box("FrontCurtain", x0, x1, y0 + t * 0.4, y0 + t * 0.6, 3.4, WALL, M['glass'], S, 0)
    box("EntryGlass", -12.8, -7.2, y0 + t * 0.4, y0 + t * 0.6, F, 3.4, M['glass'], S, 0)
    box("EntryCanopy", -13.6, -6.4, y0 - 2.5, y0, 4.6, 4.9, M['steel'], S)
    for xf in FRAMES:
        for k in range(3):
            xm = xf + k * 9.05 / 3
            if xm > x1 + 0.01:
                continue
            box(f"FrontMullion{xm:.1f}", xm - 0.09, xm + 0.09, y0 - 0.12, y0 + t, 3.4, WALL, M['steel'], S)
    for zt in (3.4, 6.4, 8.6):
        box(f"FrontTransom{zt}", x0, x1, y0 - 0.12, y0 + t, zt - 0.08, zt + 0.08, M['steel'], S)
    # end walls with gables
    def gable(name, x, opening=None):
        xa, xb = (x, x + t) if x < 0 else (x - t, x)
        if opening:
            oy0, oy1, oz1 = opening
            box(name + "A", xa, xb, y0, oy0, F, WALL, M['cladding'], S)
            box(name + "B", xa, xb, oy1, y1, F, WALL, M['cladding'], S)
            box(name + "Lintel", xa, xb, oy0, oy1, oz1, WALL, M['cladding'], S)
            box(name + "Shutter", xa - 0.2, xb + 0.2, oy0 - 0.2, oy1 + 0.2, oz1 - 0.9, oz1, M['shutter'], S)
        else:
            box(name, xa, xb, y0, y1, F, WALL, M['cladding'], S)
        prism(name + "Gable", [(xa, y0, WALL), (xa, y1, WALL), (xa, 0, RIDGE)], (xa, 0, 0), (xb, 0, 0), M['cladding'], S)
    gable("WallWest", x0)
    gable("WallEast", x1, opening=(-5.0, 3.0, 8.0))
    # portal frames (columns + rafters) inside
    for i, xf in enumerate(FRAMES):
        for yy in (y0 + t + 0.3, y1 - t - 0.3):
            beam(f"Column{i}_{yy:.0f}", (xf, yy, F), (xf, yy, WALL), 0.5, 0.35, M['steel'], S)
        beam(f"RafterA{i}", (xf, y0 + t, WALL - 0.3), (xf, 0, RIDGE - 0.3), 0.3, 0.6, M['steel'], S)
        beam(f"RafterB{i}", (xf, y1 - t, WALL - 0.3), (xf, 0, RIDGE - 0.3), 0.3, 0.6, M['steel'], S)
    # roof: two slopes, glazed ridge strip
    s = 1.6
    zs = WALL + (RIDGE - WALL) * (1 - s / 13.0)
    ov = 0.6
    for nm, ya, yb in (("RoofFront", y0 - ov, -s), ("RoofBack", y1 + ov, s)):
        za = WALL - (RIDGE - WALL) * ov / 13.0
        poly = [(x0 - ov, ya, za), (x0 - ov, yb, zs), (x0 - ov, yb, zs + 0.25), (x0 - ov, ya, za + 0.25)]
        prism(nm, poly, (x0 - ov, 0, 0), (x1 + ov, 0, 0), M['roof'], S, 0.02)
    prism("RidgeLight", [(x0, -s, zs + 0.1), (x0, s, zs + 0.1), (x0, 0, RIDGE + 0.15)], (x0, 0, 0), (x1, 0, 0), M['glass'], S, 0)
    # roof extract fans
    for k in range(5):
        x = -22 + k * 11
        for yy in (-7.5, 7.5):
            zr = WALL + (RIDGE - WALL) * (1 - abs(yy) / 13.0) + 0.25
            cyl(f"RoofFan{k}_{yy}", x, yy, zr, zr + 1.1, 0.9, 0.8, M['galv'], S, 24)
            cyl(f"RoofFanCap{k}_{yy}", x, yy, zr + 1.1, zr + 1.3, 1.05, 0.2, M['galv'], S, 24)
    # gutters and downpipes
    for yy in (y0 - 0.7, y1 + 0.7):
        beam(f"Gutter{yy:.0f}", (x0 - 0.6, yy, WALL - 0.1), (x1 + 0.6, yy, WALL - 0.1), 0.35, 0.3, M['galv'], S)
    for xf in (x0 + 0.5, -2, x1 - 0.5):
        beam(f"Downpipe{xf:.0f}", (xf, y1 + 0.75, F), (xf, y1 + 0.75, WALL - 0.1), 0.18, 0.18, M['galv'], S)
    # interior lights: luminaires + area lights
    for i in range(6):
        xc = (FRAMES[i] + FRAMES[i + 1]) / 2
        for yy in (-6.0, 5.0):
            box(f"Luminaire{i}_{yy:.0f}", xc - 2.5, xc + 2.5, yy - 0.25, yy + 0.25, 9.2, 9.3, M['lamp_warm'], S, 0)
            light(f"HallLight{i}_{yy:.0f}", 'AREA', (xc, yy, 9.1), 2600, (1.0, 0.72, 0.45), size=5.0, size_y=0.6)


def build_line(M):
    S = "ProductionLine"
    # conveyor in the hall and out through the east door to the yard
    box("ConveyorFrame", -27.5, 33.5, -2.0, 0.0, 2.8, 3.45, M['steel'], S)
    if not INTERIOR:
        box("ConveyorBelt", -27.5, 33.5, -1.85, -0.15, 3.45, 3.52, M['rubber'], S, 0.005)
    for k in range(19):
        x = -27 + k * 3.35
        for yy in (-1.85, -0.15):
            beam(f"ConvLeg{k}_{yy}", (x, yy, F if x < 26 else 0.8 if x > 33.5 else F), (x, yy, 2.8), 0.15, 0.15, M['steel'], S)
    # guard rails
    for yy in (-2.05, 0.05):
        beam(f"ConvRail{yy}", (-27.5, yy, 3.7), (33.5, yy, 3.7), 0.08, 0.12, M['safety'], S)
    # intake hopper outside the west wall
    box("HopperBase", -34.2, -30.8, -2.7, 0.7, F, 4.0, M['concrete_dark'], S)
    cyl("Hopper", -32.5, -1.0, 4.0, 7.6, 1.1, 2.4, M['galv'], S)
    beam("HopperChute", (-31, -1, 4.6), (-27.5, -1, 3.6), 1.0, 0.8, M['galv'], S)
    if not INTERIOR:
        # robot cells
        for i, x in enumerate((-20, -14, -8)):
            box(f"RobotPlinth{i}", x - 1.6, x + 1.6, 2.3, 5.5, F, 2.2, M['concrete_dark'], S)
            cyl(f"RobotBase{i}", x, 3.9, 2.2, 3.0, 0.9, 0.8, M['robot'], S, 32)
            cyl(f"RobotTurret{i}", x, 3.9, 3.0, 4.4, 0.6, 0.55, M['robot'], S, 32)
            sh = (x + 0.4, 3.4, 4.4)
            el = (x + 1.0, 1.6, 6.6)
            wr = (x + 0.5, -0.9, 5.0)
            beam(f"RobotUpper{i}", sh, el, 0.55, 0.7, M['robot'], S)
            beam(f"RobotFore{i}", el, wr, 0.45, 0.45, M['robot'], S)
            beam(f"RobotTool{i}", wr, (x + 0.5, -0.9, 4.0), 0.25, 0.25, M['steel'], S)
            light(f"RobotWeld{i}", 'POINT', (x + 0.5, -0.9, 3.8), 60, (0.6, 0.75, 1.0), size=0.05)
            # safety fence around cell
            for k in range(5):
                xx = x - 2.2 + k * 1.1
                beam(f"CellPost{i}_{k}", (xx, 6.0, F), (xx, 6.0, 3.8), 0.08, 0.08, M['safety'], S)
            box(f"CellMesh{i}", x - 2.2, x + 2.2, 5.98, 6.02, 2.0, 3.8, M['steel'], S, 0)
    # storage racking along the back wall
    for k in range(5):
        xx = -1 + k * 2.75
        for yy in (8.2, 11.0):
            beam(f"RackUpright{k}_{yy}", (xx, yy, F), (xx, yy, 6.9), 0.12, 0.12, M['safety'] if k % 2 == 0 else M['steel'], S)
    for zz in (2.1, 3.6, 5.1, 6.6):
        box(f"RackShelf{zz}", -1, 10, 8.2, 11.0, zz, zz + 0.12, M['steel'], S)
        for k in range(0 if INTERIOR else 4):
            if random.random() < 0.8:
                xx = -0.6 + k * 2.75
                box(f"RackCrate{zz}_{k}", xx, xx + 2.0, 8.4, 10.8, zz + 0.12, zz + 0.12 + random.uniform(0.6, 1.2), M['crate'], S)
    # workbench with screens (front side)
    box("BenchTop", 2, 17, -11.2, -8.2, F + 0.9, F + 1.0, M['steel'], S)
    for xx in (2.2, 9.5, 16.8):
        beam(f"BenchLeg{xx}", (xx, -9.7, F), (xx, -9.7, F + 0.9), 0.12, 2.6, M['steel'], S)
    for k in range(6):
        xx = 2.8 + k * 2.4
        box(f"Monitor{k}", xx, xx + 1.4, -9.0, -8.9, F + 1.2, F + 2.0, M['screen'], S, 0)
        box(f"MonitorBack{k}", xx - 0.03, xx + 1.43, -8.9, -8.8, F + 1.17, F + 2.03, M['steel'], S, 0)
    # inspection gates over the line
    for gx in (4.5, 13.0):
        box(f"GatePostA{gx}", gx - 0.3, gx + 0.3, 0.6, 1.2, F, 6.8, M['steel'], S)
        box(f"GatePostB{gx}", gx - 0.3, gx + 0.3, -3.2, -2.6, F, 6.8, M['steel'], S)
        box(f"GateBeam{gx}", gx - 0.4, gx + 0.4, -3.2, 1.2, 6.8, 7.4, M['steel'], S)
        for q in range(5):
            yy = 0.8 - 0.9 * q
            box(f"GateLamp{gx}_{q}", gx - 0.42, gx - 0.38, yy - 0.15, yy + 0.15, 6.95, 7.25, M['led_green'], S, 0)
        light(f"GateGlow{gx}", 'AREA', (gx, -1.0, 6.7), 120, (0.55, 0.62, 1.0), size=0.6, size_y=3.0)
    # control cabinet
    box("ControlCabinet", 17.5, 23, 2.0, 4.5, F, 3.8, M['server'], S)
    box("ControlScreen", 18, 20, 1.98, 2.0, 2.6, 3.4, M['screen'], S, 0)
    if not INTERIOR:
        # ideas (accent) and finished products on the belt
        for i, x in enumerate((-24.0, -17.5, -5.0, 9.0)):
            box(f"Idea{i}", x - 0.6, x + 0.6, -1.6, -0.4, 3.52, 4.72, M['accent'], S, 0.05)
        light("IdeaGlowA", 'POINT', (-17.5, -1, 5.0), 40, ACCENT, size=0.5)
        light("IdeaGlowB", 'POINT', (9.0, -1, 5.0), 40, ACCENT, size=0.5)
        for i, x in enumerate((19.0, 24.0, 30.0)):
            box(f"Product{i}", x - 0.7, x + 0.7, -1.7, -0.3, 3.52, 4.92, M['galv'], S, 0.06)
            box(f"ProductBand{i}", x - 0.72, x + 0.72, -1.72, -0.28, 4.55, 4.65, M['accent'], S, 0)


def build_gate_and_school(M):
    S = "Gatehouse"
    box("Gatehouse", -12.8, -7.2, -24.2, -20.2, 0, 3.2, M['concrete'], S)
    box("GatehouseWin", -12.6, -7.4, -24.25, -24.15, 1.2, 2.7, M['glass_dark'], S, 0)
    box("GatehouseRoof", -13.6, -6.4, -24.8, -19.6, 3.2, 3.6, M['steel'], S)
    light("GatehouseLight", 'POINT', (-10, -22.2, 2.5), 150, (1.0, 0.8, 0.55), size=0.3)
    light("GateCanopyLight", 'SPOT', (-10, -25, 3.4), 400, (1.0, 0.75, 0.45), size=0.2, rot=(0, 0, 0), spot=math.radians(110))
    for i, x in enumerate((-5.0, -2.8, -0.6, 1.6)):
        box(f"Bollard{i}", x - 0.3, x + 0.3, -22.6, -21.8, 0, 1.7, M['safety'], S)
        beam(f"Barrier{i}", (x, -22.2, 1.3), (x + 1.9, -22.2, 1.3), 0.12, 0.12, M['robot'], S)
        box(f"BollardLamp{i}", x - 0.1, x + 0.1, -22.62, -22.58, 1.4, 1.6, M['led_green'], S, 0)
    # path from gate to the hall entry
    box("Walkway", -10.6, -9.4, -20.2, -17.0, 0, 0.05, M['concrete'], S, 0)

    S = "School"
    ex0, ex1, ez0, ez1 = 6.0, 24.5, -27.8, -20.0
    box("SchoolBase", ex0, ex1, ez0, ez1, 0, 0.4, M['concrete'], S)
    box("SchoolRoof", ex0 - 0.4, ex1 + 0.4, ez0 - 0.4, ez1 + 0.4, 4.2, 4.6, M['concrete_dark'], S)
    box("SchoolBackWall", ex0, ex1, ez1 - 0.5, ez1, 0.4, 4.2, M['concrete'], S)
    box("SchoolGlassFront", ex0, ex1, ez0 + 0.1, ez0 + 0.15, 0.4, 4.2, M['glass'], S, 0)
    box("SchoolGlassW", ex0 + 0.1, ex0 + 0.15, ez0, ez1, 0.4, 4.2, M['glass'], S, 0)
    box("SchoolGlassE", ex1 - 0.15, ex1 - 0.1, ez0, ez1, 0.4, 4.2, M['glass'], S, 0)
    for k in range(8):
        xx = ex0 + k * (ex1 - ex0) / 7
        box(f"SchoolMullion{k}", xx - 0.08, xx + 0.08, ez0, ez0 + 0.25, 0.4, 4.2, M['steel'], S)
    box("SchoolBoard", 8.2, 14.2, ez1 - 0.55, ez1 - 0.5, 1.6, 3.6, M['screen'], S, 0)
    for row, yy in enumerate((-24.2, -26.4)):
        for i, xx in enumerate((8.5, 11.2, 13.9, 16.6, 19.3)):
            box(f"Desk{row}_{i}", xx - 0.7, xx + 0.7, yy - 0.4, yy + 0.4, 0.4, 1.15, M['steel'], S)
    light("SchoolLight", 'AREA', (15.2, -23.9, 4.0), 900, (1.0, 0.85, 0.65), size=16, size_y=6.5, rot=(0, 0, 0))
    light("SchoolBoardGlow", 'AREA', (11.2, -20.7, 2.6), 60, (0.55, 0.62, 1.0), size=6, size_y=2, rot=(math.radians(90), 0, 0))


def build_yard(M):
    S = "Deploy"
    dx0, dx1, dz0, dz1 = 33.5, 51.0, -15.5, 15.5
    box("YardPad", dx0, dx1, dz0, dz1, 0, 0.8, M['concrete'], S)
    n = 0
    for x in (37.5, 45.0):
        for y in (9.5, 1.5, -6.5):
            box(f"Server{n}", x - 2.4, x + 2.4, y - 2.2, y + 2.2, 0.8, 4.4, M['server'], S)
            # rooftop cooling
            box(f"Cooler{n}", x - 2.0, x + 2.0, y - 1.8, y + 1.8, 4.4, 5.0, M['galv'], S)
            for fx in (-1.0, 1.0):
                cyl(f"CoolerFan{n}_{fx}", x + fx, y, 5.0, 5.15, 0.8, 0.8, M['steel'], S, 24)
            # status LEDs on the -Y face
            for q in range(6):
                box(f"Led{n}_{q}", x - 1.8 + q * 0.3, x - 1.65 + q * 0.3, y - 2.23, y - 2.2, 3.7, 3.85, M['led_green'], S, 0)
            box(f"Door{n}", x - 2.0, x + 0.6, y - 2.23, y - 2.2, 1.0, 3.4, M['steel'], S, 0)
            light(f"ServerGlow{n}", 'POINT', (x - 1.0, y - 2.8, 3.8), 15, GREEN, size=0.2)
            n += 1
    # cable trays
    for y in (9.5, 1.5, -6.5):
        beam(f"Tray{y}", (34, y, 4.7), (47.4, y, 4.7), 0.6, 0.15, M['galv'], S)
    # monitoring mast with a beacon
    mx, my = 48.5, 13.0
    for a, b in ((-0.4, -0.4), (0.4, -0.4), (0.4, 0.4), (-0.4, 0.4)):
        beam(f"MastLeg{a}{b}", (mx + a * 2, my + b * 2, 0.8), (mx + a * 0.5, my + b * 0.5, 14.5), 0.15, 0.15, M['galv'], S)
    for k in range(12):
        z = 1.5 + k * 1.1
        f = 1 - (z - 0.8) / 13.7 * 0.75
        r = 0.8 * f
        for (a0, b0), (a1, b1) in (((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))):
            beam(f"MastRing{k}{a0}{b0}", (mx + a0 * r, my + b0 * r, z), (mx + a1 * r, my + b1 * r, z), 0.06, 0.06, M['galv'], S, bevel=0)
    cyl("MastHead", mx, my, 14.5, 15.3, 1.2, 1.2, M['steel'], S, 24)
    cyl("Dish", mx - 1.0, my - 0.6, 15.3, 16.2, 0.2, 1.4, M['galv'], S, 32)
    beam("AntennaL", (mx, my, 15.3), (mx - 2.5, my, 16.2), 0.08, 0.08, M['galv'], S)
    beam("AntennaR", (mx, my, 15.3), (mx + 2.5, my, 16.2), 0.08, 0.08, M['galv'], S)
    cyl("Beacon", mx, my, 15.3, 16.3, 0.22, 0.22, M['accent'], S, 16)
    light("BeaconGlow", 'POINT', (mx, my, 16.6), 400, ACCENT, size=0.3)
    # perimeter fence (replaced by the scanned chain-link fence when assets are present)
    for k in range(15 if A is None else 0):
        y = dz0 + 2.2 * k
        beam(f"FencePostE{k}", (dx1 + 0.6, y, 0.8), (dx1 + 0.6, y, 3.4), 0.1, 0.1, M['galv'], S)
    for k in range(9 if A is None else 0):
        x = dx0 + 2.2 * k
        beam(f"FencePostS{k}", (x, dz0 - 0.4, 0.8), (x, dz0 - 0.4, 3.4), 0.1, 0.1, M['galv'], S)
    for z in ((1.8, 3.0) if A is None else ()):
        beam(f"FenceRailE{z}", (dx1 + 0.6, dz0, z), (dx1 + 0.6, dz1, z), 0.06, 0.06, M['galv'], S)
        beam(f"FenceRailS{z}", (dx0, dz0 - 0.4, z), (dx1 + 0.6, dz0 - 0.4, z), 0.06, 0.06, M['galv'], S)
    # monitoring board
    box("MonitorWall", 41, 49, -12.6, -12.3, 0.8, 4.2, M['concrete_dark'], S)
    box("MonitorScreen", 41.3, 48.7, -12.65, -12.6, 1.2, 3.9, M['rubber'], S, 0)
    pts = [(41.8, 2.55), (44.2, 2.55), (44.6, 3.3), (45.0, 1.7), (45.4, 3.0), (45.7, 2.55), (48.2, 2.55)]
    for i in range(len(pts) - 1):
        beam(f"EcgTrace{i}", (pts[i][0], -12.67, pts[i][1]), (pts[i + 1][0], -12.67, pts[i + 1][1]), 0.07, 0.02, M['led_green'], S, bevel=0)


def build_crane(M):
    S = "Crane"
    cx, cy, H = 14.5, 24.5, 26.0
    w = 0.9
    box("CraneFooting", cx - 2.2, cx + 2.2, cy - 2.2, cy + 2.2, 0, 0.8, M['concrete'], S)
    corners = [(-w, -w), (w, -w), (w, w), (-w, w)]
    for a, b in corners:
        beam(f"CraneChord{a}{b}", (cx + a, cy + b, 0.8), (cx + a, cy + b, H), 0.18, 0.18, M['crane'], S)
    k = 0
    z = 0.8
    while z < H - 0.1:
        z2 = min(H, z + 2.0)
        for i in range(4):
            a0, b0 = corners[i]
            a1, b1 = corners[(i + 1) % 4]
            beam(f"CraneBrace{k}_{i}", (cx + a0, cy + b0, z), (cx + a1, cy + b1, z2), 0.08, 0.08, M['crane'], S, bevel=0)
            beam(f"CraneRing{k}_{i}", (cx + a0, cy + b0, z2), (cx + a1, cy + b1, z2), 0.08, 0.08, M['crane'], S, bevel=0)
        z = z2
        k += 1
    yaw = math.radians(196)
    d = Vector((math.cos(yaw), math.sin(yaw), 0))
    sd = Vector((-d.y, d.x, 0))
    base = Vector((cx, cy, H))
    J, CJ = 52.0, 13.0
    box("CraneSlew", cx - 1.3, cx + 1.3, cy - 1.3, cy + 1.3, H, H + 1.2, M['crane'], S)
    box("CraneCab", cx + 0.4, cx + 2.2, cy - 2.0, cy - 0.4, H - 0.2, H + 1.8, M['crane'], S)
    top = base + Vector((0, 0, 1.2))
    for sgn in (-1, 1):
        beam(f"JibChord{sgn}", top + sd * 0.6 * sgn, top + d * J + sd * 0.6 * sgn, 0.16, 0.16, M['crane'], S)
        beam(f"CJibChord{sgn}", top + sd * 0.8 * sgn, top - d * CJ + sd * 0.8 * sgn, 0.16, 0.16, M['crane'], S)
    tj = top + Vector((0, 0, 1.6))
    beam("JibTop", tj, top + d * J + Vector((0, 0, 0.2)), 0.14, 0.14, M['crane'], S)
    t = 0.0
    k = 0
    while t < J - 0.1:
        t2 = min(J, t + 3.0)
        hh = 1.6 * (1 - (t + 1.5) / J)
        s = 0.6 if k % 2 == 0 else -0.6
        beam(f"JibLace{k}", top + d * t + sd * s, top + d * (t + 1.5) + Vector((0, 0, hh)), 0.06, 0.06, M['crane'], S, bevel=0)
        beam(f"JibLaceB{k}", top + d * (t + 1.5) + Vector((0, 0, hh)), top + d * t2 - sd * s, 0.06, 0.06, M['crane'], S, bevel=0)
        t = t2
        k += 1
    apex = top + Vector((0, 0, 6))
    beam("Apex", top, apex, 0.3, 0.3, M['crane'], S)
    beam("PendantF", apex, top + d * J * 0.62 + Vector((0, 0, 1.0)), 0.05, 0.05, M['steel'], S, bevel=0)
    beam("PendantB", apex, top - d * CJ, 0.05, 0.05, M['steel'], S, bevel=0)
    cw = top - d * (CJ - 1.5)
    box("Counterweight", cw.x - 1.2, cw.x + 1.2, cw.y - 1.2, cw.y + 1.2, cw.z - 2.2, cw.z, M['concrete_dark'], S)
    tr = top + d * 31
    box("Trolley", tr.x - 0.6, tr.x + 0.6, tr.y - 0.6, tr.y + 0.6, tr.z - 0.6, tr.z, M['crane'], S)
    hook_z = 15.0
    beam("HoistCable", tr - Vector((0, 0, 0.6)), Vector((tr.x, tr.y, hook_z)), 0.04, 0.04, M['steel'], S, bevel=0)
    box("HookBlock", tr.x - 0.35, tr.x + 0.35, tr.y - 0.35, tr.y + 0.35, hook_z - 1.0, hook_z, M['safety'], S)
    cyl("AviationLight", apex.x, apex.y, apex.z, apex.z + 0.4, 0.2, 0.2, M['red_light'], S, 12)
    light("AviationGlow", 'POINT', (apex.x, apex.y, apex.z + 0.6), 80, (1.0, 0.05, 0.02), size=0.2)
    jt = top + d * J
    cyl("JibTipLight", jt.x, jt.y, jt.z, jt.z + 0.3, 0.15, 0.15, M['red_light'], S, 12)


def build_poles(M):
    S = "Poles"
    for i, (x, y) in enumerate(((-38, -27), (2, -28.5), (30, -27), (53, -18), (53, 20), (-38, 22), (32, 26))):
        beam(f"Pole{i}", (x, y, 0), (x, y, 11), 0.25, 0.25, M['steel'], S)
        box(f"PoleHead{i}", x - 0.8, x + 0.8, y - 0.35, y + 0.35, 10.8, 11.1, M['steel'], S)
        box(f"PoleLamp{i}", x - 0.7, x + 0.7, y - 0.3, y + 0.3, 10.75, 10.8, M['sodium'], S, 0)
        light(f"PoleLight{i}", 'SPOT', (x, y, 10.6), 900, (1.0, 0.6, 0.28), size=0.4, spot=math.radians(120))


def build_props(M):
    S = "Props"
    # drums, pallets, a parked truck trailer and a puddle-catching skip
    for i in range(0 if A is not None else 14):
        x = random.uniform(-39, -37) if i < 7 else random.uniform(27, 30)
        y = random.uniform(-26, -18) if i < 7 else random.uniform(18, 27)
        cyl(f"Drum{i}", x, y, 0, 1.0, 0.33, 0.33, M['galv'] if i % 3 else M['safety'], S, 20)
    for i in range(6):
        x, y = -38.5 + (i % 2) * 1.4, 4 + (i // 2) * 1.4
        box(f"Pallet{i}", x, x + 1.2, y, y + 1.2, 0, 0.15 + 0.15 * (i % 3), M['crate'], S)
    # trailer at the dock
    box("Trailer", 30.5, 44.0, 19.5, 22.2, 1.2, 5.2, M['cladding'], S)
    box("TrailerChassis", 31, 43.5, 19.8, 21.9, 0.6, 1.2, M['steel'], S)
    for xw in (31.5, 33.0, 41.0, 42.5):
        for yw in (19.6, 22.1):
            box(f"Wheel{xw}_{yw}", xw - 0.5, xw + 0.5, yw - 0.2, yw + 0.2, 0, 1.0, M['rubber'], S, 0.15)
    box("Skip", -34, -30, -26, -23.6, 0, 1.8, M['crane'], S)


def build_surroundings(M):
    S = "Surroundings"
    rnd = random.Random(11)
    if A is not None:
        return build_surroundings_far(M, rnd, S)
    # tree lines: clumps of rough blobs in the background half, 220-900 m out
    n = 0
    bm_src = bmesh.new()
    bmesh.ops.create_icosphere(bm_src, subdivisions=3, radius=1.0)
    tmpl = bpy.data.meshes.new("TreeBlob")
    bm_src.to_mesh(tmpl); bm_src.free()
    for p in tmpl.polygons:
        p.use_smooth = True
    tmpl.materials.append(M['tree'])
    tex = bpy.data.textures.get("LeafNoise") or bpy.data.textures.new("LeafNoise", 'CLOUDS')
    tex.noise_scale = 3.0
    tex.noise_depth = 3
    while n < 900:
        a = rnd.uniform(math.radians(55), math.radians(255))
        r = rnd.uniform(220, 900)
        cxx, cyy = 30 + r * math.cos(a), r * math.sin(a)
        for j in range(rnd.randint(2, 5)):
            sx = rnd.uniform(2.5, 5.5)
            ob = bpy.data.objects.new(f"Tree{n}", tmpl)
            ob.location = (cxx + rnd.uniform(-8, 8), cyy + rnd.uniform(-8, 8), rnd.uniform(4, 9))
            ob.scale = (sx, sx * rnd.uniform(0.8, 1.2), sx * rnd.uniform(1.4, 2.6))
            ob.rotation_euler = (0, 0, rnd.uniform(0, 6.28))
            dm = ob.modifiers.new("Leaves", 'DISPLACE')
            dm.texture = tex
            dm.strength = 0.45
            dm.texture_coords = 'GLOBAL'
            link(ob, S)
            n += 1
    return build_surroundings_far(M, rnd, S)


def build_surroundings_far(M, rnd, S):
    # distant town lights
    for k in range(160):
        a = rnd.uniform(math.radians(80), math.radians(230))
        r = rnd.uniform(500, 1100)
        x, y = r * math.cos(a), r * math.sin(a)
        box(f"Town{k}", x, x + rnd.uniform(1, 3), y, y + 0.5, 1, 1 + rnd.uniform(0.6, 1.5), M['town'], S, 0)
    # distant stacks
    for k, (x, y, h) in enumerate(((-260, 420, 70), (-230, 440, 55), (-300, 390, 62))):
        cyl(f"Stack{k}", x, y, 0, h, 3.5, 2.6, M['concrete_dark'], S, 24)
        cyl(f"StackLight{k}", x, y, h, h + 1, 2.7, 2.7, M['red_light'], S, 24)
    # transmission pylons marching across the background
    prev = None
    for k in range(8):
        x, y = -200 + k * 70, 120 + k * 22
        H = 34
        for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            beam(f"PylonLeg{k}{a}{b}", (x + a * 4, y + b * 4, 0), (x + a * 0.8, y + b * 0.8, H), 0.35, 0.35, M['galv'], S, bevel=0)
        for z, wdt in ((H * 0.62, 9), (H * 0.82, 7), (H, 5)):
            beam(f"PylonArm{k}_{z:.0f}", (x - wdt, y, z), (x + wdt, y, z), 0.4, 0.4, M['galv'], S, bevel=0)
        for z in range(4, int(H), 5):
            f = 1 - z / H * 0.8
            beam(f"PylonX{k}_{z}", (x - 4 * f, y - 4 * f, z), (x + 4 * f, y - 4 * f, z + 5), 0.15, 0.15, M['galv'], S, bevel=0)
            beam(f"PylonY{k}_{z}", (x + 4 * f, y - 4 * f, z), (x - 4 * f, y - 4 * f, z + 5), 0.15, 0.15, M['galv'], S, bevel=0)
        if prev:
            for z, wdt in ((H * 0.62, 9), (H * 0.82, 7), (H, 5)):
                for sx in (-wdt, wdt):
                    p0 = Vector((prev[0] + sx, prev[1], z - 1.5))
                    p1 = Vector((x + sx, y, z - 1.5))
                    pts = []
                    for i in range(13):
                        t = i / 12
                        q = p0.lerp(p1, t)
                        q.z -= 6 * 4 * t * (1 - t)
                        pts.append(q)
                    for i in range(12):
                        beam(f"Wire{k}_{z:.0f}_{sx}_{i}", pts[i], pts[i + 1], 0.06, 0.06, M['steel'], S, bevel=0)
        prev = (x, y)
    # low haze in the first 60 m of air
    hz = box("HazeVolume", -1400, 1400, -1400, 1400, -1, 60, haze(), S, 0)
    hz.visible_shadow = False
    # highway lights
    for k in range(-8, 9):
        x = k * 40
        beam(f"StreetPole{k}", (x, -35.2, 0), (x, -35.2, 10), 0.2, 0.2, M['steel'], S, bevel=0)
        box(f"StreetLamp{k}", x - 0.5, x + 0.5, -36.6, -35.2, 9.8, 10.0, M['sodium'], S, 0)
        light(f"StreetLight{k}", 'SPOT', (x, -36, 9.7), 700, (1.0, 0.55, 0.22), size=0.3, spot=math.radians(110))


def load_assets_module():
    global A
    import os
    p = os.path.join(os.path.dirname(__file__), 'assets.py')
    if not os.path.exists(p):
        A = None
        return None
    ns = {'__name__': 'factory_assets'}
    exec(compile(open(p).read(), p, 'exec'), ns)
    A = ns if ns['have_assets']() else None
    return A


def load_interior_module():
    global INTERIOR
    import os
    p = os.path.join(os.path.dirname(__file__), 'interior.py')
    INTERIOR = A is not None and os.path.exists(p)
    if INTERIOR:
        exec(compile(open(p).read(), p, 'exec'), globals())
    return INTERIOR


def build_all(preview=True, vegetation=True, interior=True):
    clear()
    load_assets_module()
    if interior:
        load_interior_module()
    else:
        global INTERIOR
        INTERIOR = False
    M = make_materials()
    setup_world()
    if A is not None:
        info = A['hdri_world'](target_az_deg=338.0, strength=0.4)
        sun = bpy.data.objects.get("Sun")
        e = math.radians(max(info[0], 1.0)); r = math.radians(338.0)
        d = Vector((math.sin(r) * math.cos(e), math.cos(r) * math.cos(e), math.sin(e)))
        sun.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
        bpy.app.driver_namespace['hdri_info'] = info
    setup_render(preview)
    build_site(M)
    build_hall(M)
    build_line(M)
    build_gate_and_school(M)
    build_yard(M)
    build_crane(M)
    build_poles(M)
    build_props(M)
    build_surroundings(M)
    if A is not None:
        vc = bpy.data.collections.get("Vegetation") or bpy.data.collections.new("Vegetation")
        if vc.name not in coll().children:
            coll().children.link(vc)
        if vegetation:
            A['build_vegetation'](vc)
        A['build_props'](vc)
    if INTERIOR:
        build_interior(M)
    bpy.app.driver_namespace['glare'] = setup_glare()
    setup_camera()
    return len(coll().all_objects)


def render_preview(path, samples=48, pct=50):
    import time
    scn = bpy.context.scene
    scn.cycles.samples = samples
    scn.render.resolution_percentage = pct
    scn.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    return round(time.time() - t, 1)
