"""Headless quality render (tests and finals): blender -b file --python quality_cli.py -- <json>

json keys:
  outdir                      output folder
  frames [list] | start,end   frames to render (a range renders every frame; existing files are skipped -> resumable)
  res [w, h]                  output size in pixels (default 1920x1080)
  samples                     max samples (default 1024)
  threshold                   adaptive noise threshold (default 0.004)
  min_samples                 adaptive min samples (default 64)
  animated_seed               bool (default True): noise moves with time instead of sticking to the screen
  pattern                     'BLUE_NOISE' | 'TABULATED_SOBOL' | 'AUTOMATIC' (default BLUE_NOISE)
  clamp_indirect              (default 10)
  blur, shutter               motion blur (default True, 0.15: labels stay readable at the v2 camera speed)
  fmt                         'PNG16' (default) | 'PNG8' | 'EXR'
  prefix                      file prefix (default 'f_')
  use_cpu, persistent         benchmark switches: GPU+CPU hybrid rendering; persistent data between frames
Steps the scene through every frame from 1 in order so particle sims are valid.
"""
import bpy, sys, json, time, os
_arg = sys.argv[sys.argv.index('--') + 1]
a = json.load(open(_arg)) if _arg.endswith('.json') else json.loads(_arg)   # a .json path avoids cmd.exe quoting
scn = bpy.context.scene
cy = scn.cycles
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
    d.use = (d.type == DEV) or (bool(a.get('use_cpu', False)) and d.type == 'CPU')   # use_cpu: GPU + CPU hybrid
print("DEVICE", DEV, [(d.name, d.type) for d in prefs.devices if d.use])
cy.device = 'GPU'
scn.render.use_persistent_data = bool(a.get('persistent', False))   # keep BVH/textures in memory between frames
scn.render.use_stamp_filename = False
scn.render.use_stamp_hostname = False

w, h = a.get('res', [1920, 1080])
scn.render.resolution_x, scn.render.resolution_y = int(w), int(h)
scn.render.resolution_percentage = 100
cy.samples = int(a.get('samples', 1024))
cy.use_adaptive_sampling = True
cy.adaptive_threshold = float(a.get('threshold', 0.004))
cy.adaptive_min_samples = int(a.get('min_samples', 64))
cy.use_animated_seed = bool(a.get('animated_seed', True))
try:
    cy.sampling_pattern = a.get('pattern', 'BLUE_NOISE')
except Exception as e:
    print("PATTERN_FAIL", e)
cy.sample_clamp_indirect = float(a.get('clamp_indirect', 10.0))
if 'volume_bounces' in a:
    cy.volume_bounces = int(a['volume_bounces'])
if 'volume_biased' in a and hasattr(cy, 'volume_biased'):
    cy.volume_biased = bool(a['volume_biased'])
# look overrides for A/B tests (the build scripts hold the real values)
if 'hall_haze_mul' in a:
    nt = bpy.data.materials['HallHaze'].node_tree
    vol = next(n for n in nt.nodes if n.bl_idname == 'ShaderNodeVolumePrincipled')
    mnode = vol.inputs['Density'].links[0].from_node
    k = next(i for i in mnode.inputs[:2] if not i.is_linked)
    k.default_value *= float(a['hall_haze_mul'])
    print("HALL_HAZE", k.default_value)
if 'shaft_mul' in a:
    for l in bpy.data.lights:
        if l.name.startswith('SunShaft'):
            l.energy *= float(a['shaft_mul'])
    print("SHAFTS", [round(l.energy) for l in bpy.data.lights if l.name.startswith('SunShaft')][:2])
cy.use_denoising = True
cy.denoiser = 'OPENIMAGEDENOISE'
cy.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
cy.denoising_prefilter = 'ACCURATE'
try:
    cy.denoising_quality = 'HIGH'
    cy.denoising_use_gpu = True
except Exception:
    pass
scn.render.use_motion_blur = bool(a.get('blur', True))
scn.render.motion_blur_shutter = float(a.get('shutter', 0.15))
scn.render.dither_intensity = 1.0

fmt = a.get('fmt', 'PNG16')
ims = scn.render.image_settings
if fmt == 'EXR':
    ims.file_format = 'OPEN_EXR'; ims.color_depth = '16'; ext = 'exr'
else:
    ims.file_format = 'PNG'; ims.color_mode = 'RGB'; ims.color_depth = '16' if fmt == 'PNG16' else '8'
    ims.compression = 15; ext = 'png'

print("SETTINGS", dict(res=(w, h), samples=cy.samples, thr=cy.adaptive_threshold, min=cy.adaptive_min_samples,
                       seed_anim=cy.use_animated_seed, pattern=getattr(cy, 'sampling_pattern', '?'), fmt=fmt,
                       vol_bounces=cy.volume_bounces, vol_biased=getattr(cy, 'volume_biased', '?')))
os.makedirs(a['outdir'], exist_ok=True)
frames = sorted(a['frames']) if 'frames' in a else list(range(a['start'], a['end'] + 1))
want = set(frames)
pre = a.get('prefix', 'f_')
t0 = time.time()
for f in range(1, frames[-1] + 1):
    scn.frame_set(f)
    if f not in want:
        continue
    out = os.path.join(a['outdir'], f"{pre}{f:04d}.{ext}")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        continue
    scn.render.filepath = out
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print("FRAME", f, round(time.time() - t, 1), flush=True)
print("QUALITY_DONE", round(time.time() - t0, 1))
