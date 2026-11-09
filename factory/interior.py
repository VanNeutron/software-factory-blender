"""Interior of the Software Factory hall: six-axis welding robots (rigged, IK-animated, sparks),
indexed product line with cubes that are built up station by station, a scanned factory floor,
varied pallet loads, and overhead services.

Executed into the build_factory.py namespace (uses box, beam, cyl, light, link, grimy, emit,
plain, glass, A, F, ...). Entry point: build_interior(M).

Timing: 24 fps, one line cycle = 96 frames (4 s). Frames 0-30 the line indexes 6 m;
frames 30-96 the cubes rest and every robot welds the cube at its station.
"""
import bpy, bmesh, math, random
from mathutils import Vector, Matrix, Euler

FPS = 24
CYCLE = 96
MOVE = 30
NCYC = 8                      # 8 cycles = 768 frames (covers the 744-frame fly-through)
PITCH = 6.0
CUBE = 1.2
BELT_TOP = 3.52
STATIONS = [(-20.0, +1, 0), (-14.0, -1, 2), (-8.0, +1, 4)]   # (x, side: +1 back / -1 front, frame stagger)
ROBOT_Y = {+1: 1.95, -1: -3.95}
ROBOT_Z = 2.2

# link lengths (m) of the robot, matched in the geometry below
SH_R, SH_Z = 0.35, 1.17       # shoulder axis in the arm plane (forward, up) from the base origin
L1, L2, LT = 1.6, 1.7, 0.65   # upper arm, elbow->wrist, wrist->tool tip


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def tube(name, p, q, r0, r1, mat, sub, seg=32, parent=None, smooth_sides=True):
    """Cylinder/cone from p to q (local coords if parent given)."""
    p, q = Vector(p), Vector(q)
    d = q - p
    L = d.length
    rot = d.normalized().to_track_quat('Z', 'Y').to_matrix().to_4x4()
    m = Matrix.Translation((p + q) / 2) @ rot
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r0, radius2=r1, depth=L, matrix=m)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = smooth_sides and abs(poly.normal.dot(d.normalized())) < 0.9
    ob = bpy.data.objects.new(name, me)
    if mat:
        me.materials.append(mat)
    link(ob, sub)
    if parent:
        ob.parent = parent
    return ob


def frustum(name, p, q, w0, h0, w1, h1, mat, sub, parent=None, bevel=0.03, up=Vector((1, 0, 0))):
    """Tapered box from p (section w0 x h0) to q (w1 x h1). 'up' picks the w axis."""
    p, q = Vector(p), Vector(q)
    d = (q - p).normalized()
    a = up - d * up.dot(d)
    if a.length < 1e-4:
        a = Vector((0, 1, 0)) - d * d.y
    a.normalize()
    b = d.cross(a).normalized()
    vs = []
    for c, w, h in ((p, w0, h0), (q, w1, h1)):
        for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            vs.append(tuple(c + a * s * w / 2 + b * t * h / 2))
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    ob = mesh_obj(name, vs, faces, mat, sub, bevel)
    me = ob.data
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    if parent:
        ob.parent = parent
    return ob


def pbox(name, x0, x1, y0, y1, z0, z1, mat, sub, parent=None, bevel=0.02):
    ob = box(name, x0, x1, y0, y1, z0, z1, mat, sub, bevel)
    if parent:
        ob.parent = parent
    return ob


def empty(name, parent, loc, sub, size=0.2):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = size
    e.empty_display_type = 'ARROWS'
    e.location = loc
    link(e, sub)
    if parent:
        e.parent = parent
    return e

# --------------------------------------------------------------------------
# materials
# --------------------------------------------------------------------------

def robot_materials(M):
    R = {}
    R['paint'] = grimy("RobotOrange", (0.72, 0.2, 0.018), metallic=0.05, rough=0.32, var=0.12, streak=0.3,
                       rust=0.04, bump=0.04)
    R['dark'] = grimy("RobotGraphite", (0.035, 0.036, 0.04), metallic=0.4, rough=0.45, var=0.15, streak=0.2, bump=0.05)
    R['steel'] = grimy("RobotSteel", (0.5, 0.5, 0.52), metallic=1.0, rough=0.28, var=0.12, streak=0.15, bump=0.03)
    R['copper'] = plain("Copper", (0.62, 0.3, 0.16), 1.0, 0.3)
    R['hose'] = plain("HoseBlack", (0.012, 0.012, 0.013), 0.0, 0.55)
    R['cable_grey'] = plain("CableGrey", (0.12, 0.12, 0.13), 0.0, 0.5)
    R['cable_yel'] = plain("CableYellow", (0.55, 0.38, 0.02), 0.0, 0.5)
    R['spark'] = emit("Spark", (1.0, 0.36, 0.06), 45)
    R['arc'] = emit("WeldArc", (0.75, 0.85, 1.0), 120)
    R['stack_g'] = emit("StackGreen", (0.1, 1.0, 0.25), 12)
    R['stack_a'] = plain("StackAmberOff", (0.4, 0.22, 0.02), 0.0, 0.2)
    R['stack_r'] = plain("StackRedOff", (0.35, 0.02, 0.02), 0.0, 0.2)
    R['idea_core'] = emit("IdeaCore", (0.16, 0.22, 1.0), 2.2)
    R['idea_shell'] = frosted("IdeaShell")
    R['frame'] = grimy("CubeFrame", (0.09, 0.095, 0.1), metallic=0.9, rough=0.35, var=0.15, streak=0.1, bump=0.05)
    R['panel'] = M['galv']
    R['seam'] = emit("SeamGlow", (0.16, 0.22, 1.0), 3)
    R['hazard'] = hazard_mat()
    R['mesh'] = wire_mesh_mat()
    R['wrap'] = wrap_mat()
    R['wood'] = wood_mat()
    R['checker'] = M['steel']
    return R


def frosted(name):
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0.55, 0.6, 1.0, 1)
    b.inputs['Transmission Weight'].default_value = 1.0
    b.inputs['Roughness'].default_value = 0.12
    b.inputs['IOR'].default_value = 1.45
    return m


