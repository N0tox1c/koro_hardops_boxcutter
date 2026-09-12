bl_info = {
    "name": "KORO HardOps + BoxCutter Core",
    "author": "KORO Toolkit",
    "version": (0, 10, 0),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > KORO HS; Q menu",
    "description": "Interactive non-destructive hard-surface Boolean workflow",
    "category": "3D View",
}

import bpy
from bpy.props import PointerProperty

from .properties import KORO_HS_Settings
from .operators.boxcutter import KORO_OT_box_cutter
from .operators.hardops import (
    KORO_OT_smart_bevel,
    KORO_OT_weighted_normals,
    KORO_OT_sharpen,
    KORO_OT_boolean_selected,
    KORO_OT_apply_booleans,
    KORO_OT_custom_cutter_selected,
    KORO_OT_smart_apply,
    KORO_OT_clean_stack,
    KORO_OT_toggle_cutters,
    KORO_OT_sort_stack,
    KORO_OT_toggle_booleans,
    KORO_OT_modifier_scroll,
    KORO_OT_edit_cutter,
    KORO_OT_parametric_cutter_edit,
    KORO_OT_profile_edit_modal,
    KORO_OT_save_user_preset,
    KORO_OT_load_user_preset,
    KORO_OT_delete_user_preset,
    KORO_OT_batch_modifier_action,
    KORO_OT_array_modal,
    KORO_OT_dice_modal,
    KORO_OT_repeat_last_cutter,
    KORO_OT_stamp_cutter,
    KORO_OT_collection_boolean,
    KORO_OT_apply_cutter_preset,
    KORO_OT_quick_array,
    KORO_OT_dice,
    KORO_MT_hardops_q,
)
from .ui.panel import KORO_PT_hardsurface


classes = (
    KORO_HS_Settings,
    KORO_OT_box_cutter,
    KORO_OT_smart_bevel,
    KORO_OT_weighted_normals,
    KORO_OT_sharpen,
    KORO_OT_boolean_selected,
    KORO_OT_apply_booleans,
    KORO_OT_custom_cutter_selected,
    KORO_OT_smart_apply,
    KORO_OT_clean_stack,
    KORO_OT_toggle_cutters,
    KORO_OT_sort_stack,
    KORO_OT_toggle_booleans,
    KORO_OT_modifier_scroll,
    KORO_OT_edit_cutter,
    KORO_OT_parametric_cutter_edit,
    KORO_OT_profile_edit_modal,
    KORO_OT_save_user_preset,
    KORO_OT_load_user_preset,
    KORO_OT_delete_user_preset,
    KORO_OT_batch_modifier_action,
    KORO_OT_array_modal,
    KORO_OT_dice_modal,
    KORO_OT_repeat_last_cutter,
    KORO_OT_stamp_cutter,
    KORO_OT_collection_boolean,
    KORO_OT_apply_cutter_preset,
    KORO_OT_quick_array,
    KORO_OT_dice,
    KORO_MT_hardops_q,
    KORO_PT_hardsurface,
)

addon_keymaps = []


def register_keymaps():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    km = kc.keymaps.new(name='Object Mode', space_type='EMPTY')
    kmi = km.keymap_items.new('wm.call_menu', type='Q', value='PRESS')
    kmi.properties.name = KORO_MT_hardops_q.bl_idname
    addon_keymaps.append((km, kmi))


def unregister_keymaps():
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    addon_keymaps.clear()


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.koro_hs = PointerProperty(type=KORO_HS_Settings)
    register_keymaps()


def unregister():
    unregister_keymaps()
    if hasattr(bpy.types.Scene, "koro_hs"):
        del bpy.types.Scene.koro_hs
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
