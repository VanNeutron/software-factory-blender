"""Headless review stills: blender -b file --python stills_cli.py -- <json>
json: outdir, frames [list], samples, pct, blur. Steps the scene through every frame in order so particle
sims are valid, and renders only the listed frames."""
import bpy, sys, json, time, os
a = json.loads(sys.argv[sys.argv.index('--') + 1])
scn = bpy.context.scene
prefs = bpy.context.preferences.addons['cycles'].preferences
DEV = None
for dev in ('OPTIX', 'CUDA', 'METAL'):
    try:
        prefs.compute_device_type = dev
    except Exception:
        continue
    prefs.get_devices()
    if any(d.type == dev for d in prefs.devices):
        DEV = dev
        break
for d in prefs.devices:
    d.use = (d.type == DEV)
print("DEVICE", DEV)
scn.cycles.device = 'GPU'
scn.render.use_stamp_filename = False
scn.render.use_stamp_hostname = False
scn.cycles.samples = a.get('samples', 64)
scn.render.resolution_percentage = a.get('pct', 50)
scn.render.use_motion_blur = bool(a.get('blur', True))
scn.render.motion_blur_shutter = a.get('shutter', 0.3)
scn.render.image_settings.file_format = 'PNG'
os.makedirs(a['outdir'], exist_ok=True)
frames = sorted(a['frames'])
t0 = time.time()
for f in range(1, frames[-1] + 1):
    scn.frame_set(f)
    if f in frames:
        scn.render.filepath = os.path.join(a['outdir'], f"s_{f:04d}.png")
        t = time.time()
        bpy.ops.render.render(write_still=True)
        print("STILL", f, round(time.time() - t, 1))
print("STILLS_DONE", round(time.time() - t0, 1))