def hazard_mat():
    m, nt, b = A['new_mat']("HazardStripe")
    v = A['coords'](nt)
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(v, sep.inputs[0])
    s = A['math_'](nt, 'ADD', sep.outputs[0], sep.outputs[1])
    s = A['math_'](nt, 'SINE', A['math_'](nt, 'MULTIPLY', s, math.pi / 0.25))
    stripe = A['math_'](nt, 'GREATER_THAN', s, 0.0)
    wear = A['to_bw'](nt, A['ramp'](nt, A['noise'](nt, v, 3.0, 8, 0.7), 0.35, 0.6))
    col = A['mixc'](nt, (0.02, 0.02, 0.02), (0.65, 0.45, 0.02), stripe)
    col = A['mixc'](nt, (0.12, 0.115, 0.11), col, wear)
    nt.links.new(col, b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.55
    return m


def wire_mesh_mat():
    """Safety fence panel: square wire mesh via alpha, painted yellow-grey."""
    m, nt, b = A['new_mat']("FenceMesh")
    v = A['coords'](nt)
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(v, sep.inputs[0])
    def grid(c):
        f = A['math_'](nt, 'FRACT', A['math_'](nt, 'DIVIDE', c, 0.05))
        return A['math_'](nt, 'LESS_THAN', A['math_'](nt, 'ABSOLUTE', A['math_'](nt, 'SUBTRACT', f, 0.5)), 0.08)
    h = A['math_'](nt, 'ADD', sep.outputs[0], sep.outputs[1])
    a = A['math_'](nt, 'MAXIMUM', grid(h), grid(sep.outputs[2]), clamp=True)
    b.inputs['Base Color'].default_value = (0.35, 0.32, 0.05, 1)
    b.inputs['Metallic'].default_value = 0.4
    b.inputs['Roughness'].default_value = 0.5
    nt.links.new(a, b.inputs['Alpha'])
    return m


def wrap_mat():
    m, nt, b = A['new_mat']("ShrinkWrap")
    v = A['coords'](nt)
    b.inputs['Base Color'].default_value = (0.8, 0.82, 0.85, 1)
    b.inputs['Transmission Weight'].default_value = 0.85
    b.inputs['IOR'].default_value = 1.4
    try:
        b.inputs['Thin Wall'].default_value = True
    except Exception:
        pass
    r = A['ramp'](nt, A['noise'](nt, v, 4.0, 6, 0.6), 0.3, 0.7, (0.08,) * 3, (0.35,) * 3)
    nt.links.new(A['to_bw'](nt, r), b.inputs['Roughness'])
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs['Strength'].default_value = 0.6
    nt.links.new(A['noise'](nt, v, 9.0, 4, 0.5), bp.inputs['Height'])
    nt.links.new(bp.outputs[0], b.inputs['Normal'])
    return m


def wood_mat():
    m, nt, b = A['new_mat']("PalletWood")
    v = A['coords'](nt)
    lay = A['sample'](nt, 'weathered_brown_planks', v, 1.8)
    A['finish'](nt, b, lay, bump=0.4, vec=v, macro=0.3)
    return m


def floor_mat():
    """Hall floor: two scanned concrete floors, saw-cut joints every 6 m, worn painted walkway lines,
    forklift tyre tracks, oil stains near the line."""
    m, nt, b = A['new_mat']("HallFloorPBR")
    v = A['coords'](nt)
    a = A['anti_tile'](nt, 'hangar_concrete_floor', v, 2.0)
    g = A['anti_tile'](nt, 'garage_floor', v, 1.89)
    lay = A['blend_layers'](nt, a, g, A['to_bw'](nt, A['ramp'](nt, A['noise'](nt, v, 0.05, 4, 0.6), 0.4, 0.6)))
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(v, sep.inputs[0])
    X, Y = sep.outputs[0], sep.outputs[1]

    def band(c, lo, hi, soft=0.01):
        return A['math_'](nt, 'MULTIPLY',
                          A['math_'](nt, 'SMOOTH_MIN', 1.0, A['math_'](nt, 'GREATER_THAN', c, lo)),
                          A['math_'](nt, 'LESS_THAN', c, hi), clamp=True)

    # saw-cut joints
    def joint(c, pitch):
        f = A['math_'](nt, 'FRACT', A['math_'](nt, 'DIVIDE', c, pitch))
        return A['math_'](nt, 'LESS_THAN', A['math_'](nt, 'ABSOLUTE', A['math_'](nt, 'SUBTRACT', f, 0.5)), 0.012 / pitch * 2)
    jm = A['math_'](nt, 'MAXIMUM', joint(A['math_'](nt, 'ADD', X, 3.0), 6.0), joint(Y, 6.5), clamp=True)
    # walkway lines (yellow) either side of the line and along the front aisle, worn away
    wear = A['to_bw'](nt, A['ramp'](nt, A['noise'](nt, v, 2.2, 8, 0.7), 0.3, 0.62))
    lines = 0.0
    for y0 in (-3.15, 1.0, -7.2, -7.0):
        bl = A['math_'](nt, 'MULTIPLY', A['math_'](nt, 'GREATER_THAN', Y, y0), A['math_'](nt, 'LESS_THAN', Y, y0 + 0.1), clamp=True)
        lines = bl if isinstance(lines, float) else A['math_'](nt, 'MAXIMUM', lines, bl, clamp=True)
    lines = A['math_'](nt, 'MULTIPLY', lines, wear, clamp=True)
    # tyre tracks: two dark bands along the forklift aisle (y -8.6 .. -5.4), streaky in x
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (0.08, 3.0, 1.0)
    nt.links.new(v, mp.inputs['Vector'])
    streak = A['to_bw'](nt, A['ramp'](nt, A['noise'](nt, mp.outputs[0], 1.0, 6, 0.6), 0.45, 0.7))
    tyre = 0.0
    for yc in (-6.4, -5.2, -10.2, -11.4):
        t = A['math_'](nt, 'MULTIPLY', A['math_'](nt, 'GREATER_THAN', Y, yc - 0.18), A['math_'](nt, 'LESS_THAN', Y, yc + 0.18), clamp=True)
        tyre = t if isinstance(tyre, float) else A['math_'](nt, 'MAXIMUM', tyre, t, clamp=True)
    tyre = A['math_'](nt, 'MULTIPLY', tyre, streak, clamp=True)
    # oil stains: blobs, denser near the line (|y+1| < 4)
    oil = A['to_bw'](nt, A['ramp'](nt, A['noise'](nt, v, 0.9, 5, 0.6), 0.64, 0.7))
    near = A['math_'](nt, 'LESS_THAN', A['math_'](nt, 'ABSOLUTE', A['math_'](nt, 'ADD', Y, 1.0)), 4.5)
    oil = A['math_'](nt, 'MULTIPLY', oil, A['math_'](nt, 'ADD', 0.35, A['math_'](nt, 'MULTIPLY', near, 0.65)), clamp=True)
    col = A['hsv'](nt, lay.color, 0.5, 0.7, 0.75)
    col = A['mixc'](nt, col, (0.55, 0.4, 0.03), lines)
    col = A['mixc'](nt, col, A['_mul'](nt, col, A['ramp'](nt, tyre, 0, 1, (1, 1, 1), (0.35, 0.35, 0.35))), 1.0)
    col = A['mixc'](nt, col, (0.012, 0.011, 0.01), A['math_'](nt, 'MULTIPLY', oil, 0.85))
    col = A['mixc'](nt, col, (0.01, 0.01, 0.01), jm)
    lay.color = col
    r = A['to_bw'](nt, lay.rough)
    r = A['math_'](nt, 'MULTIPLY', r, 0.7)
    r = A['mixc'](nt, r, 0.08, A['math_'](nt, 'MULTIPLY', oil, 0.9), 'FLOAT')
    r = A['mixc'](nt, r, 0.6, lines, 'FLOAT')
    lay.rough = r
    lay.height = A['mixc'](nt, A['to_bw'](nt, lay.height), 0.0, jm, 'FLOAT')
    A['finish'](nt, b, lay, bump=0.5, bump_dist=0.01, vec=v, macro=0.2)
    return m

# --------------------------------------------------------------------------
# robot model + rig
# --------------------------------------------------------------------------

def make_robot(tag, x, side, R, sub):
    """Six-axis welding robot. Joints are empties: J1 yaw(Z), J2 pitch(X), J3 pitch(X), J4 roll(Y),
    J5 pitch(X), J6 roll(Y). Robot forward is local +Y."""
    y = ROBOT_Y[side]
    root = empty(f"{tag}_Root", None, (x, y, ROBOT_Z), sub, 0.6)
    root.rotation_euler = (0, 0, math.pi if side > 0 else 0.0)
    P, D, S, C = R['paint'], R['dark'], R['steel'], R['copper']
    # base
    tube(f"{tag}_Foot", (0, 0, 0), (0, 0, 0.08), 0.72, 0.72, D, sub, 48, root)
    for k in range(10):
        a = k / 10 * 2 * math.pi
        tube(f"{tag}_Bolt{k}", (0.63 * math.cos(a), 0.63 * math.sin(a), 0.08), (0.63 * math.cos(a), 0.63 * math.sin(a), 0.13), 0.035, 0.035, S, sub, 6, root)
    tube(f"{tag}_BaseHousing", (0, 0, 0.08), (0, 0, 0.5), 0.56, 0.5, P, sub, 48, root)
    pbox(f"{tag}_JunctionBox", -0.22, 0.22, -0.82, -0.48, 0.08, 0.46, D, sub, root, 0.03)
    for k, xx in enumerate((-0.12, 0.0, 0.12)):
        tube(f"{tag}_Connector{k}", (xx, -0.82, 0.3), (xx, -0.9, 0.3), 0.04, 0.04, S, sub, 12, root)
    # J1 turret
    j1 = empty(f"{tag}_J1", root, (0, 0, 0.5), sub)
    tube(f"{tag}_TurretRing", (0, 0, 0), (0, 0, 0.1), 0.53, 0.53, D, sub, 48, j1)
    pbox(f"{tag}_Turret", -0.46, 0.46, -0.5, 0.56, 0.1, 0.5, P, sub, j1, 0.08)
    for sx in (-1, 1):
        pbox(f"{tag}_Yoke{sx}", sx * 0.32 if sx > 0 else -0.5, 0.5 if sx > 0 else -0.32, 0.0, 0.62, 0.3, 0.95, P, sub, j1, 0.06)
        tube(f"{tag}_ShoulderBearing{sx}", (sx * 0.5, 0.35, 0.67), (sx * 0.58, 0.35, 0.67), 0.3, 0.3, D, sub, 40, j1)
    tube(f"{tag}_A2Motor", (0.58, 0.35, 0.67), (0.98, 0.35, 0.67), 0.17, 0.17, D, sub, 32, j1)
    tube(f"{tag}_A2Cap", (0.98, 0.35, 0.67), (1.03, 0.35, 0.67), 0.13, 0.1, S, sub, 24, j1)
    for k in range(4):
        tube(f"{tag}_A2Fin{k}", (0.64 + k * 0.08, 0.35, 0.67), (0.66 + k * 0.08, 0.35, 0.67), 0.19, 0.19, D, sub, 32, j1)
    tube(f"{tag}_A1Motor", (-0.3, -0.32, 0.5), (-0.3, -0.32, 0.95), 0.14, 0.14, D, sub, 24, j1)
    tube(f"{tag}_A1Cap", (-0.3, -0.32, 0.95), (-0.3, -0.32, 1.0), 0.11, 0.08, S, sub, 24, j1)
    pbox(f"{tag}_CBAnchor", -0.14, 0.14, -0.62, -0.38, 0.35, 0.72, D, sub, j1, 0.03)
    cb_a = empty(f"{tag}_CBa", j1, (0, -0.5, 0.62), sub, 0.1)
    # J2 upper arm
    j2 = empty(f"{tag}_J2", j1, (0, SH_R, SH_Z - 0.5), sub)
    tube(f"{tag}_ShoulderHub", (-0.32, 0, 0), (0.32, 0, 0), 0.33, 0.33, P, sub, 40, j2)
    frustum(f"{tag}_UpperArm", (0, 0, 0.1), (0, 0, L1 - 0.1), 0.46, 0.5, 0.36, 0.36, P, sub, j2, 0.07)
    tube(f"{tag}_ElbowHub", (-0.27, 0, L1), (0.27, 0, L1), 0.27, 0.27, P, sub, 40, j2)
    for sx in (-1, 1):
        pbox(f"{tag}_ArmCover{sx}", sx * 0.215 if sx > 0 else -0.235, 0.235 if sx > 0 else -0.215, -0.1, 0.1, 0.35, 1.25, D, sub, j2, 0.02)
    tube(f"{tag}_A3Motor", (-0.27, 0, L1), (-0.62, 0, L1), 0.15, 0.15, D, sub, 32, j2)
    tube(f"{tag}_A3Cap", (-0.62, 0, L1), (-0.67, 0, L1), 0.11, 0.09, S, sub, 24, j2)
    cb_b = empty(f"{tag}_CBb", j2, (0, -0.3, 0.55), sub, 0.1)
    pbox(f"{tag}_CBPin", -0.12, 0.12, -0.38, -0.18, 0.45, 0.65, D, sub, j2, 0.02)
    # counterbalance (gas spring): body on the turret, rod on the arm, each tracking the other
    body = tube(f"{tag}_CBBody", (0, 0, 0), (0, 0, 0.62), 0.11, 0.11, D, sub, 24, j1)
    body.location = (0, -0.5, 0.62)
    c = body.constraints.new('DAMPED_TRACK'); c.target = cb_b; c.track_axis = 'TRACK_Z'
    rod = tube(f"{tag}_CBRod", (0, 0, 0), (0, 0, 0.7), 0.045, 0.045, S, sub, 16, j2)
    rod.location = (0, -0.3, 0.55)
    c = rod.constraints.new('DAMPED_TRACK'); c.target = cb_a; c.track_axis = 'TRACK_Z'
    # J3 elbow + wrist motor pack (forearm along +Y)
    j3 = empty(f"{tag}_J3", j2, (0, 0, L1), sub)
    pbox(f"{tag}_ElbowPack", -0.3, 0.3, -0.62, 0.18, -0.26, 0.26, P, sub, j3, 0.07)
    for k, (mx, mz) in enumerate(((-0.14, 0.09), (0.14, 0.09), (0.0, -0.12))):
        tube(f"{tag}_WristMotor{k}", (mx, -0.62, mz), (mx, -0.92, mz), 0.085, 0.085, D, sub, 24, j3)
        tube(f"{tag}_WristMotorCap{k}", (mx, -0.92, mz), (mx, -0.96, mz), 0.065, 0.05, S, sub, 16, j3)
    tube(f"{tag}_ForearmCollar", (0, 0.18, 0), (0, 0.35, 0), 0.21, 0.2, D, sub, 40, j3)
    # J4 forearm roll
    j4 = empty(f"{tag}_J4", j3, (0, 0.35, 0), sub)
    tube(f"{tag}_Forearm", (0, 0, 0), (0, 1.12, 0), 0.18, 0.14, P, sub, 40, j4)
    for sx in (-1, 1):
        pbox(f"{tag}_WristFork{sx}", sx * 0.1 if sx > 0 else -0.17, 0.17 if sx > 0 else -0.1, 1.05, 1.42, -0.14, 0.14, P, sub, j4, 0.04)
    pbox(f"{tag}_WireFeeder", -0.13, 0.13, 0.25, 0.7, 0.16, 0.4, D, sub, j4, 0.03)
    tube(f"{tag}_WireSpool", (-0.12, 0.47, 0.42), (0.12, 0.47, 0.42), 0.13, 0.13, S, sub, 24, j4)
    # J5 wrist pitch
    j5 = empty(f"{tag}_J5", j4, (0, 1.35, 0), sub)
    tube(f"{tag}_WristHub", (-0.1, 0, 0), (0.1, 0, 0), 0.12, 0.12, D, sub, 32, j5)
    tube(f"{tag}_WristBody", (0, 0, 0), (0, 0.12, 0), 0.1, 0.09, P, sub, 32, j5)
    # J6 flange + MIG torch, tip at J5 + LT along +Y
    j6 = empty(f"{tag}_J6", j5, (0, 0.12, 0), sub)
    tube(f"{tag}_Flange", (0, 0, 0), (0, 0.03, 0), 0.1, 0.1, S, sub, 32, j6)
    pbox(f"{tag}_TorchMount", -0.05, 0.05, 0.03, 0.1, -0.07, 0.07, D, sub, j6, 0.01)
    tube(f"{tag}_TorchBody", (0, 0.1, 0), (0, 0.33, 0), 0.045, 0.04, D, sub, 24, j6)
    tube(f"{tag}_TorchInsul", (0, 0.33, 0), (0, 0.37, 0), 0.042, 0.042, R['cable_grey'], sub, 24, j6)
    tube(f"{tag}_TorchNeck", (0, 0.37, 0), (0, 0.46, 0), 0.032, 0.03, C, sub, 24, j6)
    tube(f"{tag}_Nozzle", (0, 0.46, 0), (0, LT - 0.12 - 0.01, 0), 0.03, 0.021, C, sub, 24, j6)
    tip = empty(f"{tag}_Tip", j6, (0, LT - 0.12, 0), sub, 0.05)
    J = dict(root=root, j1=j1, j2=j2, j3=j3, j4=j4, j5=j5, j6=j6, tip=tip)
    return J


def dress_pack(tag, J, R, sub):
    """Cable bundles routed along the arm; each control point is hooked to the link it rides on."""
    bpy.context.view_layer.update()
    route = [('root', (0.0, -0.9, 0.3)), ('root', (0.0, -1.05, 0.55)), ('j1', (0.0, -0.75, 0.85)),
             ('j1', (0.25, -0.15, 1.05)), ('j2', (0.3, -0.2, 0.35)), ('j2', (0.3, -0.25, 1.1)),
             ('j3', (0.22, -0.5, 0.32)), ('j3', (0.1, 0.1, 0.32)), ('j4', (0.05, 0.85, 0.24)),
             ('j5', (0.0, 0.0, 0.2)), ('j6', (0.0, 0.2, 0.09))]
    bundles = [(R['hose'], 0.045, (0.0, 0.0)), (R['cable_grey'], 0.026, (0.07, 0.03)), (R['cable_yel'], 0.018, (-0.06, 0.04))]
    for bi, (mat, rad, (ox, oz)) in enumerate(bundles):
        cu = bpy.data.curves.new(f"{tag}_Cable{bi}", 'CURVE')
        cu.dimensions = '3D'
        cu.bevel_depth = rad
        cu.bevel_resolution = 3
        cu.resolution_u = 10
        cu.use_fill_caps = True
        sp = cu.splines.new('BEZIER')
        n = len(route) if bi == 0 else len(route) - 1
        sp.bezier_points.add(n - 1)
        hooks = []
        for i in range(n):
            jn, lp = route[i]
            lp = Vector(lp) + Vector((ox, 0, oz))
            e = empty(f"{tag}_CH{bi}_{i}", J[jn], tuple(lp), sub, 0.03)
            hooks.append(e)
        bpy.context.view_layer.update()
        for i, e in enumerate(hooks):
            bp = sp.bezier_points[i]
            bp.co = e.matrix_world.translation
            bp.handle_left_type = bp.handle_right_type = 'AUTO'
        cu.materials.append(mat)
        ob = bpy.data.objects.new(f"{tag}_Cable{bi}", cu)
        link(ob, sub)
        bpy.context.view_layer.update()
        for i, e in enumerate(hooks):
            md = ob.modifiers.new(f"H{i}", 'HOOK')
            md.object = e
            md.vertex_indices_set([3 * i, 3 * i + 1, 3 * i + 2])
            md.matrix_inverse = e.matrix_world.inverted()
            md.center = e.matrix_world.translation
    # cable clamps
    for jn, lp in (('j2', (0.3, -0.22, 0.35)), ('j2', (0.3, -0.25, 1.1)), ('j4', (0.05, 0.85, 0.24))):
        pbox(f"{tag}_Clamp{jn}{lp[2]}", lp[0] - 0.1, lp[0] + 0.1, lp[1] - 0.07, lp[1] + 0.07, lp[2] - 0.08, lp[2] + 0.1, R['dark'], sub, J[jn], 0.02)
    # floor hose from the junction box into a floor duct
    root = J['root']
    tube(f"{tag}_FloorHose", (0, -0.86, 0.12), (0, -1.9, -0.37), 0.05, 0.05, R['hose'], sub, 12, root)


def ik(J, P, psi):
    """Joint angles that put the tool tip at world point P with tool pitch psi (rad, from horizontal; negative = down)."""
    root = J['root']
    p = root.matrix_world.inverted() @ Vector(P)
    yaw = math.atan2(-p.x, p.y)
    r, z = math.hypot(p.x, p.y), p.z
    wr, wz = r - LT * math.cos(psi), z - LT * math.sin(psi)
    dr, dz = wr - SH_R, wz - SH_Z
    d = min(math.hypot(dr, dz), L1 + L2 - 1e-4)
    a = math.atan2(dz, dr)
    cosb = (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)
    b = math.acos(max(-1, min(1, cosb)))
    el = a + b                                   # elbow-up
    er, ez = SH_R + L1 * math.cos(el), SH_Z + L1 * math.sin(el)
    a2 = math.atan2(er - SH_R, ez - SH_Z)         # from vertical, + leans forward
    phi = math.atan2(wz - ez, wr - er)            # forearm, from horizontal
    return yaw, a2, phi, psi


def pose(J, ang, frame, roll=0.0):
    yaw, a2, phi, psi = ang
    J['j1'].rotation_euler = (0, 0, yaw)
    J['j2'].rotation_euler = (-a2, 0, 0)
    J['j3'].rotation_euler = (phi + a2, 0, 0)
    J['j4'].rotation_euler = (0, roll, 0)
    J['j5'].rotation_euler = (psi - phi, 0, 0)
    for k in ('j1', 'j2', 'j3', 'j4', 'j5'):
        J[k].keyframe_insert('rotation_euler', frame=frame)


def robot_track(x, side, stagger):
    """Waypoints for one cycle: list of (t0, t1, from, to, weld) in cycle frames; points are (x, y, z, psi)."""
    edge = -0.4 if side > 0 else -1.6
    out = 0.02 * (1 if side > 0 else -1)
    top = BELT_TOP + CUBE + 0.025
    tilt = -math.radians(62)
    home = (x - 0.2, edge + side * 1.1, top + 1.1, -math.radians(35))
    a1 = (x - 0.48, edge + out, top + 0.3, tilt)
    s1 = (x - 0.48, edge + out, top, tilt)
    e1 = (x + 0.48, edge + out, top, tilt)
    l1 = (x + 0.48, edge + side * 0.25, top + 0.25, tilt)
    s2 = (x + 0.62, edge + side * 0.05, top - 0.12, -math.radians(28))
    e2 = (x + 0.62, edge + side * 0.05, BELT_TOP + 0.15, -math.radians(22))
    s = stagger
    return [(0, 30 + s, home, home, False), (30 + s, 40 + s, home, a1, False), (40 + s, 43 + s, a1, s1, False),
            (43 + s, 58 + s, s1, e1, True), (58 + s, 61 + s, e1, l1, False), (61 + s, 66 + s, l1, s2, False),
            (66 + s, 78 + s, s2, e2, True), (78 + s, 90 + s, e2, home, False), (90 + s, CYCLE, home, home, False)]


def lerp4(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))


