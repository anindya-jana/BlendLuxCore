import bpy
from contextlib import contextmanager
from .caches.exported_data import ExportedMesh
from time import time
from .. import utils
from ..utils.errorlog import LuxCoreErrorLog


def custom_normals_supported():
    version = bpy.app.version
    if version == (2, 82, 7):
        return True
    if version[:2] == (2, 83):
        return True
    return False


def convert(obj, mesh_key, depsgraph, luxcore_scene, is_viewport_render, use_instancing, transform, exporter=None):
    start_time = time()
    
    with _prepare_mesh(obj, depsgraph) as mesh:
        if mesh is None:
            return None
        
        if mesh.has_custom_normals and not custom_normals_supported():
            LuxCoreErrorLog.add_warning("Custom normals not supported for this Blender version", obj_name=obj.name)

        loopTriPtr = mesh.loop_triangles[0].as_pointer()
        loopTriCount = len(mesh.loop_triangles)
        loopPtr = mesh.loops[0].as_pointer()
        vertPtr = mesh.vertices[0].as_pointer()
        polyPtr = mesh.polygons[0].as_pointer()
        loopUVsPtrList = []
        loopColsPtrList = []

        if mesh.uv_layers:
            for uv in mesh.uv_layers:
                loopUVsPtrList.append(uv.data[0].as_pointer())
        else:
            loopUVsPtrList.append(0)

        if mesh.vertex_colors:
            for vcol in mesh.vertex_colors:
                loopColsPtrList.append(vcol.data[0].as_pointer())
        else:
            loopColsPtrList.append(0)

        meshPtr = mesh.as_pointer()
        material_count = max(1, len(mesh.materials))

        if is_viewport_render or use_instancing:
            mesh_transform = None
        else:
            mesh_transform = utils.matrix_to_list(transform)

        mesh_definitions = luxcore_scene.DefineBlenderMesh(mesh_key, loopTriCount, loopTriPtr, loopPtr,
                                                           vertPtr, polyPtr, loopUVsPtrList, loopColsPtrList,
                                                           meshPtr, material_count, mesh_transform,
                                                           bpy.app.version)
        
        if exporter and exporter.stats:
            exporter.stats.export_time_meshes.value += time() - start_time
        
        return ExportedMesh(mesh_definitions)


@contextmanager
def _prepare_mesh(obj, depsgraph):
    """
    Create a temporary mesh from an object.
    The mesh is guaranteed to be removed when the calling block ends.
    Can return None if no mesh could be created from the object (e.g. for empties)

    Use it like this:

    with mesh_converter.convert(obj, depsgraph) as mesh:
        if mesh:
            print(mesh.name)
            ...
    """

    mesh = None
    object_eval = None

    try:
        object_eval = obj.evaluated_get(depsgraph)
        if object_eval:
            mesh = object_eval.to_mesh()

            if mesh:
                # TODO test if this makes sense
                # If negative scaling, we have to invert the normals
                # if not mesh.has_custom_normals and object_eval.matrix_world.determinant() < 0.0:
                #     # Does not handle custom normals
                #     mesh.flip_normals()
                
                mesh.calc_loop_triangles()
                if not mesh.loop_triangles:
                    object_eval.to_mesh_clear()
                    mesh = None

            if mesh:
                if mesh.use_auto_smooth:
                    if not mesh.has_custom_normals:
                        mesh.calc_normals()
                    mesh.split_faces()
                
                mesh.calc_loop_triangles()
                
                if mesh.has_custom_normals:
                    mesh.calc_normals_split()

        yield mesh
    finally:
        if object_eval and mesh:
            object_eval.to_mesh_clear()
