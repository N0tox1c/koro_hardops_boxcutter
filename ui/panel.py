import bpy
from bpy.types import Panel


class KORO_PT_hardsurface(Panel):
    bl_label = "KORO HardOps / BoxCutter"
    bl_idname = "KORO_PT_hardsurface"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'KORO HS'

    def draw(self, context):
        layout = self.layout
        s = context.scene.koro_hs

        box = layout.box()
        box.label(text="Interactive Cutter")
        row = box.row(align=True)
        op = row.operator("koro.box_cutter", text="Box", icon='MESH_CUBE')
        op.shape = 'BOX'
        op = row.operator("koro.box_cutter", text="Circle", icon='MESH_CIRCLE')
        op.shape = 'CIRCLE'
        op = row.operator("koro.box_cutter", text="NGon", icon='MESH_DATA')
        op.shape = 'NGON'
        box.label(text="Q = KORO HardOps menu")
        row = box.row(align=True)
        row.prop(s, "cutter_preset", text="")
        row.operator("koro.apply_cutter_preset", text="Apply", icon='PRESET')
        row = box.row(align=True)
        row.operator("koro.repeat_last_cutter", text="Repeat", icon='DUPLICATE')
        row.operator("koro.stamp_cutter", text="Stamp", icon='BRUSH_DATA')
        row.operator("koro.edit_cutter", text="Edit", icon='EDITMODE_HLT')

        col = layout.column(align=True)
        col.label(text="Boolean")
        col.prop(s, "operation", text="")
        col.prop(s, "solver")
        if s.operation == 'KNIFE':
            col.prop(s, "knife_merge_distance")
        row = col.row(align=True)
        row.prop(s, "default_depth")
        row.prop(s, "surface_offset")
        col.prop(s, "through_cut")
        col.prop(s, "quick_execute")
        col.prop(s, "offset_amount")
        sub = col.column(align=True)
        sub.enabled = s.through_cut
        sub.prop(s, "through_margin")

        layout.separator()
        col = layout.column(align=True)
        col.label(text="Draw / Orientation")
        col.prop(s, "draw_origin")
        col.prop(s, "orientation")
        col.prop(s, "rotation_snap")
        col.prop(s, "extrude_direction")
        col.prop(s, "circle_segments")

        layout.separator()
        col = layout.column(align=True)
        col.label(text="Snapping")
        col.prop(s, "snap_enabled")
        sub = col.column(align=True)
        sub.enabled = s.snap_enabled
        sub.prop(s, "grid_size")
        col.prop(s, "geometry_snap")
        sub = col.column(align=True)
        sub.enabled = s.geometry_snap
        sub.prop(s, "snap_requires_ctrl")
        sub.prop(s, "snap_pixel_radius")
        sub.prop(s, "snap_dot_radius")
        sub.prop(s, "snap_dot_limit")
        sub.prop(s, "snap_midpoints")

        layout.separator()
        col = layout.column(align=True)
        col.label(text="Cutter Shape")
        col.prop(s, "inset_enabled")
        sub = col.column(align=True)
        sub.enabled = s.inset_enabled
        sub.prop(s, "inset_amount")
        col.prop(s, "cutter_bevel")
        sub = col.column(align=True)
        sub.enabled = s.cutter_bevel
        sub.prop(s, "cutter_bevel_width")
        sub.prop(s, "cutter_bevel_segments")
        col.prop(s, "live_solidify")
        solid = col.column(align=True)
        solid.enabled = s.live_solidify
        solid.prop(s, "solidify_even")

        layout.separator()
        col = layout.column(align=True)
        col.label(text="Array / Mirror")
        col.prop(s, "array_mode")
        sub = col.column(align=True)
        sub.enabled = s.array_mode != 'OFF'
        sub.prop(s, "array_count")
        if s.array_mode == 'LINEAR':
            sub.prop(s, "array_gap")
        elif s.array_mode == 'RADIAL':
            sub.prop(s, "radial_sweep")
            sub.prop(s, "radial_origin")
        col.prop(s, "taper_enabled")
        sub = col.column(align=True)
        sub.enabled = s.taper_enabled
        sub.prop(s, "taper_factor")
        col.prop(s, "mirror_mode")
        col.prop(s, "mirror_origin")
        col.prop(s, "show_origin_gizmo")

        layout.separator()
        col = layout.column(align=True)
        col.label(text="Target Finish")
        col.prop(s, "auto_bevel")
        sub = col.column(align=True)
        sub.enabled = s.auto_bevel
        sub.prop(s, "bevel_width")
        sub.prop(s, "bevel_segments")
        col.prop(s, "weighted_normals")
        col.prop(s, "mark_sharp_angle")

        row = layout.row(align=True)
        row.operator("koro.sharpen", text="Sharpen")
        row.operator("koro.smart_bevel", text="Bevel")
        layout.operator("koro.weighted_normals", text="Weighted Normals")

        layout.separator()
        box = layout.box()
        box.label(text="Selected Mesh Booleans")
        row = box.row(align=True)
        op = row.operator("koro.boolean_selected", text="Difference")
        op.operation = 'DIFFERENCE'
        op = row.operator("koro.boolean_selected", text="Union")
        op.operation = 'UNION'
        row = box.row(align=True)
        op = row.operator("koro.boolean_selected", text="Intersect")
        op.operation = 'INTERSECT'
        op = row.operator("koro.custom_cutter_selected", text="Custom Cutter")
        op.operation = 'DIFFERENCE'

        box = layout.box()
        box.label(text="Collection Boolean")
        box.prop(s, "collection_operand", text="Collection")
        box.prop(s, "collection_operation", text="Operation")
        op = box.operator("koro.collection_boolean", text="Add Collection Boolean", icon='OUTLINER_COLLECTION')
        op.operation = s.collection_operation

        box = layout.box()
        box.label(text="HardOps Modeling")
        row = box.row(align=True)
        row.prop(s, "quick_array_axis", text="Axis")
        row.prop(s, "quick_array_count", text="Count")
        box.prop(s, "quick_array_gap")
        box.operator("koro.quick_array", text="Quick Array", icon='MOD_ARRAY')
        row = box.row(align=True)
        row.prop(s, "dice_x", toggle=True)
        row.prop(s, "dice_y", toggle=True)
        row.prop(s, "dice_z", toggle=True)
        row = box.row(align=True)
        row.prop(s, "dice_count_x", text="X")
        row.prop(s, "dice_count_y", text="Y")
        row.prop(s, "dice_count_z", text="Z")
        box.prop(s, "dice_merge_distance")
        box.operator("koro.dice", text="Dice Active Mesh", icon='MOD_WIREFRAME')

        layout.separator()
        col = layout.column(align=True)
        col.label(text="Cutter Lifecycle")
        col.prop(s, "keep_cutters")
        col.prop(s, "apply_on_confirm")
        col.prop(s, "show_hud")
        col.prop(s, "show_dots")
        dots = col.column(align=True)
        dots.enabled = s.show_dots
        dots.prop(s, "dot_size")
        col.operator("koro.toggle_cutters", text="Show / Hide Cutters")

        layout.separator()
        row = layout.row(align=True)
        row.operator("koro.apply_booleans", text="Apply Bool")
        row.operator("koro.smart_apply", text="Smart Apply")
        row = layout.row(align=True)
        row.operator("koro.clean_stack", text="Clean Stack")
        row = layout.row(align=True)
        row.operator("koro.sort_stack", text="Sort Stack")
        row.operator("koro.toggle_booleans", text="Toggle Bool")
        layout.operator("koro.modifier_scroll", text="Interactive Modifier Manager")