def animate_robot(J, x, side, stagger, R, sub, tag):
    track = robot_track(x, side, stagger)
    welds = []
    for n in range(NCYC):
        base = 1 + n * CYCLE
        for (t0, t1, a, b, weld) in track:
            step = 1 if weld else 2
            for t in range(t0, t1, step):
                u = (t - t0) / max(1, (t1 - t0))
                u = u if weld else smooth(u)
                p = lerp4(a, b, u)
                roll = 0.05 * math.sin((base + t) * 0.07)
                pose(J, ik(J, p[:3], p[3]), base + t, roll)
            if weld:
                welds.append((base + t0, base + t1))
    # linear keys (dense samples)
    for k in ('j1', 'j2', 'j3', 'j4', 'j5'):
        ad = J[k].animation_data
        if ad and ad.action:
            for fc in fcurves_of(ad.action):
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'
    return welds


def fcurves_of(action):
    """Blender 5 layered actions: fcurves live in channelbags."""
    out = []
    if hasattr(action, 'fcurves') and len(getattr(action, 'fcurves', [])):
        return list(action.fcurves)
    for layer in getattr(action, 'layers', []):
        for strip in layer.strips:
            for cb in getattr(strip, 'channelbags', []):
                out += list(cb.fcurves)
    return out


def weld_fx(tag, J, welds, R, sub, spark_obj):
    rnd = random.Random(hash(tag) & 0xffff)
    tip = J['tip']
    # arc glow + light
    arc = tube(f"{tag}_Arc", (0, -0.02, 0), (0, 0.03, 0), 0.03, 0.01, R['arc'], sub, 12, tip)
    lt = bpy.data.lights.new(f"{tag}_ArcLight", 'POINT')
    lt.color = (0.7, 0.8, 1.0)
    lt.shadow_soft_size = 0.02
    lo = bpy.data.objects.new(f"{tag}_ArcLight", lt)
    link(lo, sub)
    lo.parent = tip
    lo.location = (0, 0.06, 0)
    lt.energy = 0
    lt.keyframe_insert('energy', frame=1)
    arc_states = [(1, False)]
    for (f0, f1) in welds:
        lt.energy = 0
        lt.keyframe_insert('energy', frame=f0 - 1)
        arc_states += [(f0, True), (f1 + 1, False)]
        for f in range(f0, f1 + 1):
            lt.energy = rnd.uniform(600, 2200)
            lt.keyframe_insert('energy', frame=f)
            s = rnd.uniform(0.7, 1.4)
            arc.scale = (s, s, s)
            arc.keyframe_insert('scale', frame=f)
        lt.energy = 0
        lt.keyframe_insert('energy', frame=f1 + 1)
    key_visible([arc], arc_states)
    for idb in (lt, arc):
        ad = idb.animation_data
        for fc in fcurves_of(ad.action):
            for kp in fc.keyframe_points:
                kp.interpolation = 'CONSTANT'
    # spark emitter: a few verts at the tip, one particle system per weld
    me = bpy.data.meshes.new(f"{tag}_SparkEmitter")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.02)
    bm.to_mesh(me); bm.free()
    em = bpy.data.objects.new(f"{tag}_SparkEmitter", me)
    link(em, sub)
    em.parent = tip
    em.location = (0, 0.01, 0)
    for i, (f0, f1) in enumerate(welds):
        ps_mod = em.modifiers.new(f"Sparks{i}", 'PARTICLE_SYSTEM')
        ps = ps_mod.particle_system
        st = bpy.data.particles.new(f"{tag}_Sparks{i}")
        ps.settings = st
        ps.seed = rnd.randint(0, 9999)
        st.count = int((f1 - f0) * 45)
        st.frame_start = f0
        st.frame_end = f1
        st.lifetime = 12
        st.lifetime_random = 0.75
        st.emit_from = 'VERT'
        st.physics_type = 'NEWTON'
        st.normal_factor = 2.4
        st.factor_random = 3.2
        st.drag_factor = 0.0
        st.integrator = 'MIDPOINT'
        st.use_dynamic_rotation = False
        st.use_rotations = False
        st.render_type = 'OBJECT'
        st.instance_object = spark_obj
        st.particle_size = 1.0
        st.size_random = 0.6
        st.show_unborn = False
        st.use_dead = False
        st.effector_weights.gravity = 1.0
        st.mass = 1.0
    em.show_instancer_for_render = False
    em.show_instancer_for_viewport = False
    return em


