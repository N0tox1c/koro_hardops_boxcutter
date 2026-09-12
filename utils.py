import math
import bpy
import bmesh
from mathutils import Matrix, Vector, Quaternion
from mathutils.geometry import intersect_line_plane
from bpy_extras import view3d_utils

CUTTER_COLLECTION = "_KORO_CUTTERS"
BOOL_PREFIX = "KORO_BOOL"
BEVEL_NAME = "KORO_Bevel"
WN_NAME = "KORO_WeightedNormal"
CUTTER_BEVEL_NAME = "KORO_CutterBevel"
ARRAY_NAME = "KORO_Array"
MIRROR_NAME = "KORO_Mirror"
SOLIDIFY_NAME = "KORO_Solidify"
TAPER_NAME = "KORO_Taper"
RADIAL_ARRAY_NAME = "KORO_RadialArray"
ORIGIN_SUFFIX = "_Origin"
RADIAL_SUFFIX = "_RadialOrigin"


def ensure_cutter_collection(scene):
    col = bpy.data.collections.get(CUTTER_COLLECTION)
    if col is None:
        col = bpy.data.collections.new(CUTTER_COLLECTION)
        scene.collection.children.link(col)
    return col




def mark_cutter_created(scene, obj):
    """Assign a monotonically increasing serial so Repeat/Stamp can find the last cutter."""
    if obj is None:
        return 0
    serial = int(scene.get("koro_cutter_serial", 0)) + 1
    scene["koro_cutter_serial"] = serial
    scene["koro_last_cutter"] = obj.name
    obj["koro_cutter_serial"] = serial
    obj["koro_cutter"] = True
    return serial


def last_cutter(scene):
    """Return the most recently tagged KORO cutter that still exists."""
    name = scene.get("koro_last_cutter", "")
    obj = bpy.data.objects.get(name) if name else None
    if obj is not None and obj.type == 'MESH' and obj.get("koro_cutter", False):
        return obj
    col = bpy.data.collections.get(CUTTER_COLLECTION)
    if col is None:
        return None
    candidates = [o for o in col.objects if o.type == 'MESH' and o.get("koro_cutter", False)]
    if not candidates:
        return None
    return max(candidates, key=lambda o: int(o.get("koro_cutter_serial", 0)))


def duplicate_cutter(context, source, name_prefix="KORO_Repeat"):
    """Deep-copy a cutter and remap helper-object references used by live modifiers."""
    if source is None or source.type != 'MESH':
        return None
    obj = source.copy()
    obj.data = source.data.copy()
    obj.name = f"{name_prefix}_{source.name}"
    ensure_cutter_collection(context.scene).objects.link(obj)
    obj.matrix_world = source.matrix_world.copy()
    obj.display_type = 'WIRE'
    obj.show_in_front = True
    obj.hide_render = True
    obj.hide_set(False)

    helper_map = {}
    for mod in obj.modifiers:
        ref = None
        attr = None
        if mod.type == 'ARRAY' and getattr(mod, 'use_object_offset', False):
            ref = getattr(mod, 'offset_object', None)
            attr = 'offset_object'
        elif mod.type == 'MIRROR':
            ref = getattr(mod, 'mirror_object', None)
            attr = 'mirror_object'
        if ref is None or ref == source:
            continue
        if not (ref.get("koro_radial_helper", False) or ref.get("koro_origin_gizmo", False) or ref.name.startswith(source.name)):
            continue
        new_ref = helper_map.get(ref.name)
        if new_ref is None:
            new_ref = ref.copy()
            new_ref.name = ref.name.replace(source.name, obj.name, 1) if source.name in ref.name else f"{obj.name}_{ref.name}"
            ensure_cutter_collection(context.scene).objects.link(new_ref)
            new_ref.matrix_world = ref.matrix_world.copy()
            new_ref.hide_render = True
            helper_map[ref.name] = new_ref
        setattr(mod, attr, new_ref)

    mark_cutter_created(context.scene, obj)
    return obj


def add_collection_boolean(target, collection, operation='DIFFERENCE', solver='EXACT'):
    """Create one native Blender Collection Boolean modifier."""
    mod = target.modifiers.new(name=f"{BOOL_PREFIX}_COLLECTION_{operation}", type='BOOLEAN')
    mod.operand_type = 'COLLECTION'
    mod.collection = collection
    mod.operation = operation
    try:
        mod.solver = solver
    except Exception:
        mod.solver = 'EXACT'
    return mod

