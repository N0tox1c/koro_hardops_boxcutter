import math
import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy.props import EnumProperty
from bpy.types import Operator
from .. import utils


class KORO_OT_box_cutter(Operator):
    bl_idname = "koro.box_cutter"
    bl_label = "KORO Cutter"
    bl_description = "Interactive Box / Circle / NGon hard-surface cutter"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    shape: EnumProperty(
        name="Shape",
        items=(
            ('BOX', "Box", "Rectangular cutter"),
            ('CIRCLE', "Circle", "Circular cutter"),
            ('NGON', "NGon", "Free polygon cutter"),
        ),
        default='BOX',
        options={'SKIP_SAVE'},
    )

    _handle = None
    _view_handle = None
    target = None
    cutter = None
    bool_mod = None
    slice_clone = None
    extract_clone = None
    phase = 'WAIT'
    previous_phase = 'WAIT'
    start_point = None
    hit_normal = None
    base_basis_x = None
    base_basis_y = None
    base_basis_z = None
    basis_x = None
    basis_y = None
    basis_z = None
    current_point = None
    ngon_points = None
    preview_point = None
    depth = 0.001
    depth_mouse_y = 0
    width = 0.001
    height = 0.001
    radius = 0.001
    mode = 'DIFFERENCE'
    inset_enabled = False
    cutter_bevel_enabled = False
    array_enabled = False
    array_mode = 'OFF'
    taper_enabled = False
    taper_factor = 0.0
    profile_scale = 1.0
    move_start_point = None
    move_base_start = None
    scale_start_x = 0
    scale_base_factor = 1.0
    taper_start_x = 0
    taper_base_factor = 0.0
    mirror_mode = 'OFF'
    draw_origin = 'CORNER'
    orientation_mode = 'SURFACE'
    through_cut = False
    rotation_angle = 0.0
    rotation_start_x = 0
    rotation_base_angle = 0.0
    snap_kind = 'NONE'
    live_solidify = True
    mirror_origin = 'CUTTER'
    snap_dots = None
    lazorcut = False
    offset_amount = 0.0
    offset_start_y = 0
    offset_base_amount = 0.0
    inset_amount = 0.025
    inset_start_x = 0
    inset_base_amount = 0.025
    radial_origin = None
    radial_origin_base = None
    radial_origin_start = None
    paused = False
    show_helper = False
    transform_axis = 'FREE'
    rotation_angles = None
    rotation_base_angles = None
    profile_scale_xy = None
    scale_base_xy = None
    depth_scale = 1.0
    scale_base_depth = 1.0
    move_start_y = 0
    extrude_direction = 'NEGATIVE'

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return (
            context.area and context.area.type == 'VIEW_3D'
            and obj is not None and obj.type == 'MESH'
            and context.mode == 'OBJECT'
        )

    def _settings(self, context):
        return context.scene.koro_hs

    def _add_draw_handler(self, context):
        if self._handle is None:
            self._handle = bpy.types.SpaceView3D.draw_handler_add(
                self._draw_hud, (context,), 'WINDOW', 'POST_PIXEL'
            )
        if self._view_handle is None:
            self._view_handle = bpy.types.SpaceView3D.draw_handler_add(
                self._draw_dots, (context,), 'WINDOW', 'POST_VIEW'
            )

    def _remove_draw_handler(self):
        if self._handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            self._handle = None
        if self._view_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._view_handle, 'WINDOW')
            self._view_handle = None

    def _draw_line(self, text, x, y, size=14):
        font_id = 0
        blf.position(font_id, x, y, 0)
        try:
            blf.size(font_id, size)
        except TypeError:
            blf.size(font_id, size, 72)
        blf.draw(font_id, text)

    def _draw_snap_dots(self, context):
        s = self._settings(context)
        if not s.show_dots or not self.snap_dots:
            return
        groups = {
            'VERTEX': [],
            'MIDPOINT': [],
            'EDGE': [],
        }
        for _world, kind, _dist, screen in self.snap_dots:
            if kind in groups:
                groups[kind].append((float(screen[0]), float(screen[1]), 0.0))
        colors = {
            'VERTEX': (1.0, 0.72, 0.12, 1.0),
            'MIDPOINT': (0.35, 0.9, 1.0, 1.0),
            'EDGE': (0.82, 0.82, 0.82, 0.95),
        }
        try:
            shader = gpu.shader.from_builtin('POINT_UNIFORM_COLOR')
            old_size = float(s.dot_size)
            for kind in ('EDGE', 'MIDPOINT', 'VERTEX'):
                coords = groups[kind]
                if not coords:
                    continue
                size = old_size + (2.0 if kind == 'VERTEX' else 0.0)
                batch = batch_for_shader(shader, 'POINTS', {"pos": coords})
                shader.bind()
                shader.uniform_float("color", colors[kind])
                shader.uniform_float("size", size)
                batch.draw(shader)
        except Exception:
            pass

    def _draw_dots(self, context):
        s = self._settings(context)
        if not s.show_dots or not self.cutter:
            return
        pts2d = self._profile_points(include_preview=True)
        if not pts2d:
            return
        mw = self.cutter.matrix_world
        coords = [mw @ Vector((p[0], p[1], 0.0)) for p in pts2d]
        try:
            shader = gpu.shader.from_builtin('POINT_UNIFORM_COLOR')
            batch = batch_for_shader(shader, 'POINTS', {"pos": coords})
            shader.bind()
            shader.uniform_float("color", (1.0, 0.66, 0.12, 1.0))
            try:
                shader.uniform_float("size", float(s.dot_size))
            except Exception:
                gpu.state.point_size_set(float(s.dot_size))
            batch.draw(shader)
        except Exception:
            # HUD remains usable even on GPU backends that reject point drawing.
            pass

    def _draw_hud(self, context):
        self._draw_snap_dots(context)
        s = self._settings(context)
        if not s.show_hud:
            return
        x = 28
        y = context.region.height - 42
        self._draw_line("KORO BOXCUTTER v0.8", x, y, 18)
        y -= 24
        self._draw_line(
            f"Shape: {self.shape}   Mode: {self.mode}   Phase: {self.phase}", x, y, 14
        )
        y -= 20
        if self.shape == 'CIRCLE':
            dim = f"R {self.radius * self.profile_scale:.4f}   D {self.depth:.4f}   Seg {s.circle_segments}"
        else:
            dim = f"W {self.width:.4f}   H {self.height:.4f}   D {self.depth:.4f}"
        angles = self.rotation_angles if self.rotation_angles is not None else Vector((0.0, 0.0, self.rotation_angle))
        dim += f"   Rot X{math.degrees(angles.x):.0f} Y{math.degrees(angles.y):.0f} Z{math.degrees(angles.z):.0f}°"
        self._draw_line(dim, x, y, 13)
        y -= 20
        flags = (
            f"Orient {self.orientation_mode} | Origin {self.draw_origin} | Extrude {self.extrude_direction} | "
            f"Axis {self.transform_axis} | {'LOCK' if self.paused else 'LIVE'} | Grid {'ON' if s.snap_enabled else 'OFF'} | Geo {'ON' if s.geometry_snap else 'OFF'}"
        )
        self._draw_line(flags, x, y, 12)
        y -= 18
        taper_text = f"{self.taper_factor:.2f}" if self.taper_enabled else "OFF"
        flags2 = (
            f"Through {'ON' if self.through_cut else 'OFF'} | Lazor {'ON' if self.lazorcut else 'OFF'} | Snap {self.snap_kind} | "
            f"Solidify {'ON' if self.live_solidify else 'OFF'} | Inset {'ON' if self.inset_enabled else 'OFF'} | "
            f"Bevel {'ON' if self.cutter_bevel_enabled else 'OFF'} | "
            f"Array {self.array_mode}:{s.array_count if self.array_mode != 'OFF' else '-'} | "
            f"Taper {taper_text} | Offset {self.offset_amount:.4f} | Mirror {self.mirror_mode}@{self.mirror_origin}"
        )
        self._draw_line(flags2, x, y, 12)
        y -= 24

        if self.phase == 'WAIT':
            hint = "TAB shape | V orientation | C origin | LMB begin"
        elif self.phase == 'DRAW':
            hint = "Drag profile | Shift = square | release LMB -> depth"
        elif self.phase == 'NGON':
            hint = "LMB add point | Shift 15° | Backspace undo | Enter close"
        elif self.phase == 'ROTATE':
            hint = f"Move mouse = rotate {self.transform_axis} | X/Y/Z axis | Ctrl snap | accept R/LMB"
        elif self.phase == 'MOVE':
            hint = f"Move = translate {self.transform_axis} | X/Y/Z constrain | G/LMB accept"
        elif self.phase == 'SCALE':
            hint = f"Move = scale {self.transform_axis} | X/Y/Z constrain | Ctrl steps | S/LMB accept"
        elif self.phase == 'TAPER':
            hint = "Move mouse = taper | Ctrl = 0.1 steps | LMB / Enter / W = accept"
        elif self.phase == 'OFFSET':
            hint = "Move mouse = surface offset | Ctrl = grid step | LMB / Enter / O = accept"
        elif self.phase == 'INSET':
            hint = "Move mouse = inset width | Ctrl = grid step | LMB / Enter / I = accept"
        elif self.phase == 'RADIAL_ORIGIN':
            hint = "Move mouse = radial pivot | Ctrl = grid snap | LMB / Enter / Shift+O = accept"
        else:
            hint = "Move mouse = depth | E through | R rotate | G move | S scale | LMB confirm"
        self._draw_line(hint, x, y, 13)
        y -= 18
        self._draw_line("X Difference | J Join | K Slice | Shift+K Knife | T Extract | P Make", x, y, 12)
        y -= 18
        self._draw_line("A Array mode | Shift+A Radial | M Mirror | W Taper | Z Solidify | E Through", x, y, 12)
        y -= 18
        self._draw_line("G Move / Shift+G GeoSnap | S Scale / Shift+S GridSnap | Ctrl SnapDots | R Rotate", x, y, 12)
        y -= 18
        self._draw_line("Space Lazorcut/Confirm | O Offset | I Inset | Shift+O Radial Pivot | Alt+O Mirror Origin", x, y, 12)
        y -= 18
        self._draw_line("L Pause/Release | F Extrude direction | Ctrl+D Mini Helper | X/Y/Z constrain G/R/S", x, y, 12)
        if self.show_helper:
            y -= 22
            self._draw_line("MINI HELPER: TAB shape | V orient | C origin | D dots | B bevel | Z solidify", x, y, 12)
            y -= 18
            self._draw_line("Operations: X Difference | J Union | K Slice | Shift+K Knife | T Extract | P Make", x, y, 12)
            y -= 18
            self._draw_line("Transforms: G move | S scale | R rotate | axis X/Y/Z | L lock | F extrusion side", x, y, 12)

    def invoke(self, context, event):
        s = self._settings(context)
        self.target = context.active_object
        self.phase = 'WAIT'
        self.previous_phase = 'WAIT'
        self.cutter = None
        self.bool_mod = None
        self.slice_clone = None
        self.extract_clone = None
        self.start_point = None
        self.hit_normal = None
        self.current_point = None
        self.ngon_points = []
        self.preview_point = None
        self.mode = s.operation
        self.depth = max(0.001, s.default_depth)
        self.inset_enabled = s.inset_enabled
        self.cutter_bevel_enabled = s.cutter_bevel
        self.array_mode = s.array_mode if hasattr(s, 'array_mode') else ('LINEAR' if s.array_enabled else 'OFF')
        self.array_enabled = self.array_mode != 'OFF'
        self.taper_enabled = s.taper_enabled
        self.taper_factor = s.taper_factor
        self.profile_scale = 1.0
        self.mirror_mode = s.mirror_mode
        self.draw_origin = s.draw_origin
        self.orientation_mode = s.orientation
        self.through_cut = s.through_cut
        self.rotation_angle = 0.0
        self.snap_kind = 'NONE'
        self.snap_dots = []
        self.live_solidify = s.live_solidify
        self.mirror_origin = s.mirror_origin
        self.lazorcut = False
        self.offset_amount = s.offset_amount
        self.inset_amount = s.inset_amount
        self.radial_origin = Vector((s.radial_origin[0], s.radial_origin[1]))
        self.paused = False
        self.show_helper = False
        self.transform_axis = 'FREE'
        self.rotation_angles = Vector((0.0, 0.0, 0.0))
        self.rotation_base_angles = self.rotation_angles.copy()
        self.profile_scale_xy = Vector((1.0, 1.0))
        self.scale_base_xy = self.profile_scale_xy.copy()
        self.depth_scale = 1.0
        self.scale_base_depth = 1.0
        self.extrude_direction = s.extrude_direction
        self._add_draw_handler(context)
        context.window.cursor_modal_set('CROSSHAIR')
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _geometry_snap_active(self, context, event=None):
        s = self._settings(context)
        if not s.geometry_snap:
            return False
        if not s.snap_requires_ctrl:
            return True
        return bool(event and event.ctrl)

    def _grid_snap_active(self, context, event=None):
        s = self._settings(context)
        # Ctrl is reserved for Boxcutter-style geometry dots when that system is active.
        temp_grid = bool(event and event.ctrl and not s.geometry_snap)
        return s.snap_enabled or temp_grid

    def _snap_scalar(self, context, value, event=None):
        if not self._grid_snap_active(context, event):
            return value
        grid = max(self._settings(context).grid_size, 1e-8)
        return round(value / grid) * grid

    def _geometry_point(self, context, event):
        s = self._settings(context)
        if not self._geometry_snap_active(context, event):
            self.snap_dots = []
            return None
        snapped = utils.geometry_snap_point(
            context,
            (event.mouse_region_x, event.mouse_region_y),
            self.target,
            s.snap_pixel_radius,
            s.snap_dot_radius,
            s.snap_dot_limit,
            s.snap_midpoints,
        )
        if snapped is None:
            self.snap_dots = []
            return None
        world, _normal, kind, candidates = snapped
        self.snap_dots = candidates
        self.snap_kind = kind
        return world if kind in {'VERTEX', 'EDGE', 'MIDPOINT'} else None

    def _mouse_local(self, context, event):
        p = self._geometry_point(context, event)
        if p is None:
            self.snap_kind = 'GRID' if self._grid_snap_active(context, event) else 'NONE'
            p = utils.plane_point(
                context,
                (event.mouse_region_x, event.mouse_region_y),
                self.start_point,
                self.basis_z,
            )
        if p is None:
            return None
        d = p - self.start_point
        x = d.dot(self.basis_x)
        y = d.dot(self.basis_y)
        x = self._snap_scalar(context, x, event)
        y = self._snap_scalar(context, y, event)
        return Vector((x, y))

    def _calculate_base_basis(self, context, event):
        self.base_basis_x, self.base_basis_y, self.base_basis_z = utils.orientation_basis(
            context,
            self.hit_normal,
            self.orientation_mode,
            (event.mouse_region_x, event.mouse_region_y),
        )
        self._refresh_rotated_basis()

    def _refresh_rotated_basis(self):
        angles = self.rotation_angles if self.rotation_angles is not None else Vector((0.0, 0.0, self.rotation_angle))
        self.rotation_angle = angles.z
        self.basis_x, self.basis_y, self.basis_z = utils.rotate_basis_xyz(
            self.base_basis_x, self.base_basis_y, self.base_basis_z, angles
        )
        if self.cutter and self.start_point is not None:
            self.cutter.matrix_world = utils.basis_matrix(
                self.basis_x, self.basis_y, self.basis_z, self.start_point
            )

    def _begin_draw(self, context, event):
        hit = utils.raycast_scene(context, (event.mouse_region_x, event.mouse_region_y), self.target)
        if hit is None:
            self.report({'WARNING'}, "Cursor is not over the active target mesh")
            return False
        loc, normal, _, _ = hit
        if self._geometry_snap_active(context, event):
            settings = self._settings(context)
            snapped = utils.geometry_snap_point(
                context,
                (event.mouse_region_x, event.mouse_region_y),
                self.target,
                settings.snap_pixel_radius,
                settings.snap_dot_radius,
                settings.snap_dot_limit,
                settings.snap_midpoints,
            )
            if snapped is not None:
                snap_loc, _snap_normal, snap_kind, candidates = snapped
                self.snap_dots = candidates
                if snap_kind in {'VERTEX', 'EDGE', 'MIDPOINT'}:
                    loc = snap_loc
                    self.snap_kind = snap_kind
        self.start_point = loc
        self.hit_normal = normal
        self.rotation_angle = 0.0
        self.rotation_angles = Vector((0.0, 0.0, 0.0))
        self._calculate_base_basis(context, event)
        mat = utils.basis_matrix(self.basis_x, self.basis_y, self.basis_z, loc)
        self.cutter = utils.create_cutter(context, mat, name=f"KORO_{self.shape}_Cutter")
        self.bool_mod = utils.add_boolean(self.target, self.cutter, self.mode, self._settings(context).solver)
        if self.mode == 'MAKE':
            self.bool_mod.show_viewport = False
            self.bool_mod.show_render = False
        self.depth = max(0.001, self._settings(context).default_depth)

        if self.shape == 'NGON':
            self.ngon_points = [Vector((0.0, 0.0))]
            self.preview_point = Vector((0.0, 0.0))
            self.phase = 'NGON'
        else:
            self.current_point = Vector((0.001, 0.001))
            self.phase = 'DRAW'
            self._update_profile(context, event)
        return True

    def _constrain_ngon_angle(self, point, event):
        if not event.shift or not self.ngon_points:
            return point
        origin = self.ngon_points[-1]
        vec = point - origin
        length = vec.length
        if length < 1e-8:
            return point
        step = math.radians(15.0)
        angle = math.atan2(vec.y, vec.x)
        angle = round(angle / step) * step
        return origin + Vector((math.cos(angle) * length, math.sin(angle) * length))

    def _update_profile(self, context, event):
        point = self._mouse_local(context, event)
        if point is None:
            return

        if self.shape == 'BOX':
            if event.shift:
                side = max(abs(point.x), abs(point.y), 0.001)
                sx = -1.0 if point.x < 0 else 1.0
                sy = -1.0 if point.y < 0 else 1.0
                point = Vector((side * sx, side * sy))
            self.current_point = point
        elif self.shape == 'CIRCLE':
            radius = max(point.length, 0.001)
            if self._grid_snap_active(context, event):
                radius = max(self._snap_scalar(context, radius, event), 0.001)
            self.radius = radius
            self.current_point = Vector((radius, 0.0))
        elif self.shape == 'NGON':
            point = self._constrain_ngon_angle(point, event)
            self.preview_point = point

        self._update_mesh(context)

    def _profile_points(self, include_preview=True):
        scale = max(self.profile_scale, 0.0001)
        if self.shape == 'BOX':
            p = self.current_point or Vector((0.001, 0.001))
            if self.draw_origin == 'CENTER':
                x = max(abs(p.x), 0.0005)
                y = max(abs(p.y), 0.0005)
                pts = [(-x, -y), (x, -y), (x, y), (-x, y)]
            else:
                pts = [(0.0, 0.0), (p.x, 0.0), (p.x, p.y), (0.0, p.y)]
        elif self.shape == 'CIRCLE':
            pts = utils.regular_circle_points(
                max(self.radius, 0.001), self._settings(bpy.context).circle_segments
            )
        else:
            pts = [(p.x, p.y) for p in self.ngon_points]
            if include_preview and self.phase == 'NGON' and self.preview_point is not None:
                if not self.ngon_points or (self.preview_point - self.ngon_points[-1]).length > 1e-6:
                    pts.append((self.preview_point.x, self.preview_point.y))
        sx = self.profile_scale_xy.x if self.profile_scale_xy is not None else scale
        sy = self.profile_scale_xy.y if self.profile_scale_xy is not None else scale
        sx = max(float(sx), 0.0001)
        sy = max(float(sy), 0.0001)
        if abs(sx - 1.0) > 1e-8 or abs(sy - 1.0) > 1e-8:
            pts = [(x * sx, y * sy) for x, y in pts]
        return pts

    def _z_range(self, context):
        s = self._settings(context)
        surface = s.surface_offset
        top_adjust = self.offset_amount
        if (self.through_cut or self.lazorcut) and self.mode != 'UNION' and self.cutter:
            margin = max(s.through_margin, s.surface_offset)
            z_min, z_max = utils.object_bounds_in_matrix(self.target, self.cutter.matrix_world, margin)
            return z_min, z_max + top_adjust
        depth = max(0.001, self.depth * max(self.depth_scale, 0.01))
        if self.extrude_direction == 'BOTH':
            return -depth * 0.5, depth * 0.5 + top_adjust
        if self.extrude_direction == 'POSITIVE':
            return -surface, depth + top_adjust
        if self.mode == 'UNION':
            return -surface, depth + top_adjust
        return -depth, surface + top_adjust

    def _update_dimensions(self, points):
        if not points:
            return
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        self.width = max(max(xs) - min(xs), 0.001)
        self.height = max(max(ys) - min(ys), 0.001)

    def _update_modifiers(self, context, points):
        s = self._settings(context)
        utils.ensure_cutter_bevel(
            self.cutter, s.cutter_bevel_width, s.cutter_bevel_segments,
            self.cutter_bevel_enabled,
        )
        utils.ensure_taper(self.cutter, self.taper_enabled, self.taper_factor)
        linear = self.array_mode == 'LINEAR'
        radial = self.array_mode == 'RADIAL'
        utils.ensure_array(
            self.cutter, linear, s.array_count, s.array_gap,
            utils.polygon_span_x(points),
        )
        utils.ensure_radial_array(
            context, self.cutter, radial, s.array_count, s.radial_sweep,
            self.radial_origin if self.radial_origin is not None else Vector((0.0, 0.0)),
            visible=(self.phase == 'RADIAL_ORIGIN'),
        )
        mirror_ref = utils.ensure_origin_gizmo(
            context, self.cutter, self.target, self.mirror_origin, s.show_origin_gizmo
        )
        utils.ensure_mirror(self.cutter, self.mirror_mode, mirror_ref)
        utils.sort_cutter_modifiers(self.cutter)

    def _update_mesh(self, context):
        if not self.cutter:
            return
        points = self._profile_points(include_preview=True)
        if len(points) < 3:
            return
        self._update_dimensions(points)
        z_min, z_max = self._z_range(context)
        s = self._settings(context)
        inset = self.inset_amount if self.inset_enabled else 0.0
        if self.live_solidify:
            center_z = (z_min + z_max) * 0.5
            ok = utils.update_profile_mesh(self.cutter, points, center_z, inset)
            utils.ensure_solidify(
                self.cutter, ok, max(z_max - z_min, 1e-7), s.solidify_even
            )
        else:
            utils.ensure_solidify(self.cutter, False)
            ok = utils.update_prism_mesh(self.cutter, points, z_min, z_max, inset)
        if ok:
            self._update_modifiers(context, points)

    def _update_depth(self, context, event):
        if (self.through_cut or self.lazorcut) and self.mode != 'UNION':
            self._update_mesh(context)
            return
        s = self._settings(context)
        delta = self.depth_mouse_y - event.mouse_region_y
        scale_ref = max(self.target.dimensions.length, 1.0)
        depth = s.default_depth + delta * s.depth_sensitivity * scale_ref * 0.1
        if self._grid_snap_active(context, event):
            depth = self._snap_scalar(context, depth, event)
        self.depth = max(0.001, depth)
        self._update_mesh(context)

    def _set_mode(self, context, mode):
        self.mode = mode
        if self.bool_mod:
            preview_op = mode
            if preview_op in {'SLICE', 'KNIFE', 'EXTRACT', 'MAKE'}:
                preview_op = 'DIFFERENCE'
            self.bool_mod.operation = preview_op
            self.bool_mod.name = f"{utils.BOOL_PREFIX}_{mode}"
            self.bool_mod.show_viewport = mode != 'MAKE'
            self.bool_mod.show_render = mode != 'MAKE'
        if self.cutter:
            self._update_mesh(context)

    def _cycle_shape(self):
        order = ['BOX', 'CIRCLE', 'NGON']
        self.shape = order[(order.index(self.shape) + 1) % len(order)]

    def _cycle_orientation(self, context, event):
        order = ['SURFACE', 'VIEW', 'WORLD']
        self.orientation_mode = order[(order.index(self.orientation_mode) + 1) % len(order)]
        if self.start_point is not None and self.hit_normal is not None:
            self._calculate_base_basis(context, event)
            if self.cutter:
                self._update_mesh(context)

    def _cycle_origin(self, context):
        self.draw_origin = 'CENTER' if self.draw_origin == 'CORNER' else 'CORNER'
        if self.cutter and self.shape == 'BOX':
            self._update_mesh(context)

    def _cycle_array(self, context, radial_only=False):
        if radial_only:
            self.array_mode = 'OFF' if self.array_mode == 'RADIAL' else 'RADIAL'
        else:
            order = ['OFF', 'LINEAR', 'RADIAL']
            self.array_mode = order[(order.index(self.array_mode) + 1) % len(order)]
        self.array_enabled = self.array_mode != 'OFF'
        if self.cutter:
            self._update_mesh(context)

    def _cycle_mirror(self, context):
        order = ['OFF', 'X', 'Y', 'XY']
        self.mirror_mode = order[(order.index(self.mirror_mode) + 1) % len(order)]
        if self.cutter:
            self._update_mesh(context)

    def _cycle_mirror_origin(self, context):
        order = ['CUTTER', 'TARGET', 'CURSOR']
        self.mirror_origin = order[(order.index(self.mirror_origin) + 1) % len(order)]
        if self.cutter:
            self._update_mesh(context)

    def _toggle_solidify(self, context):
        self.live_solidify = not self.live_solidify
        if self.cutter:
            self._update_mesh(context)

    def _adjust_array_gap(self, context, direction):
        s = self._settings(context)
        step = max(s.grid_size * 0.25, 0.001)
        s.array_gap += direction * step
        if self.cutter:
            self._update_mesh(context)

    def _adjust_wheel(self, context, event):
        s = self._settings(context)
        direction = 1 if event.type == 'WHEELUPMOUSE' else -1
        if event.alt:
            if self.array_mode == 'OFF':
                self.array_mode = 'LINEAR'
            self.array_enabled = True
            s.array_count = max(2, min(256, s.array_count + direction))
        elif event.ctrl:
            self.inset_enabled = True
            step = max(s.grid_size * 0.1, 0.001)
            self.inset_amount = max(0.00001, self.inset_amount + direction * step)
        elif event.shift:
            if self.cutter_bevel_enabled:
                step = max(s.grid_size * 0.05, 0.0005)
                s.cutter_bevel_width = max(0.0, s.cutter_bevel_width + direction * step)
            else:
                step = max(s.grid_size * 0.05, 0.0005)
                s.bevel_width = max(0.0, s.bevel_width + direction * step)
                if s.auto_bevel:
                    utils.ensure_bevel(self.target, s.bevel_width, s.bevel_segments)
                    utils.sort_target_modifiers(self.target)
        else:
            if self.cutter_bevel_enabled:
                s.cutter_bevel_segments = max(1, min(64, s.cutter_bevel_segments + direction))
            else:
                s.bevel_segments = max(1, min(64, s.bevel_segments + direction))
                if s.auto_bevel:
                    utils.ensure_bevel(self.target, s.bevel_width, s.bevel_segments)
                    utils.sort_target_modifiers(self.target)
        if self.cutter:
            self._update_mesh(context)

    def _commit_ngon_point(self, context, event):
        point = self._mouse_local(context, event)
        if point is None:
            return
        point = self._constrain_ngon_angle(point, event)
        if (point - self.ngon_points[-1]).length < 1e-6:
            return
        self.ngon_points.append(point)
        self.preview_point = point.copy()
        self._update_mesh(context)

    def _close_ngon(self, context, event):
        if len(self.ngon_points) < 3:
            self.report({'WARNING'}, "NGon needs at least 3 points")
            return False
        self.preview_point = None
        self.phase = 'DEPTH'
        self.depth_mouse_y = event.mouse_region_y
        self._update_mesh(context)
        return True

    def _begin_rotate(self, event):
        if not self.cutter or self.phase not in {'DRAW', 'DEPTH'}:
            return
        self.previous_phase = self.phase
        self.phase = 'ROTATE'
        self.transform_axis = 'Z'
        self.rotation_start_x = event.mouse_region_x
        self.rotation_base_angles = self.rotation_angles.copy()

    def _accept_rotate(self):
        if self.phase == 'ROTATE':
            self.phase = self.previous_phase if self.previous_phase in {'DRAW', 'DEPTH'} else 'DEPTH'
            self.transform_axis = 'FREE'

    def _update_rotation(self, context, event):
        axis = self.transform_axis if self.transform_axis in {'X', 'Y', 'Z'} else 'Z'
        idx = {'X': 0, 'Y': 1, 'Z': 2}[axis]
        delta = (event.mouse_region_x - self.rotation_start_x) * 0.01
        angle = self.rotation_base_angles[idx] + delta
        if event.ctrl:
            step = max(self._settings(context).rotation_snap, math.radians(1.0))
            angle = round(angle / step) * step
        elif event.shift:
            step = math.radians(5.0)
            angle = round(angle / step) * step
        self.rotation_angles[idx] = angle
        self.rotation_angle = self.rotation_angles.z
        self._refresh_rotated_basis()
        self._update_mesh(context)

    def _begin_move(self, context, event):
        if not self.cutter or self.phase not in {'DRAW', 'DEPTH'}:
            return
        p = utils.plane_point(
            context, (event.mouse_region_x, event.mouse_region_y), self.start_point, self.basis_z
        )
        if p is None:
            return
        self.previous_phase = self.phase
        self.phase = 'MOVE'
        self.transform_axis = 'FREE'
        self.move_start_point = p
        self.move_base_start = self.start_point.copy()
        self.move_start_y = event.mouse_region_y

    def _update_move(self, context, event):
        p = utils.plane_point(
            context, (event.mouse_region_x, event.mouse_region_y), self.move_base_start, self.basis_z
        )
        if p is None:
            return
        raw = p - self.move_start_point
        dx = raw.dot(self.basis_x)
        dy = raw.dot(self.basis_y)
        if self._grid_snap_active(context, event):
            dx = self._snap_scalar(context, dx, event)
            dy = self._snap_scalar(context, dy, event)
        if self.transform_axis == 'X':
            delta = self.basis_x * dx
        elif self.transform_axis == 'Y':
            delta = self.basis_y * dy
        elif self.transform_axis == 'Z':
            scale_ref = max(self.target.dimensions.length, 1.0)
            dz = (event.mouse_region_y - self.move_start_y) * 0.0015 * scale_ref
            if self._grid_snap_active(context, event):
                dz = self._snap_scalar(context, dz, event)
            delta = self.basis_z * dz
        else:
            delta = self.basis_x * dx + self.basis_y * dy
        self.start_point = self.move_base_start + delta
        self.cutter.matrix_world.translation = self.start_point
        self._update_mesh(context)

    def _begin_scale(self, event):
        if not self.cutter or self.phase not in {'DRAW', 'DEPTH'}:
            return
        self.previous_phase = self.phase
        self.phase = 'SCALE'
        self.transform_axis = 'FREE'
        self.scale_start_x = event.mouse_region_x
        self.scale_base_xy = self.profile_scale_xy.copy()
        self.scale_base_depth = self.depth_scale

    def _update_scale(self, context, event):
        factor = math.exp((event.mouse_region_x - self.scale_start_x) * 0.01)
        if event.ctrl:
            factor = max(0.1, round(factor * 10.0) / 10.0)
        factor = max(0.01, min(100.0, factor))
        if self.transform_axis == 'X':
            self.profile_scale_xy.x = max(0.01, min(100.0, self.scale_base_xy.x * factor))
            self.profile_scale_xy.y = self.scale_base_xy.y
        elif self.transform_axis == 'Y':
            self.profile_scale_xy.y = max(0.01, min(100.0, self.scale_base_xy.y * factor))
            self.profile_scale_xy.x = self.scale_base_xy.x
        elif self.transform_axis == 'Z':
            self.depth_scale = max(0.01, min(100.0, self.scale_base_depth * factor))
        else:
            self.profile_scale_xy = Vector((
                max(0.01, min(100.0, self.scale_base_xy.x * factor)),
                max(0.01, min(100.0, self.scale_base_xy.y * factor)),
            ))
        self.profile_scale = (self.profile_scale_xy.x + self.profile_scale_xy.y) * 0.5
        self._update_mesh(context)

    def _begin_taper(self, event):
        if not self.cutter or self.phase not in {'DRAW', 'DEPTH'}:
            return
        self.previous_phase = self.phase
        self.phase = 'TAPER'
        self.taper_enabled = True
        self.taper_start_x = event.mouse_region_x
        self.taper_base_factor = self.taper_factor

    def _update_taper(self, context, event):
        factor = self.taper_base_factor + (event.mouse_region_x - self.taper_start_x) * 0.01
        if event.ctrl:
            factor = round(factor * 10.0) / 10.0
        self.taper_factor = max(-10.0, min(10.0, factor))
        self._update_mesh(context)

    def _begin_offset(self, event):
        if not self.cutter or self.phase not in {'DRAW', 'DEPTH'}:
            return
        self.previous_phase = self.phase
        self.phase = 'OFFSET'
        self.offset_start_y = event.mouse_region_y
        self.offset_base_amount = self.offset_amount

    def _update_offset(self, context, event):
        scale_ref = max(self.target.dimensions.length, 1.0)
        value = self.offset_base_amount + (event.mouse_region_y - self.offset_start_y) * 0.0015 * scale_ref
        if event.ctrl:
            grid = max(self._settings(context).grid_size, 1e-6)
            value = round(value / grid) * grid
        self.offset_amount = value
        self._update_mesh(context)

    def _begin_inset(self, event):
        if not self.cutter or self.phase not in {'DRAW', 'DEPTH'}:
            return
        self.previous_phase = self.phase
        self.phase = 'INSET'
        self.inset_enabled = True
        self.inset_start_x = event.mouse_region_x
        self.inset_base_amount = self.inset_amount

    def _update_inset(self, context, event):
        scale_ref = max(self.width, self.height, self._settings(context).grid_size, 0.01)
        value = self.inset_base_amount + (event.mouse_region_x - self.inset_start_x) * 0.002 * scale_ref
        if event.ctrl:
            step = max(self._settings(context).grid_size * 0.1, 0.0001)
            value = round(value / step) * step
        self.inset_amount = max(0.00001, value)
        self._update_mesh(context)

    def _begin_radial_origin(self, context, event):
        if not self.cutter or self.array_mode != 'RADIAL' or self.phase not in {'DRAW', 'DEPTH'}:
            return
        self.previous_phase = self.phase
        self.phase = 'RADIAL_ORIGIN'
        self.radial_origin_base = (self.radial_origin if self.radial_origin is not None else Vector((0.0, 0.0))).copy()
        self.radial_origin_start = self._mouse_local(context, event)
        self._update_mesh(context)

    def _update_radial_origin(self, context, event):
        point = self._mouse_local(context, event)
        if point is None or self.radial_origin_start is None:
            return
        delta = point - self.radial_origin_start
        value = self.radial_origin_base + delta
        if self._grid_snap_active(context, event):
            value.x = self._snap_scalar(context, value.x, event)
            value.y = self._snap_scalar(context, value.y, event)
        self.radial_origin = value
        self._update_mesh(context)

    def _cycle_extrude_direction(self, context):
        order = ['NEGATIVE', 'POSITIVE', 'BOTH']
        current = self.extrude_direction if self.extrude_direction in order else 'NEGATIVE'
        self.extrude_direction = order[(order.index(current) + 1) % len(order)]
        if self.cutter:
            self._update_mesh(context)

    def _set_transform_axis(self, context, event, axis):
        if self.phase not in {'MOVE', 'SCALE', 'ROTATE'}:
            return False
        self.transform_axis = axis
        if self.phase == 'ROTATE':
            self.rotation_start_x = event.mouse_region_x
            self.rotation_base_angles = self.rotation_angles.copy()
        elif self.phase == 'SCALE':
            self.scale_start_x = event.mouse_region_x
            self.scale_base_xy = self.profile_scale_xy.copy()
            self.scale_base_depth = self.depth_scale
        elif self.phase == 'MOVE':
            p = utils.plane_point(
                context, (event.mouse_region_x, event.mouse_region_y), self.start_point, self.basis_z
            )
            if p is not None:
                self.move_start_point = p
                self.move_base_start = self.start_point.copy()
                self.move_start_y = event.mouse_region_y
        return True

    def _activate_lazorcut(self, context):
        if not self.cutter:
            return {'RUNNING_MODAL'}
        self.lazorcut = True
        if self.phase == 'NGON':
            if len(self.ngon_points) < 3:
                self.report({'WARNING'}, "NGon needs at least 3 points for Lazorcut")
                return {'RUNNING_MODAL'}
            self.preview_point = None
        self.phase = 'DEPTH'
        self._update_mesh(context)
        return self._finish(context)

    def _accept_transform_phase(self):
        if self.phase in {'MOVE', 'SCALE', 'TAPER', 'OFFSET', 'INSET', 'RADIAL_ORIGIN'}:
            self.phase = self.previous_phase if self.previous_phase in {'DRAW', 'DEPTH'} else 'DEPTH'
            self.transform_axis = 'FREE'

    def _cancel_transform_phase(self, context):
        if self.phase == 'ROTATE':
            self.rotation_angles = self.rotation_base_angles.copy()
            self.rotation_angle = self.rotation_angles.z
            self._refresh_rotated_basis()
            self._update_mesh(context)
            self._accept_rotate()
            return True
        if self.phase == 'MOVE':
            if self.move_base_start is not None:
                self.start_point = self.move_base_start.copy()
                self.cutter.matrix_world.translation = self.start_point
                self._update_mesh(context)
            self._accept_transform_phase()
            return True
        if self.phase == 'SCALE':
            self.profile_scale_xy = self.scale_base_xy.copy()
            self.profile_scale = (self.profile_scale_xy.x + self.profile_scale_xy.y) * 0.5
            self.depth_scale = self.scale_base_depth
            self._update_mesh(context)
            self._accept_transform_phase()
            return True
        if self.phase == 'TAPER':
            self.taper_factor = self.taper_base_factor
            self.taper_enabled = abs(self.taper_factor) > 1e-8
            self._update_mesh(context)
            self._accept_transform_phase()
            return True
        if self.phase == 'OFFSET':
            self.offset_amount = self.offset_base_amount
            self._update_mesh(context)
            self._accept_transform_phase()
            return True
        if self.phase == 'INSET':
            self.inset_amount = self.inset_base_amount
            self.inset_enabled = self.inset_amount > 1e-8
            self._update_mesh(context)
            self._accept_transform_phase()
            return True
        if self.phase == 'RADIAL_ORIGIN':
            self.radial_origin = self.radial_origin_base.copy()
            self._update_mesh(context)
            self._accept_transform_phase()
            return True
        return False

    def _persist_modal_settings(self, context):
        s = self._settings(context)
        s.operation = self.mode
        s.inset_enabled = self.inset_enabled
        s.inset_amount = self.inset_amount
        s.offset_amount = self.offset_amount
        s.cutter_bevel = self.cutter_bevel_enabled
        s.array_enabled = self.array_mode != 'OFF'
        s.array_mode = self.array_mode
        s.taper_enabled = self.taper_enabled
        s.taper_factor = self.taper_factor
        s.mirror_mode = self.mirror_mode
        s.draw_origin = self.draw_origin
        s.orientation = self.orientation_mode
        s.through_cut = self.through_cut
        s.live_solidify = self.live_solidify
        s.mirror_origin = self.mirror_origin
        s.radial_origin = self.radial_origin if self.radial_origin is not None else Vector((0.0, 0.0))
        s.extrude_direction = self.extrude_direction

    def _finish(self, context):
        s = self._settings(context)
        if not self.cutter or len(self._profile_points(False)) < 3:
            self._cleanup_ui(context)
            return {'CANCELLED'}

        self._persist_modal_settings(context)
        target_finish = self.mode not in {'EXTRACT', 'MAKE'}

        if self.mode == 'KNIFE':
            # Remove the live preview Boolean before building the destructive partition.
            if self.bool_mod and self.bool_mod.name in self.target.modifiers:
                self.target.modifiers.remove(self.bool_mod)
            self.bool_mod = None
            try:
                caps, duplicates = utils.make_knife_imprint(
                    context, self.target, self.cutter, s.solver, s.knife_merge_distance
                )
                self.report(
                    {'INFO'},
                    f"Knife imprint rebuilt topology; removed {caps} interface and {duplicates} duplicate face(s)"
                )
            except Exception as exc:
                self.report({'ERROR'}, f"Knife imprint failed: {exc}")
                return self._cancel(context)

        elif self.mode == 'EXTRACT':
            if self.bool_mod and self.bool_mod.name in self.target.modifiers:
                self.target.modifiers.remove(self.bool_mod)
            self.bool_mod = None
            self.extract_clone, extract_mod = utils.create_extract(
                context, self.target, self.cutter, s.solver
            )
            if s.auto_bevel:
                utils.ensure_bevel(self.extract_clone, s.bevel_width, s.bevel_segments)
            if s.weighted_normals:
                utils.ensure_weighted_normal(self.extract_clone)
            utils.sort_target_modifiers(self.extract_clone)
            if s.apply_on_confirm:
                try:
                    utils.apply_modifier(context, self.extract_clone, extract_mod)
                except Exception as exc:
                    self.report({'WARNING'}, f"Could not apply Extract Boolean: {exc}")

        elif self.mode == 'MAKE':
            if self.bool_mod and self.bool_mod.name in self.target.modifiers:
                self.target.modifiers.remove(self.bool_mod)
            self.bool_mod = None
            if self.mirror_origin != 'CURSOR':
                utils.delete_origin_gizmo(self.cutter)
            self.cutter.name = f"KORO_{self.shape}_Shape"
            self.cutter["koro_cutter"] = False
            self.cutter["koro_made_shape"] = True
            utils.promote_cutter_to_shape(context, self.cutter, self.target)
            self.cutter.display_type = 'SOLID'
            self.cutter.show_in_front = False
            self.cutter.hide_render = False
            # A made shape is an output object, not a disposable Boolean helper.

        else:
            if not self.bool_mod:
                self.report({'ERROR'}, "Boolean preview modifier is missing")
                return self._cancel(context)

            if self.mode == 'SLICE':
                self.slice_clone = utils.duplicate_for_slice(context, self.target, self.bool_mod)
                if s.auto_bevel:
                    utils.ensure_bevel(self.slice_clone, s.bevel_width, s.bevel_segments)
                if s.weighted_normals:
                    utils.ensure_weighted_normal(self.slice_clone)
                utils.sort_target_modifiers(self.slice_clone)

            if s.apply_on_confirm:
                try:
                    bool_name = self.bool_mod.name
                    clone_mod = self.slice_clone.modifiers.get(bool_name) if self.slice_clone else None
                    utils.apply_modifier(context, self.target, self.bool_mod)
                    if clone_mod:
                        utils.apply_modifier(context, self.slice_clone, clone_mod)
                except Exception as exc:
                    self.report({'WARNING'}, f"Could not apply modifier: {exc}")

        if self.cutter and self.mode != 'MAKE':
            # Persist enough metadata for Repeat/Stamp/Edit workflows in v0.8.
            self.cutter["koro_operation"] = self.mode if self.mode in {'DIFFERENCE', 'UNION', 'INTERSECT'} else 'DIFFERENCE'
            self.cutter["koro_shape"] = self.shape
            self.cutter["koro_inset_enabled"] = bool(self.inset_enabled)
            self.cutter["koro_inset_amount"] = float(self.inset_amount)
            self.cutter["koro_offset_amount"] = float(self.offset_amount)
            self.cutter["koro_depth"] = float(self.depth)
            self.cutter["koro_through"] = bool(self.through_cut or self.lazorcut)
            utils.mark_cutter_created(context.scene, self.cutter)

        if target_finish:
            if s.auto_bevel:
                utils.ensure_bevel(self.target, s.bevel_width, s.bevel_segments)
            if s.weighted_normals:
                utils.ensure_weighted_normal(self.target)
            utils.sort_target_modifiers(self.target)

        if self.mode == 'MAKE':
            self.cutter.select_set(True)
            self.target.select_set(False)
            context.view_layer.objects.active = self.cutter
        elif s.keep_cutters:
            self.cutter.display_type = 'WIRE'
            self.cutter.show_in_front = True
            self.cutter.select_set(False)
            if self.extract_clone:
                self.extract_clone.select_set(True)
                self.target.select_set(False)
                context.view_layer.objects.active = self.extract_clone
            else:
                self.target.select_set(True)
                context.view_layer.objects.active = self.target
        else:
            if s.apply_on_confirm or self.mode == 'KNIFE':
                utils.delete_object(self.cutter)
                self.cutter = None
            else:
                # Keep dependency helpers alive because live Mirror/Radial Array modifiers can reference them.
                self.cutter.hide_set(True)
                origin = bpy.data.objects.get(f"{self.cutter.name}{utils.ORIGIN_SUFFIX}")
                radial = bpy.data.objects.get(f"{self.cutter.name}{utils.RADIAL_SUFFIX}")
                if origin:
                    origin.hide_set(True)
                if radial:
                    radial.hide_set(True)

        self._cleanup_ui(context)
        self.report({'INFO'}, f"KORO {self.shape} cutter confirmed: {self.mode}")
        return {'FINISHED'}

    def _cancel(self, context):
        if self.bool_mod and self.target and self.bool_mod.name in self.target.modifiers:
            self.target.modifiers.remove(self.bool_mod)
        if self.cutter:
            utils.delete_origin_gizmo(self.cutter)
            utils.delete_radial_helper(self.cutter)
            utils.delete_object(self.cutter)
            self.cutter = None
        self._cleanup_ui(context)
        return {'CANCELLED'}

    def _cleanup_ui(self, context):
        self._remove_draw_handler()
        try:
            context.window.cursor_modal_restore()
        except Exception:
            pass
        if context.area:
            context.area.tag_redraw()

    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()

        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            if self.phase in {'ROTATE', 'MOVE', 'SCALE', 'TAPER', 'OFFSET', 'INSET', 'RADIAL_ORIGIN'}:
                self._cancel_transform_phase(context)
                return {'RUNNING_MODAL'}
            return self._cancel(context)

        if event.value == 'PRESS':
            if event.type == 'TAB' and self.phase == 'WAIT':
                self._cycle_shape()
                return {'RUNNING_MODAL'}
            if event.type == 'V':
                self._cycle_orientation(context, event)
                return {'RUNNING_MODAL'}
            if event.type == 'D' and event.ctrl:
                self.show_helper = not self.show_helper
                return {'RUNNING_MODAL'}
            if event.type == 'L':
                self.paused = not self.paused
                return {'RUNNING_MODAL'}
            if event.type == 'F':
                self._cycle_extrude_direction(context)
                return {'RUNNING_MODAL'}
            if event.type in {'X', 'Y', 'Z'} and self.phase in {'MOVE', 'SCALE', 'ROTATE'}:
                self._set_transform_axis(context, event, event.type)
                return {'RUNNING_MODAL'}
            if event.type == 'C' and self.shape == 'BOX':
                self._cycle_origin(context)
                return {'RUNNING_MODAL'}
            if event.type == 'X':
                self._set_mode(context, 'DIFFERENCE')
                return {'RUNNING_MODAL'}
            if event.type == 'J':
                self._set_mode(context, 'UNION')
                return {'RUNNING_MODAL'}
            if event.type == 'K':
                self._set_mode(context, 'KNIFE' if event.shift else 'SLICE')
                return {'RUNNING_MODAL'}
            if event.type == 'T':
                self._set_mode(context, 'EXTRACT')
                return {'RUNNING_MODAL'}
            if event.type == 'P':
                self._set_mode(context, 'MAKE')
                return {'RUNNING_MODAL'}
            if event.type == 'I':
                if self.phase == 'INSET':
                    self._accept_transform_phase()
                elif self.cutter and not event.shift:
                    self._begin_inset(event)
                else:
                    self.inset_enabled = not self.inset_enabled
                    if self.cutter:
                        self._update_mesh(context)
                return {'RUNNING_MODAL'}
            if event.type == 'B':
                self.cutter_bevel_enabled = not self.cutter_bevel_enabled
                if self.cutter:
                    self._update_mesh(context)
                return {'RUNNING_MODAL'}
            if event.type == 'A':
                self._cycle_array(context, radial_only=event.shift)
                return {'RUNNING_MODAL'}
            if event.type == 'M':
                self._cycle_mirror(context)
                return {'RUNNING_MODAL'}
            if event.type == 'O':
                if event.alt:
                    self._cycle_mirror_origin(context)
                elif event.shift:
                    if self.phase == 'RADIAL_ORIGIN':
                        self._accept_transform_phase()
                    else:
                        self._begin_radial_origin(context, event)
                elif self.phase == 'OFFSET':
                    self._accept_transform_phase()
                else:
                    self._begin_offset(event)
                return {'RUNNING_MODAL'}
            if event.type == 'Z':
                self._toggle_solidify(context)
                return {'RUNNING_MODAL'}
            if event.type == 'H':
                self._settings(context).show_origin_gizmo = not self._settings(context).show_origin_gizmo
                if self.cutter:
                    self._update_mesh(context)
                return {'RUNNING_MODAL'}
            if event.type == 'E':
                self.through_cut = not self.through_cut
                if self.cutter:
                    self._update_mesh(context)
                return {'RUNNING_MODAL'}
            if event.type == 'R':
                if self.phase == 'ROTATE':
                    self._accept_rotate()
                else:
                    self._begin_rotate(event)
                return {'RUNNING_MODAL'}
            if event.type == 'W':
                if self.phase == 'TAPER':
                    self._accept_transform_phase()
                elif event.shift:
                    self.taper_enabled = not self.taper_enabled
                    if self.cutter:
                        self._update_mesh(context)
                else:
                    self._begin_taper(event)
                return {'RUNNING_MODAL'}
            if event.type == 'D':
                self._settings(context).show_dots = not self._settings(context).show_dots
                return {'RUNNING_MODAL'}
            if event.type == 'S':
                if event.shift or self.phase == 'WAIT':
                    self._settings(context).snap_enabled = not self._settings(context).snap_enabled
                elif self.phase == 'SCALE':
                    self._accept_transform_phase()
                else:
                    self._begin_scale(event)
                return {'RUNNING_MODAL'}
            if event.type == 'G':
                if event.shift or self.phase == 'WAIT':
                    self._settings(context).geometry_snap = not self._settings(context).geometry_snap
                elif self.phase == 'MOVE':
                    self._accept_transform_phase()
                else:
                    self._begin_move(context, event)
                return {'RUNNING_MODAL'}
            if event.type == 'COMMA' and self.array_mode == 'LINEAR':
                self._adjust_array_gap(context, -1)
                return {'RUNNING_MODAL'}
            if event.type == 'PERIOD' and self.array_mode == 'LINEAR':
                self._adjust_array_gap(context, 1)
                return {'RUNNING_MODAL'}
            if event.type in {'LEFT_BRACKET', 'RIGHT_BRACKET'} and self.array_mode == 'RADIAL':
                step = math.radians(15.0) * (1 if event.type == 'RIGHT_BRACKET' else -1)
                self._settings(context).radial_sweep = max(-math.tau, min(math.tau, self._settings(context).radial_sweep + step))
                self._update_mesh(context)
                return {'RUNNING_MODAL'}
            if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and self.phase != 'ROTATE':
                self._adjust_wheel(context, event)
                return {'RUNNING_MODAL'}
            if event.type == 'BACK_SPACE' and self.phase == 'NGON':
                if len(self.ngon_points) > 1:
                    self.ngon_points.pop()
                    self.preview_point = self.ngon_points[-1].copy()
                    self._update_mesh(context)
                return {'RUNNING_MODAL'}
            if event.type == 'SPACE':
                if self.phase in {'DRAW', 'NGON'}:
                    return self._activate_lazorcut(context)
                if self.phase in {'ROTATE', 'MOVE', 'SCALE', 'TAPER', 'OFFSET', 'INSET', 'RADIAL_ORIGIN'}:
                    if self.phase == 'ROTATE':
                        self._accept_rotate()
                    else:
                        self._accept_transform_phase()
                    return {'RUNNING_MODAL'}
                if self.phase == 'DEPTH':
                    return self._finish(context)
            if event.type in {'RET', 'NUMPAD_ENTER'}:
                if self.phase == 'NGON':
                    self._close_ngon(context, event)
                    return {'RUNNING_MODAL'}
                if self.phase == 'ROTATE':
                    self._accept_rotate()
                    return {'RUNNING_MODAL'}
                if self.phase in {'MOVE', 'SCALE', 'TAPER', 'OFFSET', 'INSET', 'RADIAL_ORIGIN'}:
                    self._accept_transform_phase()
                    return {'RUNNING_MODAL'}
                if self.phase == 'DEPTH':
                    return self._finish(context)

        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS' and self.phase == 'WAIT':
                if self._begin_draw(context, event):
                    return {'RUNNING_MODAL'}
            elif event.value == 'PRESS' and self.phase == 'NGON':
                self._commit_ngon_point(context, event)
                return {'RUNNING_MODAL'}
            elif event.value == 'RELEASE' and self.phase == 'DRAW':
                if self._settings(context).quick_execute:
                    return self._activate_lazorcut(context)
                self.phase = 'DEPTH'
                self.depth_mouse_y = event.mouse_region_y
                return {'RUNNING_MODAL'}
            elif event.value == 'PRESS' and self.phase == 'ROTATE':
                self._accept_rotate()
                return {'RUNNING_MODAL'}
            elif event.value == 'PRESS' and self.phase in {'MOVE', 'SCALE', 'TAPER', 'OFFSET', 'INSET', 'RADIAL_ORIGIN'}:
                self._accept_transform_phase()
                return {'RUNNING_MODAL'}
            elif event.value == 'PRESS' and self.phase == 'DEPTH':
                return self._finish(context)

        if event.type == 'MOUSEMOVE':
            if self.paused:
                if self.phase == 'WAIT' and self._geometry_snap_active(context, event):
                    self._geometry_point(context, event)
                return {'RUNNING_MODAL'}
            if self.phase in {'DRAW', 'NGON'}:
                self._update_profile(context, event)
            elif self.phase == 'DEPTH':
                self._update_depth(context, event)
            elif self.phase == 'ROTATE':
                self._update_rotation(context, event)
            elif self.phase == 'MOVE':
                self._update_move(context, event)
            elif self.phase == 'SCALE':
                self._update_scale(context, event)
            elif self.phase == 'TAPER':
                self._update_taper(context, event)
            elif self.phase == 'OFFSET':
                self._update_offset(context, event)
            elif self.phase == 'INSET':
                self._update_inset(context, event)
            elif self.phase == 'RADIAL_ORIGIN':
                self._update_radial_origin(context, event)
            elif self.phase == 'WAIT' and self._geometry_snap_active(context, event):
                # Populate Ctrl-held snap dots before the first click.
                self._geometry_point(context, event)
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}
