"""Fly-through camera for the Software Factory (standalone; run inside Blender on the saved scene).

Timing is tied to the line in interior.py: 24 fps, cycle 96 frames (line moves frames 0-30, robots weld
~43-78 of every cycle). Scene frame 1 = start of cycle 0, when the hero cube (Cube10) slides in from the wall.

Story: intake -> follow the hero cube to robot 1 (welds it as we pass) -> overtake, robot 2 welding the
cube ahead -> past robot 3 -> inspection gates -> out the east door over the server yard -> rise, orbit the
site counter-clockwise (silhouettes against the sunset on the south side) -> pull back to the poster frame.
"""
import bpy, math
from mathutils import Vector

C = (6.0, 2.0, 4.0)          # orbit centre (site)
R_ORB, Z_ORB = 92.0, 38.0


def orbit(a_deg, z=Z_ORB, r=R_ORB):
    a = math.radians(a_deg)
    return (C[0] + r * math.cos(a), C[1] + r * math.sin(a), z)


# (frame, camera position, look-at target, lens mm)
WAYPOINTS = [
    (1,   (-24.2, -3.6, 3.9),  (-29.0, -1.0, 4.1), 22),   # intake: the idea cube slides out of the wall
    (24,  (-24.6, -3.3, 4.2),  (-27.4, -1.0, 4.2), 22),
    (60,  (-26.4, -2.7, 5.4),  (-23.0, -1.0, 4.3), 22),   # swing round behind it; sparks down the line
    (96,  (-28.0, -1.1, 6.0),  (-20.0, -1.0, 4.4), 22),
    (126, (-24.6, -1.1, 6.2),  (-17.0, -0.8, 4.6), 22),   # line indexes: ride along behind the cube
    (140, (-22.2, -1.3, 6.4),  (-19.7, -0.6, 4.8), 22),   # robot 1 starts welding the hero cube
    (156, (-19.0, -1.6, 6.6),  (-14.5, -2.0, 4.9), 22),   # overtake; robot 2 welding the cube ahead
    (172, (-15.4, -1.2, 6.6),  (-11.5, -1.6, 4.5), 22),
    (192, (-10.6, -1.0, 6.3),  (-2.0, -1.0, 4.6), 22),    # past robot 3, speeding up
    (222, (-2.5, -1.0, 5.9),   (7.0, -1.0, 4.8), 22),
    (252, (5.5, -1.0, 5.6),    (16.0, -1.0, 4.8), 22),    # inspection gate 1 (x 4.5, beam at 6.8 m)
    (280, (13.5, -1.2, 5.6),   (24.0, -1.4, 4.9), 22),    # gate 2 (x 13)
    (306, (21.5, -1.6, 5.6),   (32.0, -2.0, 5.2), 22),
    (326, (27.5, -2.0, 5.8),   (40.0, -2.6, 6.0), 22),    # east door
    (350, (35.0, -2.6, 7.2),   (46.0, -2.6, 8.0), 24),    # over the server yard, between the modules
    (378, (44.0, -4.0, 14.0),  (34.0, 0.0, 5.0), 26),     # rise and pivot back to the building
    (410, orbit(5, 26, 70),    C, 28),
    (450, orbit(50, 33, 82),   C, 28),                     # north-east: silos and crane
    (490, orbit(100, 38, 90),  C, 28),
    (530, orbit(150, 40),      C, 28),                     # west: intake and hopper
    (570, orbit(200, 40),      C, 28),
    (610, orbit(250, 38),      C, 28),                     # south: crane + silos against the sunset
    (645, orbit(295, 36),      C, 30),                     # gatehouse and training pavilion
    (670, orbit(318, 36, 95),  C, 30),
    (730, (122.0, -122.0, 46.0), (0.0, 6.0, 6.0), 32),     # pull back to the poster frame
    (744, (124.0, -124.0, 46.5), (0.0, 6.0, 6.0), 32),
]


def catmull(ts, ps, t):
    """Time-parameterised (non-uniform) Catmull-Rom: C1-continuous through the waypoints."""
    n = len(ts)
    i = max(0, min(n - 2, max(k for k in range(n - 1) if ts[k] <= t)))
    t0, t1 = ts[i], ts[i + 1]
    p0, p1 = Vector(ps[i]), Vector(ps[i + 1])
    pm = Vector(ps[i - 1]) if i > 0 else p0 - (p1 - p0)
    tm = ts[i - 1] if i > 0 else t0 - (t1 - t0)
    p2 = Vector(ps[i + 2]) if i + 2 < n else p1 + (p1 - p0)
    t2 = ts[i + 2] if i + 2 < n else t1 + (t1 - t0)
    m1 = (p1 - pm) / (t1 - tm) * (t1 - t0)
    m2 = (p2 - p0) / (t2 - t0) * (t1 - t0)
    u = (t - t0) / (t1 - t0)
    h00, h10, h01, h11 = 2*u**3 - 3*u**2 + 1, u**3 - 2*u**2 + u, -2*u**3 + 3*u**2, u**3 - u**2
    return h00 * p0 + h10 * m1 + h01 * p1 + h11 * m2


def build_camera(name="FlyCam"):
    scn = bpy.context.scene
    ob = bpy.data.objects.get(name)
    if ob is None:
        cd = bpy.data.cameras.new(name)
        ob = bpy.data.objects.new(name, cd)
        scn.collection.objects.link(ob)
    ob.animation_data_clear()
    ob.data.animation_data_clear()
    cd = ob.data
    cd.clip_start = 0.05
    cd.clip_end = 3000
    cd.sensor_width = 36
    ts = [w[0] for w in WAYPOINTS]
    P = [w[1] for w in WAYPOINTS]
    T = [w[2] for w in WAYPOINTS]
    Ls = [(w[3], 0, 0) for w in WAYPOINTS]
    f0, f1 = ts[0], ts[-1]
    speeds = []
    prev = None
    for f in range(f0, f1 + 1):
        p = catmull(ts, P, f)
        tg = catmull(ts, T, f)
        lens = catmull(ts, Ls, f).x
        ob.location = p
        ob.rotation_euler = (tg - p).to_track_quat('-Z', 'Y').to_euler()
        cd.lens = lens
        ob.keyframe_insert('location', frame=f)
        ob.keyframe_insert('rotation_euler', frame=f)
        cd.keyframe_insert('lens', frame=f)
        if prev is not None:
            speeds.append((f, round((p - prev).length * scn.render.fps, 1)))
        prev = p.copy()
    for idb in (ob, cd):
        ad = idb.animation_data
        acts = [ad.action] if ad and ad.action else []
        for act in acts:
            fcs = list(getattr(act, 'fcurves', []))
            for layer in getattr(act, 'layers', []):
                for strip in layer.strips:
                    for cb in getattr(strip, 'channelbags', []):
                        fcs += list(cb.fcurves)
            for fc in fcs:
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'
    scn.camera = ob
    scn.frame_start, scn.frame_end = f0, f1
    return speeds


speeds = build_camera()
mx = max(speeds, key=lambda s: s[1])
print("CAMERA_DONE frames", bpy.context.scene.frame_start, bpy.context.scene.frame_end,
      "max speed m/s", mx, "interior max", max(s[1] for s in speeds if s[0] < 330))