def create_cutter(context, matrix_world, name="KORO_Cutter"):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    obj = bpy.data.objects.new(name, mesh)
    ensure_cutter_collection(context.scene).objects.link(obj)
    obj.matrix_world = matrix_world
    obj.display_type = 'WIRE'
    obj.show_in_front = True
    obj.hide_render = True
    obj["koro_cutter"] = True
    mark_cutter_created(context.scene, obj)
    return obj


def delete_object(obj):
    if not obj:
        return
    if getattr(obj, "type", None) == 'MESH':
        delete_origin_gizmo(obj)
        delete_radial_helper(obj)
    mesh = obj.data if getattr(obj, "type", None) == 'MESH' else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def view_ray(context, mouse_xy):
    region = context.region
    rv3d = context.region_data
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse_xy)
    direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse_xy)
    return origin, direction.normalized()


def raycast_scene(context, mouse_xy, target=None):
    origin, direction = view_ray(context, mouse_xy)
    depsgraph = context.evaluated_depsgraph_get()
    hit, loc, normal, face_index, obj, _matrix = context.scene.ray_cast(
        depsgraph, origin, direction, distance=100000.0
    )
    if not hit:
        return None
    if target is not None and obj != target:
        inv = target.matrix_world.inverted()
        ro = inv @ origin
        rd = (inv.to_3x3() @ direction).normalized()
        ok, local_loc, local_no, fi = target.ray_cast(ro, rd, distance=100000.0)
        if not ok:
            return None
        loc = target.matrix_world @ local_loc
        normal = (target.matrix_world.to_3x3().inverted().transposed() @ local_no).normalized()
        obj = target
        face_index = fi
    return loc, normal.normalized(), face_index, obj


def plane_point(context, mouse_xy, plane_co, plane_no):
    origin, direction = view_ray(context, mouse_xy)
    return intersect_line_plane(
        origin, origin + direction * 100000.0, plane_co, plane_no, False
    )


def surface_basis(context, normal):
    rv3d = context.region_data
    inv_view = rv3d.view_matrix.inverted().to_3x3()
    view_right = (inv_view @ Vector((1.0, 0.0, 0.0))).normalized()
    x = view_right - normal * view_right.dot(normal)
    if x.length < 1e-5:
        fallback = Vector((1, 0, 0)) if abs(normal.x) < 0.9 else Vector((0, 1, 0))
        x = fallback - normal * fallback.dot(normal)
    x.normalize()
    y = normal.cross(x).normalized()
    x = y.cross(normal).normalized()
    return x, y, normal.normalized()


def orientation_basis(context, normal, mode='SURFACE', mouse_xy=None):
    mode = mode or 'SURFACE'
    if mode == 'SURFACE':
        return surface_basis(context, normal)

    if mode == 'VIEW':
        if mouse_xy is None:
            mouse_xy = (context.region.width * 0.5, context.region.height * 0.5)
        _origin, view_dir = view_ray(context, mouse_xy)
        z = (-view_dir).normalized()
        inv_view = context.region_data.view_matrix.inverted().to_3x3()
        view_right = (inv_view @ Vector((1.0, 0.0, 0.0))).normalized()
        x = view_right - z * view_right.dot(z)
        if x.length < 1e-6:
            x = Vector((1, 0, 0)) - z * z.x
        x.normalize()
        y = z.cross(x).normalized()
        x = y.cross(z).normalized()
        return x, y, z

    # WORLD: lock the cutter normal to the closest signed world axis.
    axes = (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
    idx = max(range(3), key=lambda i: abs(normal.dot(axes[i])))
    z = axes[idx].copy()
    if normal.dot(z) < 0.0:
        z.negate()
    candidate = Vector((1, 0, 0)) if abs(z.x) < 0.9 else Vector((0, 1, 0))
    x = candidate - z * candidate.dot(z)
    x.normalize()
    y = z.cross(x).normalized()
    x = y.cross(z).normalized()
    return x, y, z


def basis_matrix(x, y, z, translation):
    mat = Matrix.Identity(4)
    mat.col[0].xyz = x
    mat.col[1].xyz = y
    mat.col[2].xyz = z
    mat.translation = translation
    return mat


def rotate_basis(x, y, z, angle):
    c = math.cos(angle)
    s = math.sin(angle)
    xr = (x * c + y * s).normalized()
    yr = (-x * s + y * c).normalized()
    return xr, yr, z.normalized()


def rotate_basis_xyz(x, y, z, angles):
    """Rotate an orthonormal basis around its evolving local X/Y/Z axes.

    ``angles`` is an XYZ vector in radians.  Sequential local-axis quaternions
    provide real X/Y/Z rotation constraints while keeping the cutter basis
    orthonormal enough for interactive modeling.
    """
    xr, yr, zr = x.normalized(), y.normalized(), z.normalized()
    for axis_name, angle in zip(('X', 'Y', 'Z'), angles):
        if abs(float(angle)) < 1e-12:
            continue
        axis = xr if axis_name == 'X' else yr if axis_name == 'Y' else zr
        q = Quaternion(axis, float(angle))
        xr = (q @ xr).normalized()
        yr = (q @ yr).normalized()
        zr = (q @ zr).normalized()
    # Re-orthogonalize to avoid accumulated floating-point skew.
    zr.normalize()
    xr = (xr - zr * xr.dot(zr)).normalized()
    yr = zr.cross(xr).normalized()
    xr = yr.cross(zr).normalized()
    return xr, yr, zr


def _screen_distance(context, world_point, mouse_xy):
    p2 = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, world_point)
    if p2 is None:
        return float('inf')
    dx = p2.x - mouse_xy[0]
    dy = p2.y - mouse_xy[1]
    return math.hypot(dx, dy)