def spark_object(R, sub):
    me = bpy.data.meshes.new("SparkStreak")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=0.006)
    bm.to_mesh(me); bm.free()
    me.materials.append(R['spark'])
    ob = bpy.data.objects.new("SparkStreak", me)
    link(ob, sub)
    ob.location = (0, 0, -50)          # parked below the floor
    ob.hide_render = False
    return ob


def robot_cell(tag, x, side, R, M, sub):
    y = ROBOT_Y[side]
    y0, y1 = (0.75, 3.3) if side > 0 else (-5.1, -2.55)
    pbox(f"{tag}_Riser", x - 1.05, x + 1.05, y0 + 0.05, y1 - 0.05, F, ROBOT_Z - 0.03, M['steel'], sub, None, 0.03)
    pbox(f"{tag}_RiserTop", x - 1.1, x + 1.1, y0, y1, ROBOT_Z - 0.03, ROBOT_Z, M['steel'], sub, None, 0.01)
    # floor hazard frame around the cell
    fy0, fy1 = (y0 - 0.4, y1 + 2.6) if side > 0 else (y0 - 2.4, y1 + 0.4)
    for (a0, a1, b0, b1) in ((x - 2.6, x + 2.6, fy0, fy0 + 0.15), (x - 2.6, x + 2.6, fy1 - 0.15, fy1),
                             (x - 2.6, x - 2.45, fy0, fy1), (x + 2.45, x + 2.6, fy0, fy1)):
        pbox(f"{tag}_Hazard{a0:.1f}{b0:.1f}", a0, a1, b0, b1, F + 0.03, F + 0.034, R['hazard'], sub, None, 0)
    # safety fence: mesh panels on the far side, posts
    fy = fy1 if side > 0 else fy0
    for k in range(5):
        xx = x - 2.5 + k * 1.25
        pbox(f"{tag}_FencePost{k}", xx - 0.04, xx + 0.04, fy - 0.04, fy + 0.04, F, F + 2.2, R['cable_yel'], sub, None, 0.005)
        if k < 4:
            pbox(f"{tag}_FencePanel{k}", xx + 0.05, xx + 1.2, fy - 0.01, fy + 0.01, F + 0.15, F + 2.1, R['mesh'], sub, None, 0)
            pbox(f"{tag}_FenceRail{k}", xx, xx + 1.25, fy - 0.025, fy + 0.025, F + 2.1, F + 2.16, R['cable_yel'], sub, None, 0.005)
    # stack light
    sx, sy = x + 2.3, (y1 + 0.3) if side > 0 else (y0 - 0.3)
    pbox(f"{tag}_StackPole", sx - 0.03, sx + 0.03, sy - 0.03, sy + 0.03, F, F + 2.4, R['dark'], sub, None, 0.005)
    for k, mat in enumerate((R['stack_g'], R['stack_a'], R['stack_r'])):
        tube(f"{tag}_Stack{k}", (sx, sy, F + 2.4 + k * 0.14), (sx, sy, F + 2.52 + k * 0.14), 0.06, 0.06, mat, sub, 16)
    light(f"{tag}_StackGlow", 'POINT', (sx, sy, F + 2.45), 8, (0.1, 1.0, 0.25), size=0.05, sub=sub)
    # welding curtain behind the robot (red translucent strips)
    # controller cabinet
    cx0 = x - 2.2
    pbox(f"{tag}_Controller", cx0, cx0 + 0.8, (y1 - 0.6) if side > 0 else (y0), (y1) if side > 0 else (y0 + 0.6), F, F + 1.9, R['dark'], sub, None, 0.02)
    pbox(f"{tag}_ControllerScreen", cx0 + 0.15, cx0 + 0.65, ((y1 - 0.61) if side > 0 else (y0 + 0.6)), ((y1 - 0.6) if side > 0 else (y0 + 0.61)), F + 1.2, F + 1.55, M['screen'], sub, None, 0)

