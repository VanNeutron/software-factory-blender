"""Fly-through camera v2 for the Software Factory: slow, calm, one continuous move.

Run inside Blender on the saved scene (after rebuild_cli.py):  blender -b software_factory.blend --python camera_v2.py

Story (owner's brief, 2026-11-10): start inside the hall, back by the front windows, watching the line; a slow
dolly + pan from left to right as the packages move down the line; out through the east door; hold on the
deployment (OPERATIONS) building as a package rolls in; then pull back gradually to the wide poster frame.

Smoothness: the waypoints only shape the path. Positions and look-at targets are sampled from a centripetal
Catmull-Rom spline, re-timed by a monotone (PCHIP) arc-length curve so speed never jumps or overshoots, then
Gaussian-smoothed per frame. Speeds, accelerations and pan rates are printed so they can be checked.

Line timing (interior.py): 24 fps, cycle 96 frames (index on cycle frames 0-30), NCYC 14 -> frames 1-1344.
"""
import bpy, math
from mathutils import Vector

FPS = 24
FILM = (25, 840)           # 816 frames = 34 s

# (frame, camera position, look-at target, lens mm). Hall: x -28.6..25.6, y -12.6..12.6 (front glass at -12.6),
# floor z 1.8, line at y -1 (packages 3.5-4.9 m), east door opening y -5..3, z < 7.1.
WAYPOINTS = [
    # 1. inside, back by the front windows: dolly left -> right while the packages index down the line
    (25,   (-23.0, -9.8, 4.5),  (-25.0, 0.0, 3.9), 30),
    (178,  (-6.0, -9.8, 4.5),   (-4.0, 0.0, 3.9),  30),
    (313,  (11.0, -9.8, 5.1),   (19.0, -0.5, 4.0), 28),   # 5.1: clears the bench monitors by > 1.4 m
    # 2. across the floor and out through the east door (beside the conveyor, under the shutter)
    (381,  (21.0, -5.6, 5.3),   (30.0, -1.5, 4.4), 26),
    (421,  (26.4, -3.0, 6.0),   (36.0, -1.2, 4.4), 24),
    # 3. the deployment building, kept short: one package rolls in (door cycle 471-517), OPERATIONS sign + board
    (470,  (30.5, -7.2, 8.0),   (37.5, -1.2, 4.6), 25),
    (520,  (32.2, -15.5, 9.2),  (41.5, -2.5, 6.6), 26),
    # 4. gradual pull back and rise to the wide poster frame, settle at the end
    (640,  (42.0, -31.0, 12.0), (28.0, -1.0, 6.0), 27),
    (745,  (53.5, -53.0, 18.8), (10.0, 2.0, 6.0),  29),
    (810,  (57.9, -61.9, 21.9), (2.4, 3.9, 6.0),   30),
    (840,  (58.4, -62.4, 22.05), (2.0, 4.0, 6.0),  30),
]
SIGMA = 8.0                # Gaussian smoothing (frames) applied to the sampled path


def centripetal(ps, n_per=400):
    """Dense polyline through ps (centripetal Catmull-Rom, alpha 0.5: no cusps or loops)."""
    P = [Vector(p) for p in ps]
    P = [P[0] + (P[0] - P[1])] + P + [P[-1] + (P[-1] - P[-2])]
    out, knots = [], [0]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        t0 = 0.0
        t1 = t0 + max((p1 - p0).length ** 0.5, 1e-4)
        t2 = t1 + max((p2 - p1).length ** 0.5, 1e-4)
        t3 = t2 + max((p3 - p2).length ** 0.5, 1e-4)
        for k in range(n_per):
            t = t1 + (t2 - t1) * k / n_per
            a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
            a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
            a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
            b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
            b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
            out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
        knots.append(len(out))
    out.append(P[-2].copy())
    return out, knots


def arclen(poly):
    s = [0.0]
    for a, b in zip(poly, poly[1:]):
        s.append(s[-1] + (b - a).length)
    return s


def pchip(xs, ys):
    """Monotone cubic interpolant (Fritsch-Carlson). End slopes 0 -> eased start and stop."""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    def f(x):
        i = max(0, min(n - 2, max(k for k in range(n - 1) if xs[k] <= x) if x >= xs[0] else 0))
        t = (x - xs[i]) / h[i]
        h00, h10, h01, h11 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t, -2*t**3 + 3*t**2, t**3 - t**2
        return h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]
    return f