def _closest_point_segment(point, a, b):
    ab = b - a
    den = ab.length_squared
    if den < 1e-12:
        return a.copy()
    t = max(0.0, min(1.0, (point - a).dot(ab) / den))
    return a + ab * t


def _closest_point_segment_2d(point, a, b):
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    px, py = float(point[0]), float(point[1])
    abx, aby = bx - ax, by - ay
    den = abx * abx + aby * aby
    if den < 1e-12:
        return 0.0, (ax, ay)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / den))
    return t, (ax + abx * t, ay + aby * t)


def geometry_snap_candidates(
    context,
    mouse_xy,
    target,
    pixel_radius=14,
    display_radius=72,
    max_points=48,
    include_midpoints=True,
):
    """Return projected target vertex/edge/midpoint snap candidates near the cursor.

    Each item is ``(world_location, kind, distance_px, screen_xy)``.  The function
    intentionally works on the evaluated target so modifier-generated topology is
    represented as well.  A scan stride protects modal interaction on very dense
    meshes while preserving deterministic behavior.
    """
    if target is None or target.type != 'MESH' or context.region_data is None:
        return []

    depsgraph = context.evaluated_depsgraph_get()
    eval_obj = target.evaluated_get(depsgraph)
    mesh = getattr(eval_obj, 'data', None)
    if mesh is None:
        return []

    mw = eval_obj.matrix_world
    mx, my = float(mouse_xy[0]), float(mouse_xy[1])
    display_radius = max(float(display_radius), float(pixel_radius))
    candidates = []

    # Keep the per-mouse-move cost bounded on production meshes.
    vertex_stride = max(1, math.ceil(len(mesh.vertices) / 25000))
    screen_cache = {}

    def project_vertex(index):
        cached = screen_cache.get(index)
        if cached is not None:
            return cached
        world = mw @ mesh.vertices[index].co
        p2 = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, world)
        value = (world, p2)
        screen_cache[index] = value
        return value

    for vi in range(0, len(mesh.vertices), vertex_stride):
        v = mesh.vertices[vi]
        world = mw @ v.co
        p2 = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, world)
        if p2 is None:
            continue
        dist = math.hypot(p2.x - mx, p2.y - my)
        if dist <= display_radius:
            candidates.append((world, 'VERTEX', dist, (p2.x, p2.y)))
            screen_cache[v.index] = (world, p2)

    edge_stride = max(1, math.ceil(len(mesh.edges) / 25000))
    for ei in range(0, len(mesh.edges), edge_stride):
        edge = mesh.edges[ei]
        a_world, a2 = project_vertex(edge.vertices[0])
        b_world, b2 = project_vertex(edge.vertices[1])
        if a2 is None or b2 is None:
            continue

        t, cp2 = _closest_point_segment_2d((mx, my), a2, b2)
        dist = math.hypot(cp2[0] - mx, cp2[1] - my)
        if dist <= display_radius:
            world = a_world.lerp(b_world, t)
            candidates.append((world, 'EDGE', dist + 0.35, cp2))

        if include_midpoints:
            mid2 = ((a2.x + b2.x) * 0.5, (a2.y + b2.y) * 0.5)
            md = math.hypot(mid2[0] - mx, mid2[1] - my)
            if md <= display_radius:
                candidates.append((a_world.lerp(b_world, 0.5), 'MIDPOINT', md + 0.15, mid2))

    # Prefer vertex, then midpoint, then arbitrary edge when distances are close.
    priority = {'VERTEX': 0.0, 'MIDPOINT': 0.2, 'EDGE': 0.4}
    candidates.sort(key=lambda item: item[2] + priority.get(item[1], 1.0))
    return candidates[:max(1, int(max_points))]