# --------------------------------------------------------------------------
# product cubes on the indexed line
# --------------------------------------------------------------------------

def cube_parts(name, R, sub, parent):
    h = CUBE / 2
    parts = {}
    parts['core'] = pbox(f"{name}_Core", -0.38, 0.38, -0.38, 0.38, 0.22, 0.98, R['idea_core'], sub, parent, 0.05)
    parts['shell'] = pbox(f"{name}_Shell", -h, h, -h, h, 0.0, CUBE, R['idea_shell'], sub, parent, 0.04)
    fr = []
    t = 0.06
    for sx in (-1, 1):
        for sy in (-1, 1):
            fr.append(pbox(f"{name}_PostE{sx}{sy}", sx * h - t if sx > 0 else -h, h if sx > 0 else -h + t,
                           sy * h - t if sy > 0 else -h, h if sy > 0 else -h + t, 0, CUBE, R['frame'], sub, parent, 0.01))
    for z0 in (0.0, CUBE - t):
        for sy in (-1, 1):
            fr.append(pbox(f"{name}_RailX{z0:.1f}{sy}", -h, h, sy * h - t if sy > 0 else -h, h if sy > 0 else -h + t, z0, z0 + t, R['frame'], sub, parent, 0.01))
        for sx in (-1, 1):
            fr.append(pbox(f"{name}_RailY{z0:.1f}{sx}", sx * h - t if sx > 0 else -h, h if sx > 0 else -h + t, -h, h, z0, z0 + t, R['frame'], sub, parent, 0.01))
    parts['frame'] = fr
    p = 0.03
    parts['panels_a'] = [pbox(f"{name}_PanelS", -h + t, h - t, -h - 0.005, -h + p, t, CUBE - t, R['panel'], sub, parent, 0.005),
                         pbox(f"{name}_PanelN", -h + t, h - t, h - p, h + 0.005, t, CUBE - t, R['panel'], sub, parent, 0.005)]
    parts['panels_b'] = [pbox(f"{name}_PanelW", -h - 0.005, -h + p, -h + t, h - t, t, CUBE - t, R['panel'], sub, parent, 0.005),
                         pbox(f"{name}_PanelE", h - p, h + 0.005, -h + t, h - t, t, CUBE - t, R['panel'], sub, parent, 0.005),
                         pbox(f"{name}_PanelTop", -h + t, h - t, -h + t, h - t, CUBE - p, CUBE + 0.005, R['panel'], sub, parent, 0.005)]
    parts['seam'] = [pbox(f"{name}_Seam{k}", -h - 0.008, h + 0.008, -h - 0.008, h + 0.008, z, z + 0.035, R['seam'], sub, parent, 0)
                     for k, z in enumerate((0.42,))]
    return parts


