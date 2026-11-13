"""Interior wall lining for the hall: painted panels just inside the corrugated cladding, so the inside can have
its own colour while the outside stays weathered iron. Self-contained (only bpy), idempotent.

Styles: 'white' (light panels, charcoal dado), 'slate' (blue-grey panels), 'charcoal' (dark panels).
All have a periwinkle accent stripe (the site accent) above the dado, and set the colour of the overhead lights.

Use from the build:  ns = {}; exec(open('liner.py').read(), ns); ns['apply']('white')
Use for a look test: set FACTORY_LINER=<style> and run  blender -b scene.blend --python liner.py --python quality_cli.py -- job.json
"""
import bpy, bmesh, os

STYLES = {
    #            wall panel            dado                  overhead light colour
    'white':    ((0.62, 0.64, 0.64), (0.050, 0.055, 0.060), (1.00, 0.93, 0.84)),
    'slate':    ((0.085, 0.14, 0.20), (0.030, 0.034, 0.040), (1.00, 0.95, 0.88)),
    'charcoal': ((0.040, 0.043, 0.048), (0.022, 0.023, 0.026), (0.86, 0.92, 1.00)),
}
ACCENT = (0.32, 0.39, 1.0)       # periwinkle #9AA8FF in linear light
X0, X1, Y0, Y1, F, WALL = -28.6, 25.6, -12.6, 12.6, 1.8, 10.8
T = 0.04                         # lining thickness
DADO, STRIPE = 3.0, 0.14         # dado top (m), stripe height
STRIPE_Z = 5.5                   # stripe sits above the packages (at 3 m the conveyor hid it)


def _mat(name, col, rough, seams=True):
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = next(n for n in nt.nodes if n.bl_idname == 'ShaderNodeBsdfPrincipled')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    # tonal variation + scuffs (object coords = world metres: the meshes are built in world space)
    nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 0.6; nz.inputs['Detail'].default_value = 6
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tc.outputs['Object'], sep.inputs[0])
    def math(op, a, b=None):
        n = nt.nodes.new('ShaderNodeMath'); n.operation = op
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                nt.links.new(v, n.inputs[i])
        return n.outputs[0]
    fac = math('ADD', 0.80, math('MULTIPLY', nz.outputs['Fac'], 0.40))            # 0.8 .. 1.2
    if seams:
        # panel joints every 1.2 m along the wall (x + y covers both wall directions), thin dark line
        u = math('ADD', sep.outputs[0], sep.outputs[1])
        fr = math('FRACT', math('DIVIDE', u, 1.2))
        seam = math('LESS_THAN', fr, 0.012)
        fac = math('MULTIPLY', fac, math('SUBTRACT', 1.0, math('MULTIPLY', seam, 0.55)))
    # grime rising from the floor: darker in the first 0.8 m
    low = math('SUBTRACT', 1.0, math('MULTIPLY', math('SUBTRACT', 1.0, math('MINIMUM', math('DIVIDE', math('SUBTRACT', sep.outputs[2], F), 0.8), 1.0)), 0.35))
    fac = math('MULTIPLY', fac, low)
    mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0
    mix.inputs['A'].default_value = (*col, 1)
    comb = nt.nodes.new('ShaderNodeCombineColor')
    for i in range(3):
        nt.links.new(fac, comb.inputs[i])
    nt.links.new(comb.outputs[0], mix.inputs['B'])
    nt.links.new(mix.outputs['Result'], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = rough
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.25
    bump.inputs['Distance'].default_value = 0.01
    h = math('MULTIPLY', nz.outputs['Fac'], 0.3)
    if seams:
        # micro-ribbed insulated panels: a shallow rib every 10 cm, and the joint is a recessed groove
        rib = math('ABSOLUTE', math('SINE', math('MULTIPLY', u, 31.416)))
        h = math('SUBTRACT', math('ADD', h, math('MULTIPLY', rib, 0.5)), math('MULTIPLY', seam, 3.0))
    nt.links.new(h, bump.inputs['Height'])
    nt.links.new(bump.outputs[0], b.inputs['Normal'])
    return m


def _box(name, x0, x1, y0, y1, z0, z1, mat, coll):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x = x0 if v.co.x < 0 else x1
        v.co.y = y0 if v.co.y < 0 else y1
        v.co.z = z0 if v.co.z < 0 else z1
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def apply(style='white'):
    wall_c, dado_c, light_c = STYLES[style]
    coll = bpy.data.collections.get("Liner")
    if coll is None:
        coll = bpy.data.collections.new("Liner")
        bpy.context.scene.collection.children.link(coll)
    for ob in list(coll.objects):
        bpy.data.objects.remove(ob)
    mw = _mat("LinerWall", wall_c, 0.48)
    md = _mat("LinerDado", dado_c, 0.55)
    ms = _mat("LinerStripe", ACCENT, 0.4, seams=False)
    n = [0]

    def wall(axis, pos, a, b, z0, z1):
        """Lining on one wall segment. axis 'y': wall at y=pos spanning x a..b; axis 'x': wall at x=pos spanning y a..b.
        pos is the room-side face of the cladding; the lining sits T inside it."""
        inward = -1 if pos > 0 else 1
        lo, hi = sorted((pos, pos + inward * T))
        for (q0, q1, mat, extra) in ((z0, min(z1, DADO), md, 0.0), (DADO, STRIPE_Z, mw, 0.0),
                                     (STRIPE_Z, STRIPE_Z + STRIPE, ms, 0.004), (STRIPE_Z + STRIPE, z1, mw, 0.0)):
            q0, q1 = max(q0, z0), min(q1, z1)
            if q1 - q0 < 0.01:
                continue
            l2, h2 = (lo - extra, hi + extra)
            if axis == 'y':
                _box(f"Liner{n[0]}", a, b, l2, h2, q0, q1, mat, coll)
            else:
                _box(f"Liner{n[0]}", l2, h2, a, b, q0, q1, mat, coll)
            n[0] += 1

    # back wall (y = +12.6): below and above the window band (6.6 - 9.0)
    wall('y', Y1, X0, X1, F, 6.6)
    wall('y', Y1, X0, X1, 9.0, WALL)
    # west wall (x = -28.6): intake opening y -2.1..0.1, z 3.1..5.2
    wall('x', X0, Y0, -2.1, F, WALL)
    wall('x', X0, 0.1, Y1, F, WALL)
    wall('x', X0, -2.1, 0.1, F, 3.1)
    wall('x', X0, -2.1, 0.1, 5.2, WALL)
    # east wall (x = +25.6): door opening y -5..3 up to z 8.0
    wall('x', X1, Y0, -5.0, F, WALL)
    wall('x', X1, 3.0, Y1, F, WALL)
    wall('x', X1, -5.0, 3.0, 8.0, WALL)
    k = 0
    for lo in bpy.data.objects:
        if lo.type == 'LIGHT' and lo.name.startswith("HallLight"):
            lo.data.color = light_c
            k += 1
    print("LINER", style, "panels", n[0], "lights", k)
    return n[0]


if __name__ == "__main__" and os.environ.get('FACTORY_LINER'):
    apply(os.environ['FACTORY_LINER'])