def geometry_snap_point(
    context,
    mouse_xy,
    target,
    pixel_radius=14,
    display_radius=None,
    max_points=48,
    include_midpoints=True,
):
    """Return the nearest geometry snap and nearby dots.

    Result is ``(world_location, world_normal, kind, candidates)``.  ``FACE`` is
    retained as a fallback when no vertex/edge/midpoint falls inside the snap
    radius, so callers can continue drawing on the hit surface.
    """
    hit = raycast_scene(context, mouse_xy, target)
    if hit is None:
        return None
    loc, normal, _face_index, _obj = hit
    display_radius = display_radius if display_radius is not None else pixel_radius
    candidates = geometry_snap_candidates(
        context,
        mouse_xy,
        target,
        pixel_radius=pixel_radius,
        display_radius=display_radius,
        max_points=max_points,
        include_midpoints=include_midpoints,
    )
    if candidates:
        best = candidates[0]
        if best[2] <= float(pixel_radius) + 0.5:
            return best[0], normal, best[1], candidates
    return loc, normal, 'FACE', candidates


def object_bounds_in_matrix(target, matrix_world, margin=0.0):
    inv = matrix_world.inverted()
    points = [inv @ (target.matrix_world @ Vector(corner)) for corner in target.bound_box]
    if not points:
        return -0.1, 0.1
    z_min = min(p.z for p in points) - margin
    z_max = max(p.z for p in points) + margin
    if abs(z_max - z_min) < 1e-6:
        z_min -= max(margin, 0.001)
        z_max += max(margin, 0.001)
    return z_min, z_max


def polygon_area_2d(points):
    area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return area * 0.5


def ensure_ccw(points):
    pts = [(float(p[0]), float(p[1])) for p in points]
    return pts if polygon_area_2d(pts) >= 0.0 else list(reversed(pts))


def _line_intersection_2d(p1, d1, p2, d2, eps=1e-9):
    cross = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(cross) < eps:
        return None
    qx = p2[0] - p1[0]
    qy = p2[1] - p1[1]
    t = (qx * d2[1] - qy * d2[0]) / cross
    return (p1[0] + d1[0] * t, p1[1] + d1[1] * t)


def offset_polygon(points, distance):
    """Offset a simple polygon inward. Best for convex / mildly concave cutter profiles."""
    pts = ensure_ccw(points)
    if len(pts) < 3 or distance <= 0.0:
        return None
    shifted = []
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return None
        nx, ny = -dy / length, dx / length
        shifted.append(((a[0] + nx * distance, a[1] + ny * distance), (dx, dy)))

    inner = []
    for i in range(n):
        prev_p, prev_d = shifted[(i - 1) % n]
        curr_p, curr_d = shifted[i]
        hit = _line_intersection_2d(prev_p, prev_d, curr_p, curr_d)
        if hit is None:
            hit = curr_p
        inner.append(hit)

    if abs(polygon_area_2d(inner)) < 1e-10:
        return None
    return ensure_ccw(inner)


def update_prism_mesh(obj, points2d, z_min, z_max, inset_amount=0.0):
    if not obj or obj.type != 'MESH' or len(points2d) < 3:
        return False
    outer = ensure_ccw(points2d)
    if abs(polygon_area_2d(outer)) < 1e-10:
        return False

    inner = offset_polygon(outer, inset_amount) if inset_amount > 0.0 else None
    if inner and (len(inner) != len(outer) or abs(polygon_area_2d(inner)) >= abs(polygon_area_2d(outer))):
        inner = None

    verts = []
    faces = []
    n = len(outer)

    if inner is None:
        verts.extend((x, y, z_min) for x, y in outer)
        verts.extend((x, y, z_max) for x, y in outer)
        faces.append(tuple(reversed(range(n))))
        faces.append(tuple(range(n, 2 * n)))
        for i in range(n):
            j = (i + 1) % n
            faces.append((i, j, n + j, n + i))
    else:
        verts.extend((x, y, z_min) for x, y in outer)
        verts.extend((x, y, z_max) for x, y in outer)
        verts.extend((x, y, z_min) for x, y in inner)
        verts.extend((x, y, z_max) for x, y in inner)
        ob, ot, ib, it = 0, n, 2 * n, 3 * n
        for i in range(n):
            j = (i + 1) % n
            faces.append((ob + i, ob + j, ot + j, ot + i))
            faces.append((ib + i, it + i, it + j, ib + j))
            faces.append((ot + i, ot + j, it + j, it + i))
            faces.append((ob + i, ib + i, ib + j, ob + j))

    mesh = obj.data
    try:
        mesh.clear_geometry()
    except AttributeError:
        old = mesh
        mesh = bpy.data.meshes.new(f"{obj.name}Mesh")
        obj.data = mesh
        if old.users == 0:
            bpy.data.meshes.remove(old)
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    return True