def merge(a, b):
    """AND of two step functions given as [(frame, bool), ...] sorted by frame."""
    def at(st, f):
        v = st[0][1]
        for (ff, vv) in st:
            if ff <= f:
                v = vv
        return v
    frames = sorted({f for f, _ in a} | {f for f, _ in b})
    out, prev = [], None
    for f in frames:
        v = at(a, f) and at(b, f)
        if v != prev:
            out.append((f, v))
            prev = v
    return out


def key_visible(objs, frames_states):
    """frames_states: list of (frame, visible) applied with constant interpolation."""
    for ob in objs:
        for f, vis in frames_states:
            ob.hide_render = not vis
            ob.hide_viewport = not vis
            ob.keyframe_insert('hide_render', frame=f)
            ob.keyframe_insert('hide_viewport', frame=f)


def build_line_cubes(R, sub):
    xs = [28.0 - PITCH * k for k in range(10 + NCYC + 1)]       # 28 .. -26 on the line, more queued behind the wall
    weld_done = {sx: (CYCLE - 18) + stg for (sx, side, stg) in STATIONS}   # cycle frame when station's 2nd weld ends
    for k, x0 in enumerate(xs):
        name = f"Cube{k:02d}"
        car = empty(name, None, (x0, -1.0, BELT_TOP), sub, 0.3)
        # motion: indexed moves
        car.location = (x0, -1.0, BELT_TOP)
        car.keyframe_insert('location', frame=1)
        for n in range(NCYC):
            f0 = 1 + n * CYCLE
            a, b = x0 + PITCH * n, x0 + PITCH * (n + 1)
            for t in range(0, MOVE + 1, 2):
                car.location = (a + (b - a) * smooth(t / MOVE), -1.0, BELT_TOP)
                car.keyframe_insert('location', frame=f0 + t)
        parts = cube_parts(name, R, sub, car)
        allp = [o for v in parts.values() for o in (v if isinstance(v, list) else [v])]
        # stage times: completion frame of the weld at each station (or 0 if before the shot)
        done = []
        for (sx, side, stg) in STATIONS:
            n = round((sx - x0) / PITCH) - 1
            if (sx - x0) % PITCH != 0 or (sx - x0) < 0:
                done.append(0 if sx < x0 else None)       # already past (before the shot) / never reaches
                continue
            done.append(0 if n < 0 else (1 + n * CYCLE + weld_done[sx]))
        def st(i, default_hidden=True):
            d = done[i]
            if d is None:
                return [(1, False)]
            if d == 0:
                return [(1, True)]
            return [(1, False), (d, True)]
        # whole cube hidden while inside the west wall or past the east end
        win = []
        prev = None
        for f in range(1, 1 + NCYC * CYCLE, 2):
            n = (f - 1) // CYCLE
            t = (f - 1) % CYCLE
            xx = x0 + PITCH * n + (PITCH * smooth(t / MOVE) if t <= MOVE else PITCH)
            v = -30.5 < xx < 33.8
            if v != prev:
                win.append((f, v))
                prev = v
        s0 = st(0)
        shell = [(f, not v) for (f, v) in s0]
        key_visible(parts['frame'], merge(st(0), win))
        key_visible(parts['panels_a'], merge(st(1), win))
        key_visible(parts['panels_b'] + parts['seam'], merge(st(2), win))
        key_visible([parts['shell']], merge(shell, win))
        key_visible([parts['core']], win)
        if car.animation_data:
            for fc in fcurves_of(car.animation_data.action):
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'
        for ob in allp:
            if ob.animation_data:
                for fc in fcurves_of(ob.animation_data.action):
                    for kp in fc.keyframe_points:
                        kp.interpolation = 'CONSTANT'


