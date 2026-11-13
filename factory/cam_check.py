"""Camera clearance check: blender -b software_factory.blend --python cam_check.py
Every 2 frames of the film, cast rays in 14 directions from the scene camera; report hits closer than 1.5 m."""
import bpy, math
from mathutils import Vector
scn = bpy.context.scene
cam = scn.camera
dirs = [Vector(d).normalized() for d in [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
        (1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1), (-1, 1, 1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)]]
worst = []
for f in range(scn.frame_start, scn.frame_end + 1):     # step every frame so particles/anim stay valid
    scn.frame_set(f)
    if f % 2:
        continue
    dg = bpy.context.evaluated_depsgraph_get()
    p = cam.matrix_world.translation.copy()
    best = (99.0, None)
    for d in dirs:
        hit, loc, nrm, idx, ob, _ = scn.ray_cast(dg, p, d, distance=1.5)
        if hit:
            dist = (loc - p).length
            if dist < best[0]:
                best = (dist, ob.name)
    if best[1]:
        worst.append((f, round(best[0], 2), best[1]))
for w in worst:
    print("NEAR", *w)
print("CHECK_DONE near_frames", len(worst), "min", min((w[1] for w in worst), default=None))