def update_profile_mesh(obj, points2d, z=0.0, inset_amount=0.0):
    """Build a flat cutter profile suitable for a Solidify modifier."""
    if not obj or obj.type != 'MESH' or len(points2d) < 3:
        return False
    outer = ensure_ccw(points2d)
    if abs(polygon_area_2d(outer)) < 1e-10:
        return False

    inner = offset_polygon(outer, inset_amount) if inset_amount > 0.0 else None
    if inner and (len(inner) != len(outer) or abs(polygon_area_2d(inner)) >= abs(polygon_area_2d(outer))):
        inner = None

    verts = [(x, y, z) for x, y in outer]
    faces = []
    n = len(outer)
    if inner is None:
        faces.append(tuple(range(n)))
    else:
        verts.extend((x, y, z) for x, y in inner)
        for i in range(n):
            j = (i + 1) % n
            faces.append((i, j, n + j, n + i))

    mesh = obj.data
    try:
        mesh.clear_geometry()
    except AttributeError:
        old = mesh
        mesh = bpy.data.meshes.new(f"{obj.name}Mesh")
        obj.data = mesh
        if old.users == 0:
            bpy.data.meshes.remove(old)
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)
    return True


def ensure_solidify(obj, enabled, thickness=0.1, even=True):
    mod = obj.modifiers.get(SOLIDIFY_NAME)
    if not enabled:
        if mod:
            obj.modifiers.remove(mod)
        return None
    if mod is None or mod.type != 'SOLIDIFY':
        mod = obj.modifiers.new(name=SOLIDIFY_NAME, type='SOLIDIFY')
    mod.thickness = max(float(thickness), 1e-7)
    mod.offset = 0.0
    try:
        mod.use_rim = True
    except Exception:
        pass
    try:
        mod.use_even_offset = bool(even)
    except Exception:
        pass
    return mod


def _origin_empty_name(cutter):
    return f"{cutter.name}{ORIGIN_SUFFIX}"


def ensure_origin_gizmo(context, cutter, target, mode='CUTTER', visible=True):
    """Create/update a lightweight axes helper and return the mirror reference object.

    CUTTER mirrors around the cutter object's own origin (mirror_object=None).
    TARGET mirrors around the target object's axes/origin.
    CURSOR mirrors around a helper located at the 3D cursor using cutter orientation.
    """
    if not cutter:
        return None

    name = _origin_empty_name(cutter)
    helper = bpy.data.objects.get(name)
    if helper is None:
        helper = bpy.data.objects.new(name, None)
        col = ensure_cutter_collection(context.scene)
        col.objects.link(helper)
        helper.empty_display_type = 'PLAIN_AXES'
        helper.empty_display_size = 0.08
        helper.hide_render = True
        helper["koro_origin_gizmo"] = True
        helper["koro_cutter_name"] = cutter.name

    if mode == 'TARGET' and target:
        helper.matrix_world = target.matrix_world.copy()
        mirror_ref = target
    elif mode == 'CURSOR':
        mat = cutter.matrix_world.copy()
        mat.translation = context.scene.cursor.location.copy()
        helper.matrix_world = mat
        mirror_ref = helper
    else:
        helper.matrix_world = cutter.matrix_world.copy()
        mirror_ref = None

    helper.hide_set(not visible)
    helper.hide_viewport = False
    return mirror_ref


def delete_origin_gizmo(cutter):
    if not cutter:
        return
    helper = bpy.data.objects.get(_origin_empty_name(cutter))
    if helper:
        bpy.data.objects.remove(helper, do_unlink=True)


def promote_cutter_to_shape(context, cutter, target=None):
    """Move a made shape out of the private cutter collection into a normal scene collection."""
    if not cutter:
        return
    src = bpy.data.collections.get(CUTTER_COLLECTION)
    if target and target.users_collection:
        dst = target.users_collection[0]
    else:
        dst = context.scene.collection
    if dst not in cutter.users_collection:
        dst.objects.link(cutter)
    if src and src in cutter.users_collection:
        try:
            src.objects.unlink(cutter)
        except Exception:
            pass


def duplicate_target(context, target, suffix):
    clone = target.copy()
    clone.data = target.data.copy()
    clone.name = f"{target.name}_{suffix}"
    collection = target.users_collection[0] if target.users_collection else context.scene.collection
    collection.objects.link(clone)
    return clone