def roller_conveyor(R, M, sub):
    """Replace the belt: side frames, rollers every 0.3 m, motor drives, e-stop pull cord."""
    me = bpy.data.meshes.new("Roller")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.055, radius2=0.055, depth=1.7,
                          matrix=Matrix.Rotation(math.pi / 2, 4, 'X'))
    bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(R['steel'])
    x = -27.4
    while x < 33.4:
        ob = bpy.data.objects.new(f"Roller{x:.1f}", me)
        ob.location = (x, -1.0, BELT_TOP - 0.055)
        link(ob, sub)
        x += 0.3
    for k, xx in enumerate((-24.0, -11.0, 2.0, 15.0, 28.0)):
        pbox(f"DriveMotor{k}", xx - 0.3, xx + 0.3, -2.45, -2.02, 2.75, 3.25, R['dark'], sub, None, 0.03)
        tube(f"DriveMotorBody{k}", (xx, -2.25, 2.85), (xx, -2.25, 3.2), 0.16, 0.16, M['crane'], sub, 24)
    # e-stop pull cord with red pull-boxes
    beam("EStopCord", (-27.4, -2.12, 3.95), (24.5, -2.12, 3.95), 0.012, 0.012, R['stack_r'], sub, bevel=0)
    for k in range(6):
        xx = -26 + k * 10
        pbox(f"EStopBox{k}", xx - 0.12, xx + 0.12, -2.2, -2.05, 3.85, 4.05, R['stack_r'], sub, None, 0.01)

# --------------------------------------------------------------------------
# clutter: pallets and varied loads on the racks and floor
# --------------------------------------------------------------------------

def pallet(name, x, y, z, R, sub, rot=0.0):
    w, d = 1.2, 0.8
    parts = []
    for k in range(5):
        yy = -d / 2 + k * (d - 0.1) / 4
        parts.append(((-w / 2, w / 2, yy, yy + 0.1, 0.122, 0.144)))
    for k in range(3):
        xx = -w / 2 + k * (w - 0.1) / 2
        parts.append(((xx, xx + 0.1, -d / 2, d / 2, 0.022, 0.122)))
    for k in range(3):
        yy = -d / 2 + k * (d - 0.1) / 2
        parts.append(((-w / 2, w / 2, yy, yy + 0.1, 0.0, 0.022)))
    e = empty(name, None, (x, y, z), sub, 0.3)
    e.rotation_euler = (0, 0, rot)
    for i, (a0, a1, b0, b1, c0, c1) in enumerate(parts):
        pbox(f"{name}_b{i}", a0, a1, b0, b1, c0, c1, R['wood'], sub, e, 0.004)
    return e


def load_pallets(R, M, sub, rnd):
    boxes = A['variants']('cardboard_box_01')
    crates = A['variants']('wooden_crate_01') + A['variants']('wooden_crate_02', pattern=r'^wooden_crate_02', mode='one')
    pcrates = []
    for nm in ('plastic_crate_01', 'plastic_crate_02', 'plastic_crate_03'):
        try:
            pcrates += A['variants'](nm)
        except Exception:
            pass
    cans = []
    for nm in ('industrial_pastic_container', 'metal_jerrycan'):
        try:
            cans += A['variants'](nm)
        except Exception:
            pass
    slots = []
    for zz in (2.22, 3.72, 5.22, 6.72):
        for k in range(4):
            slots.append((-0.6 + k * 2.75 + 1.0, 9.6, zz))
    floor_slots = [(-26 + i * 1.5, 10.6, F + 0.0) for i in range(6)] + [(20 + i * 1.5, 10.8, F) for i in range(3)] + \
                  [(-27.5, -10.5 + i * 1.1, F) for i in range(4)]
    for i, (x, y, z) in enumerate(slots + floor_slots):
        if rnd.random() < 0.12:
            continue
        rot = rnd.uniform(-0.06, 0.06) + (math.pi / 2 if y < 0 else 0)
        p = pallet(f"Pallet{i}", x, y, z, R, sub, rot)
        kind = rnd.random()
        top = z + 0.144
        if kind < 0.45:          # stacked cardboard, uneven
            rows = rnd.randint(1, 3)
            for lvl in range(rows):
                for (bx, by) in ((-0.3, -0.2), (0.3, -0.2), (-0.3, 0.2), (0.3, 0.2)):
                    if rnd.random() < 0.15 and lvl == rows - 1:
                        continue
                    s = rnd.uniform(0.95, 1.25)
                    A['place'](rnd.choice(boxes), (x + bx + rnd.uniform(-0.03, 0.03), y + by + rnd.uniform(-0.03, 0.03), top + lvl * 0.36),
                               rot + rnd.uniform(-0.12, 0.12) + rnd.choice((0, math.pi / 2)), s, sub_coll(sub))
        elif kind < 0.65:        # shrink-wrapped load
            hgt = rnd.uniform(0.6, 1.15)
            pbox(f"Load{i}", -0.58, 0.58, -0.38, 0.38, 0.144, 0.144 + hgt, R['wrap'], sub, p, 0.06)
            pbox(f"LoadIn{i}", -0.55, 0.55, -0.35, 0.35, 0.145, 0.14 + hgt - 0.02, M['crate'], sub, p, 0.01)
        elif kind < 0.82 and crates:
            e = A['place'](rnd.choice(crates), (x, y, top), rot + rnd.uniform(-0.1, 0.1), rnd.uniform(1.0, 1.35), sub_coll(sub))
        elif pcrates:
            for lvl in range(rnd.randint(2, 4)):
                for bx in (-0.3, 0.3):
                    A['place'](rnd.choice(pcrates), (x + bx, y, top + lvl * 0.27), rot, 1.0, sub_coll(sub))
        if cans and rnd.random() < 0.15 and z < 2.5:
            A['place'](rnd.choice(cans), (x + 0.8, y + rnd.uniform(-0.3, 0.3), z), rnd.uniform(0, 6.28), 1.0, sub_coll(sub))


def sub_coll(sub):
    c = bpy.data.collections.get(sub)
    if c is None:
        c = bpy.data.collections.new(sub)
        coll().children.link(c)
    return c