def at_s(poly, s, q):
    """Point at arc length q."""
    lo, hi = 0, len(s) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if s[mid] <= q:
            lo = mid
        else:
            hi = mid
    u = 0.0 if s[hi] == s[lo] else (q - s[lo]) / (s[hi] - s[lo])
    return poly[lo].lerp(poly[hi], u)


def sample(ts, pts, frames):
    poly, knots = centripetal(pts)
    s = arclen(poly)
    f = pchip([float(t) for t in ts], [s[k] for k in knots])
    return [at_s(poly, s, min(max(f(fr), 0.0), s[-1])) for fr in frames]


def gauss(vals, sigma):
    """Gaussian smoothing with mirrored-free clamped ends (ends keep their exact value)."""
    n = len(vals)
    r = int(3 * sigma)
    w = [math.exp(-0.5 * (k / sigma) ** 2) for k in range(-r, r + 1)]
    out = []
    for i in range(n):
        acc, ws = vals[i] * 0, 0.0
        rr = min(r, i, n - 1 - i)            # shrink the window near the ends so they stay pinned
        for k in range(-rr, rr + 1):
            acc = acc + vals[i + k] * w[k + r]
            ws += w[k + r]
        out.append(acc / ws)
    return out


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
    cd.clip_start, cd.clip_end, cd.sensor_width = 0.05, 3000, 36
    ts = [w[0] for w in WAYPOINTS]
    frames = list(range(FILM[0], FILM[1] + 1))
    P = gauss(sample(ts, [w[1] for w in WAYPOINTS], frames), SIGMA)
    T = gauss(sample(ts, [w[2] for w in WAYPOINTS], frames), SIGMA)
    lens_f = pchip([float(t) for t in ts], [float(w[3]) for w in WAYPOINTS])
    stats = []
    prev_d = None
    prev_e = None
    for i, fr in enumerate(frames):
        p, tg = P[i], T[i]
        d = (tg - p).normalized()
        ob.location = p
        e = d.to_track_quat('-Z', 'Y').to_euler('XYZ', prev_e) if prev_e else d.to_track_quat('-Z', 'Y').to_euler()
        ob.rotation_euler = e
        prev_e = e.copy()
        cd.lens = lens_f(fr)
        ob.keyframe_insert('location', frame=fr)
        ob.keyframe_insert('rotation_euler', frame=fr)
        cd.keyframe_insert('lens', frame=fr)
        if i:
            v = (P[i] - P[i - 1]).length * FPS
            pan = math.degrees(prev_d.angle(d, 0.0)) * FPS
            stats.append((fr, v, pan))
        prev_d = d
    for idb in (ob, cd):
        ad = idb.animation_data
        for act in ([ad.action] if ad and ad.action else []):
            fcs = list(getattr(act, 'fcurves', []))
            for layer in getattr(act, 'layers', []):
                for strip in layer.strips:
                    for cb in getattr(strip, 'channelbags', []):
                        fcs += list(cb.fcurves)
            for fc in fcs:
                for kp in fc.keyframe_points:
                    kp.interpolation = 'LINEAR'
                fc.update()
    # keep Euler angles continuous (no 360 flips between frames)
    scn.camera = ob
    scn.frame_start, scn.frame_end = FILM
    return stats


def report(stats):
    acc = [(stats[i][0], abs(stats[i][1] - stats[i - 1][1]) * FPS) for i in range(1, len(stats))]
    for lo, hi, label in [(25, 313, "1 interior"), (313, 425, "2 exit"), (425, 520, "3 ops"), (520, 840, "4 pullback")]:
        seg = [s for s in stats if lo <= s[0] < hi]
        sa = [a for a in acc if lo <= a[0] < hi]
        print(f"CAM {label:11s} max speed {max(s[1] for s in seg):5.2f} m/s  mean {sum(s[1] for s in seg)/len(seg):5.2f}"
              f"  max pan {max(s[2] for s in seg):5.1f} deg/s  max accel {max(a[1] for a in sa):5.2f} m/s2")


if __name__ == "__main__":
    st = build_camera()
    report(st)
    print("CAMERA_DONE frames", bpy.context.scene.frame_start, bpy.context.scene.frame_end)