def _append_mesh_into_bmesh(dst_bm, target, source):
    transform = target.matrix_world.inverted() @ source.matrix_world
    vmap = {}
    for v in source.data.vertices:
        vmap[v.index] = dst_bm.verts.new(transform @ v.co)
    dst_bm.verts.index_update()
    for poly in source.data.polygons:
        try:
            face = dst_bm.faces.new([vmap[i] for i in poly.vertices])
            face.material_index = poly.material_index
        except ValueError:
            # An identical face may already exist; duplicate cleanup handles the rest.
            pass


def merge_partition_back(target, inside, distance=1e-5):
    """Join an INTERSECT partition back into a DIFFERENCE target as an imprint.

    The two Boolean outputs share an internal interface. After welding coincident
    vertices, duplicate interface faces are removed in pairs, leaving only the
    reconstructed exterior with a real topology seam where the cutter met it.
    """
    if not target or not inside or target.type != 'MESH' or inside.type != 'MESH':
        return 0

    bm = bmesh.new()
    bm.from_mesh(target.data)
    _append_mesh_into_bmesh(bm, target, inside)
    bm.verts.ensure_lookup_table()
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=max(distance, 1e-9))
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    groups = {}
    for face in list(bm.faces):
        key = tuple(sorted(v.index for v in face.verts))
        groups.setdefault(key, []).append(face)

    duplicate_faces = []
    for faces in groups.values():
        if len(faces) > 1:
            duplicate_faces.extend(faces)
    if duplicate_faces:
        bmesh.ops.delete(bm, geom=duplicate_faces, context='FACES_ONLY')

    try:
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    except Exception:
        pass
    bm.to_mesh(target.data)
    bm.free()
    target.data.update()
    return len(duplicate_faces)


def _append_temp_material(obj, material):
    for i, mat in enumerate(obj.data.materials):
        if mat == material:
            return i
    obj.data.materials.append(material)
    return len(obj.data.materials) - 1


def _mark_cutter_material(cutter, material):
    idx = _append_temp_material(cutter, material)
    for poly in cutter.data.polygons:
        poly.material_index = idx
    return idx


def _delete_faces_with_material(obj, material):
    indices = [i for i, mat in enumerate(obj.data.materials) if mat == material]
    if not indices:
        return 0
    marker = set(indices)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    faces = [f for f in bm.faces if f.material_index in marker]
    count = len(faces)
    if faces:
        bmesh.ops.delete(bm, geom=faces, context='FACES_ONLY')
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    # Marker was appended and is expected to be the final slot after TRANSFER.
    for i in sorted(indices, reverse=True):
        try:
            obj.data.materials.pop(index=i)
        except Exception:
            pass
    return count


def make_knife_imprint(context, target, cutter, solver='EXACT', merge_distance=1e-5):
    """Destructively imprint cutter intersection into target while preserving volume.

    Exact Boolean material transfer tags the temporary partition faces. Those
    interface faces are deleted from both partitions before the two exterior
    shells are welded back together, leaving a real seam in the exterior topology.
    """
    marker = bpy.data.materials.new(name="KORO_Knife_Interface_TMP")
    inside = None
    try:
        _mark_cutter_material(cutter, marker)
        inside = duplicate_target(context, target, "KORO_KNIFE_INSIDE")
        outside_mod = add_boolean(target, cutter, 'DIFFERENCE', 'EXACT')
        inside_mod = add_boolean(inside, cutter, 'INTERSECT', 'EXACT')
        for mod in (outside_mod, inside_mod):
            try:
                mod.material_mode = 'TRANSFER'
            except Exception:
                pass
        sort_target_modifiers(target)
        sort_target_modifiers(inside)
        apply_modifier(context, target, outside_mod)
        apply_modifier(context, inside, inside_mod)
        outside_caps = _delete_faces_with_material(target, marker)
        inside_caps = _delete_faces_with_material(inside, marker)
        duplicate_faces = merge_partition_back(target, inside, merge_distance)
        return outside_caps + inside_caps, duplicate_faces
    finally:
        if inside and inside.name in bpy.data.objects:
            delete_object(inside)
        # Remove marker from cutter if it survived the operation.
        if cutter and cutter.name in bpy.data.objects:
            try:
                for i in range(len(cutter.data.materials) - 1, -1, -1):
                    if cutter.data.materials[i] == marker:
                        cutter.data.materials.pop(index=i)
            except Exception:
                pass
        if marker and marker.users == 0:
            bpy.data.materials.remove(marker)



def create_extract(context, target, cutter, solver='EXACT'):
    clone = duplicate_target(context, target, "EXTRACT")
    mod = add_boolean(clone, cutter, 'INTERSECT', solver)
    sort_target_modifiers(clone)
    return clone, mod


