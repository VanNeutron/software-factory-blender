"""Fly-through camera for the Software Factory (standalone; run inside Blender on the saved scene).

Timing is tied to the line in interior.py: 24 fps, cycle 96 frames (line indexes on cycle frames 0-30).
The film runs scene frames 73-936 (36 s). The hero cube is Cube11: it waits in the intake tunnel, comes
through the roll-up door on frames ~108-115, rests, then rides into station 1 (frames 193-223), where the
handling robot lowers a steel cover over it (frames 241-257). The welders on stations 2 and 3 seam-weld the
cubes ahead as the camera overtakes, then it runs through the inspection gates, out of the east door, and
watches a finished package roll into the deployment building, sweeps over the roof, and makes a slow pass along
the front and its sign before it pulls back to the poster frame.
"""
import bpy, math
from mathutils import Vector

C = (6.0, 2.0, 4.0)          # orbit centre (site)
FILM = (73, 936)


def orbit(a_deg, z, r):
    a = math.radians(a_deg)
    return (C[0] + r * math.cos(a), C[1] + r * math.sin(a), z)


# (frame, camera position, look-at target, lens mm)
WAYPOINTS = [
    (73,  (-23.2, -5.0, 4.6),  (-28.6, -1.0, 4.3), 26),   # intake door closed, beacon starts at 87
    (100, (-23.6, -4.8, 4.7),  (-28.5, -1.0, 4.3), 26),   # door rolls up; the glass cube glides in (108-115)
    (130, (-24.2, -4.7, 5.0),  (-25.6, -1.0, 4.3), 26),
    (152, (-25.0, -5.0, 5.4),  (-21.5, -0.4, 4.8), 26),   # turn east: robot 1 lowers a cover on the cube ahead
    (180, (-25.0, -5.3, 5.6),  (-21.0, -0.4, 4.9), 26),
    (215, (-22.8, -5.0, 5.6),  (-19.8, 0.0, 5.0), 25),    # hero cube indexes into station 1
    (245, (-21.4, -4.6, 5.5),  (-20.0, 0.0, 5.3), 24),    # the cover comes down over the glass (241-257)
    (260, (-19.0, -5.4, 5.4),  (-14.4, -1.9, 3.9), 24),   # robot 2 welds the front seam of the cube ahead
    (272, (-16.4, -1.1, 7.1),  (-11.0, -1.2, 4.4), 26),   # over the line, between the welders
    (285, (-11.2, -1.0, 7.2),  (-7.2, -0.2, 4.0), 26),    # robot 3 welds the back seam
    (298, (-6.0, -1.0, 6.8),   (2.0, -1.0, 4.6), 25),
    (322, (-1.2, -1.3, 6.3),   (4.0, -1.0, 4.4), 24),    # slow down: gate 1 laser-scans the resting package
    (342, (2.4, -1.1, 6.15),   (9.0, -1.0, 4.6), 24),    # under gate 1 (x 4)
    (358, (8.8, -1.1, 6.0),    (16.0, -1.0, 4.8), 24),   # gate 2 (x 16): inspection cameras flash
    (374, (16.0, -1.4, 6.0),   (26.0, -1.8, 5.0), 24),    # gate 2 (x 16): inspection cameras flash, light turns green
    (396, (23.0, -1.8, 5.9),   (34.0, -2.3, 5.4), 24),
    (414, (28.5, -2.2, 6.0),   (40.0, -2.6, 5.6), 24),    # east door
    (440, (31.5, -5.4, 7.0),   (35.6, -1.2, 4.4), 24),    # out over the yard: a package waits at the deploy door
    (470, (31.2, -7.6, 7.6),   (35.4, -1.0, 4.5), 24),    # door rolls up (471-483), it rides in, status flashes
    (500, (33.0, -10.5, 9.5),  (41.5, -2.5, 6.8), 24),    # door closes; OPERATIONS sign and live board come into view
    (530, (40.0, -12.0, 17.0), (20.0, 0.0, 6.0), 26),     # rise, turn back to the building
    (565, (30.0, 2.0, 30.0),   (-10.0, 4.0, 6.0), 26),    # quick crane move over the roof towards the sunset
    (600, (-16.0, 2.0, 28.0),  (-28.0, -30.0, 6.0), 26),
    (640, (-46.0, -30.0, 15.0), (-16.0, -13.0, 7.0), 27),  # down past the intake building to the front
    (690, (-34.0, -40.0, 11.0), (-14.0, -13.0, 7.0), 28), # slow pass along the front facade
    (750, (-5.0, -42.0, 9.5),  (-1.5, -13.0, 9.0), 38),   # SOFTWARE FACTORY sign
    (805, (22.0, -46.0, 12.0), (5.0, -11.0, 7.0), 30),
    (850, (44.0, -53.0, 17.5), (4.0, 0.0, 6.0), 30),
    (890, (54.0, -58.0, 21.5), (2.0, 4.0, 6.0), 30),      # pull back to the poster frame
    (924, (58.0, -62.0, 22.0), (2.0, 4.0, 6.0), 30),
    (936, (58.4, -62.4, 22.05), (2.0, 4.0, 6.0), 30),
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
    scn.frame_start, scn.frame_end = FILM
    return speeds


speeds = build_camera()
mx = max(speeds, key=lambda s: s[1])
print("CAMERA_DONE frames", bpy.context.scene.frame_start, bpy.context.scene.frame_end,
      "max speed m/s", mx, "interior max", max(s[1] for s in speeds if s[0] < 414))
