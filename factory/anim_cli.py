"""Headless animation render: blender -b file --python anim_cli.py -- <json>
json: outdir, start, end, samples, pct, blur, cam {loc,target,lens}"""
import bpy, sys, json, time, os
from mathutils import Vector
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
# keep machine paths and hostnames out of image metadata
scn.render.use_stamp_filename = False
scn.render.use_stamp_hostname = False
scn.cycles.samples = a.get('samples', 32)
scn.render.resolution_percentage = a.get('pct', 50)
scn.render.use_motion_blur = bool(a.get('blur', True))
scn.render.motion_blur_shutter = a.get('shutter', 0.3)
c = a.get('cam')
if c:
    cam = bpy.data.objects.get('CliCam') or bpy.data.objects.new('CliCam', bpy.data.cameras.new('CliCam'))
    if cam.name not in scn.collection.objects:
        scn.collection.objects.link(cam)
    cam.data.lens = c.get('lens', 28)
    cam.location = c['loc']
    cam.rotation_euler = (Vector(c['target']) - Vector(c['loc'])).to_track_quat('-Z', 'Y').to_euler()
    scn.camera = cam
os.makedirs(a['outdir'], exist_ok=True)
scn.frame_start, scn.frame_end = a['start'], a['end']
for fr in range(1, a['start']):          # bring particle sims up to the first frame
    scn.frame_set(fr)
scn.render.filepath = os.path.join(a['outdir'], 'f_')
scn.render.image_settings.file_format = 'PNG'
t = time.time()
bpy.ops.render.render(animation=True)
print("ANIM_DONE", round(time.time() - t, 1))