def regular_circle_points(radius, segments):
    segments = max(6, int(segments))
    return [
        (math.cos((i / segments) * math.tau) * radius,
         math.sin((i / segments) * math.tau) * radius)
        for i in range(segments)
    ]


def polygon_span_x(points):
    if not points:
        return 0.001
    xs = [p[0] for p in points]
    return max(max(xs) - min(xs), 0.001)


def add_boolean(target, cutter, operation='DIFFERENCE', solver='EXACT'):
    mod = target.modifiers.new(name=f"{BOOL_PREFIX}_{operation}", type='BOOLEAN')
    mod.operand_type = 'OBJECT'
    mod.object = cutter
    op = operation
    if op in {'SLICE', 'KNIFE', 'EXTRACT', 'MAKE'}:
        op = 'DIFFERENCE'
    mod.operation = op
    try:
        mod.solver = solver
    except Exception:
        mod.solver = 'EXACT'
    return mod


def ensure_cutter_bevel(obj, width, segments, enabled=True):
    mod = obj.modifiers.get(CUTTER_BEVEL_NAME)
    if not enabled:
        if mod:
            obj.modifiers.remove(mod)
        return None
    if mod is None or mod.type != 'BEVEL':
        mod = obj.modifiers.new(name=CUTTER_BEVEL_NAME, type='BEVEL')
    mod.width = max(0.0, width)
    mod.segments = max(1, segments)
    mod.limit_method = 'NONE'
    mod.profile = 0.5
    mod.use_clamp_overlap = True
    return mod




def ensure_taper(obj, enabled=False, factor=0.0):
    mod = obj.modifiers.get(TAPER_NAME)
    if not enabled:
        if mod:
            obj.modifiers.remove(mod)
        return None
    if mod is None or mod.type != 'SIMPLE_DEFORM':
        mod = obj.modifiers.new(name=TAPER_NAME, type='SIMPLE_DEFORM')
    mod.deform_method = 'TAPER'
    mod.deform_axis = 'Z'
    mod.factor = float(factor)
    return mod


def _radial_empty_name(obj):
    return f"{obj.name}{RADIAL_SUFFIX}"


def delete_radial_helper(obj):
    if not obj:
        return
    helper = bpy.data.objects.get(_radial_empty_name(obj))
    if helper:
        bpy.data.objects.remove(helper, do_unlink=True)


def ensure_radial_array(
    context,
    obj,
    enabled,
    count=6,
    sweep=math.tau,
    pivot_xy=(0.0, 0.0),
    visible=False,
):
    """Configure a live radial Array around a movable cutter-local pivot."""
    mod = obj.modifiers.get(RADIAL_ARRAY_NAME)
    helper = bpy.data.objects.get(_radial_empty_name(obj))
    if not enabled:
        if mod:
            obj.modifiers.remove(mod)
        if helper:
            bpy.data.objects.remove(helper, do_unlink=True)
        return None

    if helper is None:
        helper = bpy.data.objects.new(_radial_empty_name(obj), None)
        ensure_cutter_collection(context.scene).objects.link(helper)
        helper.empty_display_type = 'ARROWS'
        helper.empty_display_size = 0.06
        helper.hide_render = True
        helper["koro_radial_helper"] = True
        helper["koro_cutter_name"] = obj.name

    count = max(2, int(count))
    step = float(sweep) / count
    px, py = float(pivot_xy[0]), float(pivot_xy[1])
    pivot = Matrix.Translation((px, py, 0.0))
    unpivot = Matrix.Translation((-px, -py, 0.0))
    delta = pivot @ Matrix.Rotation(step, 4, 'Z') @ unpivot
    helper.matrix_world = obj.matrix_world @ delta
    helper.hide_viewport = False
    helper.hide_set(not bool(visible))

    if mod is None or mod.type != 'ARRAY':
        mod = obj.modifiers.new(name=RADIAL_ARRAY_NAME, type='ARRAY')
    mod.count = count
    mod.fit_type = 'FIXED_COUNT'
    mod.use_relative_offset = False
    mod.use_constant_offset = False
    mod.use_object_offset = True
    mod.offset_object = helper
    try:
        mod.use_merge_vertices = False
    except Exception:
        pass
    return mod


def ensure_array(obj, enabled, count=2, gap=0.05, span_x=1.0):
    mod = obj.modifiers.get(ARRAY_NAME)
    if not enabled:
        if mod:
            obj.modifiers.remove(mod)
        return None
    if mod is None or mod.type != 'ARRAY':
        mod = obj.modifiers.new(name=ARRAY_NAME, type='ARRAY')
    mod.count = max(2, int(count))
    mod.fit_type = 'FIXED_COUNT'
    mod.use_relative_offset = False
    mod.use_constant_offset = True
    mod.constant_offset_displace = (max(0.0001, span_x + gap), 0.0, 0.0)
    try:
        mod.use_merge_vertices = False
    except Exception:
        pass
    return mod


