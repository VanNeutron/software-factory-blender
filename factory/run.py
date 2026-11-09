# Executed inside Blender: (re)load build_factory.py into a namespace stored on bpy.
# Paths resolve from the saved .blend (factory/software_factory.blend) or the FACTORY_DIR env var.
import bpy, os
D = os.environ.get('FACTORY_DIR') or (os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.getcwd())
P = os.path.join(D, 'build_factory.py')
g = {'__name__': 'factory'}
g['__file__'] = P
exec(compile(open(P).read(), P, 'exec'), g)
bpy.app.driver_namespace['factory'] = g
