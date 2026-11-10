"""Headless render helper: blender -b software_factory.blend --python render_cli.py -- <json>

json keys: out, frame, samples, pct, blur (bool), cam: {loc, target, lens} (optional, else scene camera),
           warm (int frames to step before the frame so particle sims are current when no bake exists)
"""
import bpy, sys, json, time
from mathutils import Vector

args = json.loads(sys.argv[sys.argv.index('--') + 1])
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
scn.cycles.samples = args.get('samples', 128)
scn.render.resolution_percentage = args.get('pct', 50)
scn.render.use_motion_blur = bool(args.get('blur', False))
scn.render.motion_blur_shutter = args.get('shutter', 0.3)
c = args.get('cam')
if c:
    cam = bpy.data.objects.get('CliCam') or bpy.data.objects.new('CliCam', bpy.data.cameras.new('CliCam'))
    if cam.name not in scn.collection.objects:
        scn.collection.objects.link(cam)
    cam.data.lens = c.get('lens', 28)
    cam.data.clip_end = 3000
    cam.location = c['loc']
    cam.rotation_euler = (Vector(c['target']) - Vector(c['loc'])).to_track_quat('-Z', 'Y').to_euler()
    scn.camera = cam
f = int(args['frame'])
w = int(args.get('warm', 0))
for fr in range(max(1, f - w), f + 1):
    scn.frame_set(fr)
scn.render.filepath = args['out']
t = time.time()
bpy.ops.render.render(write_still=True)
print("RENDER_DONE", round(time.time() - t, 1), args['out'])
