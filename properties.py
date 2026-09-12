import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, FloatVectorProperty, PointerProperty, StringProperty


class KORO_HS_Settings(bpy.types.PropertyGroup):
    operation: EnumProperty(
        name="Operation",
        items=(
            ('DIFFERENCE', "Difference", "Subtract cutter from target"),
            ('UNION', "Union", "Join cutter volume to target"),
            ('SLICE', "Slice", "Keep outside and intersected slice"),
            ('KNIFE', "Knife / Imprint", "Preserve volume and imprint cutter boundary into topology"),
            ('EXTRACT', "Extract", "Keep target unchanged and create the intersected region"),
            ('MAKE', "Make", "Create cutter geometry without changing the target"),
        ),
        default='DIFFERENCE',
    )
    solver: EnumProperty(
        name="Solver",
        items=(
            ('EXACT', "Exact", "Robust solver with overlap support"),
            ('MANIFOLD', "Manifold", "Fast solver for manifold meshes"),
            ('FLOAT', "Float", "Fast solver for simple intersections"),
        ),
        default='EXACT',
    )
    default_depth: FloatProperty(
        name="Initial Depth", default=0.20, min=0.0001, soft_max=10.0, unit='LENGTH'
    )
    depth_sensitivity: FloatProperty(
        name="Depth Sensitivity", default=0.004, min=0.0001, max=0.1
    )
    surface_offset: FloatProperty(
        name="Surface Offset", default=0.001, min=0.0, soft_max=0.05, unit='LENGTH'
    )

    draw_origin: EnumProperty(
        name="Draw Origin",
        items=(
            ('CORNER', "Corner", "First click is a corner of the box"),
            ('CENTER', "Center", "First click is the center of the box"),
        ),
        default='CORNER',
    )
    orientation: EnumProperty(
        name="Orientation",
        items=(
            ('SURFACE', "Surface", "Align cutter to the hit surface normal"),
            ('VIEW', "View", "Align cutter to the current view"),
            ('WORLD', "World", "Align cutter to the nearest world axis"),
        ),
        default='SURFACE',
    )
    rotation_snap: FloatProperty(
        name="Rotation Snap", subtype='ANGLE', default=0.2617993878, min=0.0174532925, max=1.5707963268
    )
    extrude_direction: EnumProperty(
        name="Extrude Direction",
        items=(
            ('NEGATIVE', "Into Surface", "Extrude from the hit surface into the target"),
            ('POSITIVE', "Outward", "Extrude from the hit surface away from the target"),
            ('BOTH', "Both", "Extrude equally on both sides of the drawing plane"),
        ),
        default='NEGATIVE',
    )

    snap_enabled: BoolProperty(name="Grid Snap", default=False)
    grid_size: FloatProperty(
        name="Grid Size", default=0.05, min=0.00001, soft_max=10.0, unit='LENGTH'
    )
    geometry_snap: BoolProperty(name="Geometry Snap", default=True)
    snap_requires_ctrl: BoolProperty(
        name="Hold Ctrl for Snap Dots",
        description="Match Boxcutter-style behavior: geometry snapping and dots engage while Ctrl is held",
        default=True,
    )
    snap_pixel_radius: IntProperty(name="Geometry Snap Radius", default=14, min=3, max=64)
    snap_dot_radius: IntProperty(name="Snap Dot Display Radius", default=72, min=16, max=256)
    snap_dot_limit: IntProperty(name="Snap Dot Limit", default=48, min=4, max=256)
    snap_midpoints: BoolProperty(name="Edge Midpoint Dots", default=True)
    circle_segments: IntProperty(name="Circle Segments", default=32, min=6, max=256)

    through_cut: BoolProperty(name="Through / Extend", default=False)
    through_margin: FloatProperty(
        name="Through Margin", default=0.02, min=0.0001, soft_max=1.0, unit='LENGTH'
    )
    quick_execute: BoolProperty(
        name="Quick Execute / Lazorcut",
        description="Confirm the initial profile directly as a through-cut without entering manual depth",
        default=False,
    )
    offset_amount: FloatProperty(
        name="Surface Offset Adjust", default=0.0, min=-1000.0, max=1000.0, soft_min=-0.25, soft_max=0.25, unit='LENGTH'
    )

    inset_enabled: BoolProperty(name="Inset Cutter", default=False)
    inset_amount: FloatProperty(
        name="Inset Width", default=0.025, min=0.00001, soft_max=1.0, unit='LENGTH'
    )

    cutter_bevel: BoolProperty(name="Cutter Bevel", default=False)
    cutter_bevel_width: FloatProperty(
        name="Cutter Bevel Width", default=0.01, min=0.0, soft_max=0.25, unit='LENGTH'
    )
    cutter_bevel_segments: IntProperty(name="Cutter Bevel Segments", default=3, min=1, max=64)

    array_enabled: BoolProperty(name="Array (Legacy)", default=False)
    array_mode: EnumProperty(
        name="Array Mode",
        items=(
            ('OFF', "Off", "No cutter array"),
            ('LINEAR', "Linear", "Linear array along cutter local X"),
            ('RADIAL', "Radial", "Radial array using an object-offset helper"),
        ),
        default='OFF',
    )
    array_count: IntProperty(name="Array Count", default=2, min=2, max=256)
    array_gap: FloatProperty(
        name="Array Gap", default=0.05, min=-1000.0, soft_min=-1.0, soft_max=10.0, unit='LENGTH'
    )
    radial_sweep: FloatProperty(
        name="Radial Sweep", subtype='ANGLE', default=6.28318530718,
        min=-6.28318530718, max=6.28318530718,
        description="Total angular sweep distributed across the radial array"
    )
    radial_origin: FloatVectorProperty(
        name="Radial Origin",
        description="Radial Array pivot in cutter-local XY coordinates",
        size=2,
        default=(0.0, 0.0),
        subtype='NONE',
    )

    taper_enabled: BoolProperty(
        name="Wedge / Taper",
        description="Non-destructive taper along cutter local Z",
        default=False,
    )
    taper_factor: FloatProperty(
        name="Taper Factor", default=0.0, min=-10.0, max=10.0, soft_min=-2.0, soft_max=2.0
    )
    wedge_enabled: BoolProperty(
        name="Real Wedge",
        description="Build a real sloped cutter prism instead of a Simple Deform taper",
        default=False,
    )
    wedge_factor: FloatProperty(
        name="Wedge Factor", default=0.0, min=-4.0, max=4.0, soft_min=-1.5, soft_max=1.5
    )
    wedge_axis: EnumProperty(
        name="Wedge Axis",
        items=(('X', "X", "Slope top face across local X"), ('Y', "Y", "Slope top face across local Y")),
        default='X',
    )

    show_dots: BoolProperty(
        name="BoxCutter Dots",
        description="Show modal profile and snap dots",
        default=True,
    )
    dot_size: FloatProperty(name="Dot Size", default=8.0, min=2.0, max=32.0)
    show_parameter_handles: BoolProperty(
        name="Parameter Handles",
        description="Show draggable Depth / Inset / Bevel handles on the live cutter",
        default=True,
    )
    handle_size: FloatProperty(name="Handle Size", default=12.0, min=4.0, max=40.0)
    handle_pick_radius: IntProperty(name="Handle Pick Radius", default=18, min=6, max=64)

    mirror_mode: EnumProperty(
        name="Mirror",
        items=(
            ('OFF', "Off", "No cutter mirror"),
            ('X', "X", "Mirror around target X plane"),
            ('Y', "Y", "Mirror around target Y plane"),
            ('XY', "X + Y", "Mirror around target X and Y planes"),
        ),
        default='OFF',
    )


    live_solidify: BoolProperty(
        name="Live Solidify",
        description="Build cutter depth with a live Solidify modifier instead of baked prism geometry",
        default=True,
    )
    solidify_even: BoolProperty(
        name="Even Thickness",
        description="Request even-thickness correction when supported",
        default=True,
    )

    mirror_origin: EnumProperty(
        name="Mirror Origin",
        items=(
            ('CUTTER', "Cutter", "Mirror around the cutter origin"),
            ('TARGET', "Target", "Mirror around the target object origin"),
            ('CURSOR', "3D Cursor", "Mirror around the 3D Cursor with cutter orientation"),
        ),
        default='CUTTER',
    )
    show_origin_gizmo: BoolProperty(
        name="Show Origin Gizmo",
        description="Show a small axes helper for the active mirror origin",
        default=True,
    )
    knife_merge_distance: FloatProperty(
        name="Knife Merge Distance",
        description="Merge tolerance used when reconstructing an imprinted mesh",
        default=0.00001, min=0.0000001, soft_max=0.001, unit='LENGTH'
    )

    auto_bevel: BoolProperty(name="Target Auto Bevel", default=True)
    bevel_width: FloatProperty(
        name="Target Bevel Width", default=0.005, min=0.0, soft_max=0.1, unit='LENGTH'
    )
    bevel_segments: IntProperty(name="Target Bevel Segments", default=3, min=1, max=64)
    weighted_normals: BoolProperty(name="Weighted Normals", default=True)
    keep_cutters: BoolProperty(name="Keep Cutters", default=True)
    apply_on_confirm: BoolProperty(name="Apply Boolean on Confirm", default=False)
    show_hud: BoolProperty(name="Show Modal HUD", default=True)
    mark_sharp_angle: FloatProperty(
        name="Sharp Angle", subtype='ANGLE', default=0.523599, min=0.0, max=3.14159265
    )

    cutter_preset: EnumProperty(
        name="Cutter Preset",
        items=(
            ('PANEL', "Panel", "Inset panel cut with a small cutter bevel"),
            ('GROOVE', "Groove", "Thin inset groove/ring style cutter"),
            ('VENT', "Vent Array", "Linear repeated vent cutter setup"),
            ('BOLT', "Bolt / Hole", "Circular through-hole setup"),
            ('CLEAN', "Clean Boolean", "Minimal clean Boolean cutter"),
        ),
        default='PANEL',
    )
    collection_operand: PointerProperty(
        name="Boolean Collection",
        description="Collection used by native Collection Boolean",
        type=bpy.types.Collection,
    )
    collection_operation: EnumProperty(
        name="Collection Operation",
        items=(
            ('DIFFERENCE', "Difference", "Subtract the entire collection"),
            ('UNION', "Union", "Union the entire collection"),
            ('INTERSECT', "Intersect", "Intersect with every source mesh in the collection"),
        ),
        default='DIFFERENCE',
    )

    quick_array_axis: EnumProperty(
        name="Array Axis",
        items=(('X', "X", "Local X"), ('Y', "Y", "Local Y"), ('Z', "Z", "Local Z")),
        default='X',
    )
    quick_array_count: IntProperty(name="Quick Array Count", default=3, min=2, max=10000)
    quick_array_gap: FloatProperty(name="Quick Array Gap", default=0.05, min=-1000.0, max=1000.0, unit='LENGTH')

    dice_x: BoolProperty(name="Dice X", default=True)
    dice_y: BoolProperty(name="Dice Y", default=False)
    dice_z: BoolProperty(name="Dice Z", default=False)
    dice_count_x: IntProperty(name="X Cuts", default=3, min=1, max=128)
    dice_count_y: IntProperty(name="Y Cuts", default=3, min=1, max=128)
    dice_count_z: IntProperty(name="Z Cuts", default=3, min=1, max=128)
    dice_merge_distance: FloatProperty(name="Dice Epsilon", default=0.00001, min=0.0000001, max=0.01, unit='LENGTH')


    user_preset_slot: IntProperty(
        name="Preset Slot",
        description="Scene-local custom cutter preset slot",
        default=1, min=1, max=8,
    )
    user_preset_name: StringProperty(
        name="Preset Name",
        description="Optional label stored with the custom cutter preset",
        default="", maxlen=64,
    )

    batch_modifier_filter: EnumProperty(
        name="Modifier Filter",
        items=(
            ('KORO', "KORO", "Only KORO-generated modifiers"),
            ('BOOLEAN', "Boolean", "All Boolean modifiers"),
            ('BEVEL', "Bevel", "All Bevel modifiers"),
            ('ARRAY', "Array", "All Array modifiers"),
            ('MIRROR', "Mirror", "All Mirror modifiers"),
            ('SOLIDIFY', "Solidify", "All Solidify modifiers"),
            ('ALL', "All", "All modifiers"),
        ),
        default='KORO',
    )
    batch_modifier_action: EnumProperty(
        name="Batch Action",
        items=(
            ('TOGGLE_VIEW', "Toggle View", "Toggle viewport visibility"),
            ('ENABLE_VIEW', "Enable View", "Enable viewport visibility"),
            ('DISABLE_VIEW', "Disable View", "Disable viewport visibility"),
            ('TOGGLE_RENDER', "Toggle Render", "Toggle render visibility"),
            ('APPLY', "Apply", "Apply matching modifiers"),
            ('REMOVE', "Remove", "Remove matching modifiers"),
            ('SORT', "Sort", "Sort the KORO hard-surface stack"),
        ),
        default='TOGGLE_VIEW',
    )