def overhead(R, M, sub):
    """Services under the roof: cable trays, sprinkler/compressed-air pipes, a duct, hanging festoon."""
    for k, (yy, zz, w) in enumerate(((-4.5, 8.4, 0.6), (5.5, 8.6, 0.45))):
        pbox(f"TrayBase{k}", -28.4, 25.4, yy - w / 2, yy + w / 2, zz, zz + 0.02, M['galv'], sub, None, 0)
        for sgn in (-1, 1):
            pbox(f"TraySide{k}{sgn}", -28.4, 25.4, yy + sgn * w / 2 - 0.01, yy + sgn * w / 2 + 0.01, zz, zz + 0.12, M['galv'], sub, None, 0)
        for xx in FRAMES:
            beam(f"TrayHanger{k}_{xx:.0f}", (xx + 0.4, yy, zz), (xx + 0.4, yy, 10.6), 0.03, 0.03, M['steel'], sub, bevel=0)
    for k, (yy, zz, r, mat) in enumerate(((-9.0, 9.2, 0.09, R['stack_r']), (-8.6, 9.3, 0.06, M['crane']), (7.5, 9.1, 0.12, M['galv']))):
        tube(f"Pipe{k}", (-28.5, yy, zz), (25.5, yy, zz), r, r, mat, sub, 16)
        for xx in FRAMES:
            beam(f"PipeHanger{k}_{xx:.0f}", (xx + 0.6, yy, zz + r), (xx + 0.6, yy, 10.5), 0.02, 0.02, M['steel'], sub, bevel=0)
    tube("Duct", (-28.5, 2.8, 9.6), (25.5, 2.8, 9.6), 0.45, 0.45, M['galv'], sub, 32)
    for xx in range(-26, 25, 6):
        tube(f"DuctDrop{xx}", (xx, 2.8, 9.15), (xx, 2.8, 8.2), 0.18, 0.12, M['galv'], sub, 16)
    # zone signs 01-06 hanging over the line (periwinkle accent numerals are emissive tiles)
    for i, xx in enumerate((-24, -14, -4, 6, 15, 23)):
        pbox(f"ZoneSign{i}", xx - 0.9, xx + 0.9, -1.05, -0.95, 7.6, 8.3, R['dark'], sub, None, 0.01)
        pbox(f"ZoneSignBar{i}", xx - 0.75, xx - 0.45, -1.11, -1.05, 7.75, 8.15, R['seam'], sub, None, 0)
        beam(f"ZoneSignWireA{i}", (xx - 0.7, -1.0, 8.3), (xx - 0.7, -1.0, 9.5), 0.01, 0.01, M['steel'], sub, bevel=0)
        beam(f"ZoneSignWireB{i}", (xx + 0.7, -1.0, 8.3), (xx + 0.7, -1.0, 9.5), 0.01, 0.01, M['steel'], sub, bevel=0)


def floor_clutter(R, M, sub, rnd):
    """Gas cylinders, wire drums and hoses at each cell; parts bins."""
    for (x, side, stg) in STATIONS:
        y0 = 3.6 if side > 0 else -5.5
        for k in range(3):
            xx = x + 1.6 + k * 0.32
            tube(f"Gas{x}_{k}", (xx, y0, F), (xx, y0, F + 1.5), 0.11, 0.11, M['galv'] if k else R['stack_r'], sub, 20)
            tube(f"GasCap{x}_{k}", (xx, y0, F + 1.5), (xx, y0, F + 1.62), 0.07, 0.05, R['dark'], sub, 12)
        tube(f"WireDrum{x}", (x - 1.6, y0, F), (x - 1.6, y0, F + 0.85), 0.33, 0.33, R['dark'], sub, 32)
        tube(f"WireDrumLid{x}", (x - 1.6, y0, F + 0.85), (x - 1.6, y0, F + 0.95), 0.15, 0.1, R['cable_yel'], sub, 24)
    bins = A['variants']('plastic_crate_01')
    for i in range(14):
        x = rnd.uniform(-26, 22)
        y = rnd.choice((-6.9, 4.4)) + rnd.uniform(-0.2, 0.2)
        if any(abs(x - sx) < 2.8 for (sx, _, _) in STATIONS):
            continue
        A['place'](bins[0], (x, y, F), rnd.uniform(-0.2, 0.2), 1.0, sub_coll(sub))


def hall_haze(sub, density=0.0028):
    """Dusty air inside the hall: a volume box just inside the walls. Overlaps (adds to) the site haze."""
    m = bpy.data.materials.get("HallHaze")
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new("HallHaze")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    v = nt.nodes.new('ShaderNodeVolumePrincipled')
    v.inputs['Color'].default_value = (0.9, 0.85, 0.78, 1)
    v.inputs['Anisotropy'].default_value = 0.6
    # thicker near the floor and around the welding cells, thinner under the roof
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Object'], sep.inputs[0])
    fall = A['math_'](nt, 'SUBTRACT', 1.0, A['math_'](nt, 'DIVIDE', sep.outputs[2], 16.0), clamp=True)
    nz = A['noise'](nt, tc.outputs['Object'], 0.08, 3, 0.5)
    var = A['math_'](nt, 'ADD', 0.55, nz)
    dens = A['math_'](nt, 'MULTIPLY', A['math_'](nt, 'MULTIPLY', fall, var), density)
    nt.links.new(dens, v.inputs['Density'])
    nt.links.new(v.outputs[0], out.inputs['Volume'])
    ob = box("HallHazeVolume", -28.6, 25.6, -12.6, 12.6, F + 0.05, 13.3, m, sub, 0)
    ob.visible_shadow = False
    return ob


def sun_shafts(sub, az_deg=338.0, elev_deg=13.0, energy=7000):
    """Low sunset light raking through the back (+Y) window band. The real sun is hidden by the tree line at
    2 degrees, so these hidden area lights stand in for it (classic film cheat), aimed along the sun's azimuth."""
    r, e = math.radians(az_deg), math.radians(elev_deg)
    to_sun = Vector((math.sin(r) * math.cos(e), math.cos(r) * math.cos(e), math.sin(e)))
    rot = (-to_sun).to_track_quat('-Z', 'Y').to_euler()
    for i in range(6):
        xc = (FRAMES[i] + FRAMES[i + 1]) / 2
        p = Vector((xc, 13.0, 7.8)) + to_sun * 6.0
        ld = bpy.data.lights.new(f"SunShaft{i}", 'AREA')
        ld.shape = 'RECTANGLE'
        ld.size, ld.size_y = 8.6, 2.6
        ld.energy = energy
        ld.color = (1.0, 0.52, 0.22)
        ld.spread = math.radians(6)
        ob = bpy.data.objects.new(f"SunShaft{i}", ld)
        ob.location = p
        ob.rotation_euler = rot
        ob.visible_camera = False
        ob.visible_glossy = False
        link(ob, sub)


def build_interior(M):
    S = "Interior"
    rnd = random.Random(21)
    scn = bpy.context.scene
    scn.render.fps = FPS
    scn.frame_start = 1
    scn.frame_end = 600
    R = robot_materials(M)
    # floor
    fl = bpy.data.objects.get("HallFloor")
    if fl:
        fl.data.materials.clear()
        fl.data.materials.append(floor_mat())
    roller_conveyor(R, M, S)
    spark = spark_object(R, S)
    for i, (x, side, stg) in enumerate(STATIONS):
        tag = f"Robot{i + 1}"
        J = make_robot(tag, x, side, R, S)
        dress_pack(tag, J, R, S)
        welds = animate_robot(J, x, side, stg, R, S, tag)
        weld_fx(tag, J, welds, R, S, spark)
        robot_cell(tag, x, side, R, M, S)
    build_line_cubes(R, S)
    hall_haze(S)
    for lo in bpy.data.objects:
        if lo.name.startswith("HallLight") and lo.type == 'LIGHT':
            lo.data.spread = math.radians(70)
            lo.data.energy = 2800
    sun_shafts(S)
    load_pallets(R, M, S, rnd)
    overhead(R, M, S)
    floor_clutter(R, M, S, rnd)
    # collision for sparks
    for nm in ("HallFloor", "ConveyorFrame"):
        ob = bpy.data.objects.get(nm)
        if ob and not any(m.type == 'COLLISION' for m in ob.modifiers):
            ob.modifiers.new("Collision", 'COLLISION')
            ob.collision.damping_factor = 0.5
            ob.collision.friction_factor = 0.4
            ob.collision.thickness_outer = 0.02
    return True