def ensure_mirror(obj, enabled_mode='OFF', mirror_object=None):
    mod = obj.modifiers.get(MIRROR_NAME)
    if enabled_mode == 'OFF':
        if mod:
            obj.modifiers.remove(mod)
        return None
    if mod is None or mod.type != 'MIRROR':
        mod = obj.modifiers.new(name=MIRROR_NAME, type='MIRROR')
    mod.use_axis[0] = enabled_mode in {'X', 'XY'}
    mod.use_axis[1] = enabled_mode in {'Y', 'XY'}
    mod.use_axis[2] = False
    mod.mirror_object = mirror_object
    mod.use_clip = False
    try:
        mod.use_mirror_merge = False
    except Exception:
        pass
    return mod


def sort_cutter_modifiers(obj):
    desired = [SOLIDIFY_NAME, TAPER_NAME, CUTTER_BEVEL_NAME, ARRAY_NAME, RADIAL_ARRAY_NAME, MIRROR_NAME]
    dst = 0
    for name in desired:
        idx = obj.modifiers.find(name)
        if idx >= 0:
            obj.modifiers.move(idx, dst)
            dst += 1


def ensure_bevel(obj, width=0.005, segments=3):
    mod = obj.modifiers.get(BEVEL_NAME)
    if mod is None or mod.type != 'BEVEL':
        mod = obj.modifiers.new(name=BEVEL_NAME, type='BEVEL')
    mod.width = width
    mod.segments = segments
    mod.limit_method = 'ANGLE'
    mod.angle_limit = 0.523599
    mod.profile = 0.5
    mod.use_clamp_overlap = True
    return mod


def ensure_weighted_normal(obj):
    mod = obj.modifiers.get(WN_NAME)
    if mod is None or mod.type != 'WEIGHTED_NORMAL':
        mod = obj.modifiers.new(name=WN_NAME, type='WEIGHTED_NORMAL')
    mod.keep_sharp = True
    try:
        mod.mode = 'FACE_AREA_WITH_ANGLE'
    except Exception:
        pass
    return mod


def sort_target_modifiers(obj):
    bevel_idx = obj.modifiers.find(BEVEL_NAME)
    if bevel_idx >= 0:
        bool_indices = [i for i, m in enumerate(obj.modifiers) if m.type == 'BOOLEAN']
        if bool_indices:
            wanted = min(max(bool_indices) + 1, len(obj.modifiers) - 1)
            bevel_idx = obj.modifiers.find(BEVEL_NAME)
            if bevel_idx != wanted:
                obj.modifiers.move(bevel_idx, wanted)
    wn_idx = obj.modifiers.find(WN_NAME)
    if wn_idx >= 0 and wn_idx != len(obj.modifiers) - 1:
        obj.modifiers.move(wn_idx, len(obj.modifiers) - 1)


def apply_modifier(context, obj, modifier):
    old_active = context.view_layer.objects.active
    old_selected = list(context.selected_objects)
    try:
        for o in old_selected:
            o.select_set(False)
        obj.hide_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    finally:
        if obj and obj.name in bpy.data.objects:
            obj.select_set(False)
        for o in old_selected:
            if o and o.name in bpy.data.objects:
                o.select_set(True)
        if old_active and old_active.name in bpy.data.objects:
            context.view_layer.objects.active = old_active


def mark_sharp_by_angle(obj, angle):
    if obj.type != 'MESH':
        return 0
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    count = 0
    for e in bm.edges:
        if len(e.link_faces) == 2:
            try:
                face_angle = e.calc_face_angle(0.0)
            except Exception:
                face_angle = 0.0
            is_sharp = face_angle >= angle
            e.smooth = not is_sharp
            if is_sharp:
                count += 1
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return count


def duplicate_for_slice(context, target, boolean_mod):
    clone = target.copy()
    clone.data = target.data.copy()
    clone.name = f"{target.name}_SLICE"
    target.users_collection[0].objects.link(clone)
    cloned_mod = clone.modifiers.get(boolean_mod.name)
    if cloned_mod and cloned_mod.type == 'BOOLEAN':
        cloned_mod.operation = 'INTERSECT'
    return clone


def clean_orphan_booleans(obj):
    removed = 0
    for mod in list(obj.modifiers):
        if mod.type == 'BOOLEAN' and mod.operand_type == 'OBJECT' and mod.object is None:
            obj.modifiers.remove(mod)
            removed += 1
    return removed
