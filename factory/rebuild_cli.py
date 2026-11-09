# Headless rebuild: blender -b software_factory.blend --python rebuild_cli.py
import bpy, math
import os
exec(open(os.path.join(os.path.dirname(bpy.data.filepath), 'run.py')).read())
f = bpy.app.driver_namespace['factory']
n = f['build_all'](True)
for nm in ('Vegetation', 'Surroundings'):
    c = bpy.data.collections.get(nm)
    if c:
        c.hide_viewport = True
scn = bpy.context.scene
try:
    scn.render.compositor_device = 'CPU'
except Exception:
    pass
# particle sanity check over the first 2 cycles
bad = alive = 0
for fr in range(1, 200):
    scn.frame_set(fr)
    if fr % 10:
        continue
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in bpy.data.objects:
        if 'SparkEmitter' not in ob.name:
            continue
        for ps in ob.evaluated_get(dg).particle_systems:
            for p in ps.particles:
                if p.alive_state != 'ALIVE':
                    continue
                alive += 1
                if any(math.isnan(x) or math.isinf(x) or abs(x) > 200 for x in list(p.location) + list(p.velocity)):
                    bad += 1
scn.frame_set(1)
bpy.ops.wm.save_mainfile()
print("REBUILD_DONE objects", n, "glare", bpy.app.driver_namespace.get('glare'), "alive", alive, "bad", bad)
