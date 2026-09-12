import math
import bpy
import blf
import bmesh
from mathutils import Vector, Matrix
from bpy.props import EnumProperty
from bpy.types import Operator, Menu
from .. import utils


class KORO_OT_smart_bevel(Operator):
    bl_idname = "koro.smart_bevel"
    bl_label = "Smart Bevel"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.koro_hs
        count = 0
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                utils.ensure_bevel(obj, s.bevel_width, s.bevel_segments)
                utils.sort_target_modifiers(obj)
                count += 1
        self.report({'INFO'}, f"Bevel configured on {count} object(s)")
        return {'FINISHED'}


class KORO_OT_weighted_normals(Operator):
    bl_idname = "koro.weighted_normals"
    bl_label = "Weighted Normals"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                utils.ensure_weighted_normal(obj)
                utils.sort_target_modifiers(obj)
                count += 1
        self.report({'INFO'}, f"Weighted normals on {count} object(s)")
        return {'FINISHED'}


class KORO_OT_sharpen(Operator):
    bl_idname = "koro.sharpen"
    bl_label = "Sharpen"
    bl_description = "Mark hard-surface edges sharp using an angle threshold"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        angle = context.scene.koro_hs.mark_sharp_angle
        total = 0
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                total += utils.mark_sharp_by_angle(obj, angle)
        self.report({'INFO'}, f"Sharpened {total} edge(s)")
        return {'FINISHED'}


class KORO_OT_boolean_selected(Operator):
    bl_idname = "koro.boolean_selected"
    bl_label = "Boolean Selected"
    bl_description = "Use selected mesh objects as non-destructive cutters on the active mesh"
    bl_options = {'REGISTER', 'UNDO'}

    operation: EnumProperty(
        name="Operation",
        items=(
            ('DIFFERENCE', "Difference", "Subtract selected cutters"),
            ('UNION', "Union", "Union selected cutters"),
            ('INTERSECT', "Intersect", "Keep only the target/cutter intersection"),
        ),
        default='DIFFERENCE',
    )

    @classmethod
    def poll(cls, context):
        target = context.active_object
        return target and target.type == 'MESH' and context.mode == 'OBJECT'

    def execute(self, context):
        s = context.scene.koro_hs
        target = context.active_object
        cutters = [o for o in context.selected_objects if o != target and o.type == 'MESH']
        if not cutters:
            self.report({'WARNING'}, "Select one or more cutter meshes plus the active target")
            return {'CANCELLED'}

        count = 0
        for cutter in cutters:
            utils.add_boolean(target, cutter, self.operation, s.solver)
            cutter.display_type = 'WIRE'
            cutter.show_in_front = True
            cutter.hide_render = True
            cutter["koro_cutter"] = True
            count += 1

        if s.auto_bevel:
            utils.ensure_bevel(target, s.bevel_width, s.bevel_segments)
        if s.weighted_normals:
            utils.ensure_weighted_normal(target)
        utils.sort_target_modifiers(target)
        self.report({'INFO'}, f"Added {count} {self.operation.lower()} Boolean(s)")
        return {'FINISHED'}


class KORO_OT_custom_cutter_selected(Operator):
    bl_idname = "koro.custom_cutter_selected"
    bl_label = "Custom Cutter from Selected"
    bl_description = "Duplicate selected mesh shapes into KORO cutters and Boolean them against the active target"
    bl_options = {'REGISTER', 'UNDO'}

    operation: EnumProperty(
        name="Operation",
        items=(
            ('DIFFERENCE', "Difference", "Subtract custom shape"),
            ('UNION', "Union", "Join custom shape"),
            ('INTERSECT', "Intersect", "Keep intersection"),
        ),
        default='DIFFERENCE',
    )

    @classmethod
    def poll(cls, context):
        target = context.active_object
        return target is not None and target.type == 'MESH' and context.mode == 'OBJECT'

    def execute(self, context):
        s = context.scene.koro_hs
        target = context.active_object
        sources = [o for o in context.selected_objects if o != target and o.type == 'MESH']
        if not sources:
            self.report({'WARNING'}, "Select custom mesh shape(s), then make the Boolean target active")
            return {'CANCELLED'}

        col = utils.ensure_cutter_collection(context.scene)
        made = []
        for source in sources:
            cutter = source.copy()
            cutter.data = source.data.copy()
            cutter.name = f"KORO_Custom_{source.name}"
            col.objects.link(cutter)
            cutter.matrix_world = source.matrix_world.copy()
            cutter.display_type = 'WIRE'
            cutter.show_in_front = True
            cutter.hide_render = True
            cutter["koro_cutter"] = True
            cutter["koro_custom_source"] = source.name
            cutter["koro_operation"] = self.operation
            utils.mark_cutter_created(context.scene, cutter)
            utils.add_boolean(target, cutter, self.operation, s.solver)
            made.append(cutter)

        if s.auto_bevel:
            utils.ensure_bevel(target, s.bevel_width, s.bevel_segments)
        if s.weighted_normals:
            utils.ensure_weighted_normal(target)
        utils.sort_target_modifiers(target)

        for obj in context.selected_objects:
            obj.select_set(False)
        target.select_set(True)
        context.view_layer.objects.active = target
        self.report({'INFO'}, f"Created {len(made)} custom non-destructive cutter(s)")
        return {'FINISHED'}


class KORO_OT_smart_apply(Operator):
    bl_idname = "koro.smart_apply"
    bl_label = "Smart Apply"
    bl_description = "Apply KORO/Boolean hard-surface modifiers in current stack order"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objects = [o for o in context.selected_objects if o.type == 'MESH']
        if not objects and context.active_object and context.active_object.type == 'MESH':
            objects = [context.active_object]
        applied = 0
        skipped = 0
        for obj in objects:
            candidates = [
                m for m in list(obj.modifiers)
                if m.name.startswith('KORO_') or m.type in {'BOOLEAN'}
            ]
            for mod in candidates:
                try:
                    utils.apply_modifier(context, obj, mod)
                    applied += 1
                except Exception:
                    skipped += 1
        self.report({'INFO'}, f"Smart Apply: {applied} applied, {skipped} skipped")
        return {'FINISHED'}


class KORO_OT_apply_booleans(Operator):
    bl_idname = "koro.apply_booleans"
    bl_label = "Apply Booleans"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        mods = [m for m in obj.modifiers if m.type == 'BOOLEAN']
        applied = 0
        for mod in mods:
            try:
                utils.apply_modifier(context, obj, mod)
                applied += 1
            except Exception as exc:
                self.report({'WARNING'}, f"Skipped {mod.name}: {exc}")
        self.report({'INFO'}, f"Applied {applied} Boolean modifier(s)")
        return {'FINISHED'}


class KORO_OT_clean_stack(Operator):
    bl_idname = "koro.clean_stack"
    bl_label = "Clean Boolean Stack"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        removed = 0
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                removed += utils.clean_orphan_booleans(obj)
                utils.sort_target_modifiers(obj)
        self.report({'INFO'}, f"Removed {removed} orphan Boolean modifier(s)")
        return {'FINISHED'}


class KORO_OT_toggle_cutters(Operator):
    bl_idname = "koro.toggle_cutters"
    bl_label = "Toggle Cutters"
    bl_options = {'REGISTER'}

    def execute(self, context):
        col = bpy.data.collections.get(utils.CUTTER_COLLECTION)
        if col is None:
            self.report({'INFO'}, "No KORO cutter collection yet")
            return {'FINISHED'}
        new_state = not col.hide_viewport
        col.hide_viewport = new_state
        self.report({'INFO'}, "Cutters hidden" if new_state else "Cutters visible")
        return {'FINISHED'}



class KORO_OT_parametric_cutter_edit(Operator):
    bl_idname = "koro.parametric_cutter_edit"
    bl_label = "Parametric Cutter Edit"
    bl_description = "Re-open a v0.9 KORO cutter and edit stored parametric values without baking the Boolean"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    _handle = None
    cutter = None
    target = None
    parameter = 'DEPTH'
    start_x = 0
    start_value = 0.0
    original = None

    PARAMS = ('DEPTH', 'INSET', 'BEVEL', 'OFFSET', 'TAPER', 'WEDGE', 'ARRAY_COUNT', 'ARRAY_GAP')

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return context.area and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT' and obj is not None

    def _find_cutter(self, context):
        active = context.active_object
        if active and active.type == 'MESH' and active.get('koro_cutter', False):
            return active
        if active and active.type == 'MESH':
            for mod in reversed(list(active.modifiers)):
                if mod.type == 'BOOLEAN' and getattr(mod, 'operand_type', 'OBJECT') == 'OBJECT':
                    ob = getattr(mod, 'object', None)
                    if ob and ob.type == 'MESH' and ob.get('koro_cutter', False):
                        return ob
        return utils.last_cutter(context.scene)

    def _value(self):
        c = self.cutter
        if self.parameter == 'DEPTH': return float(c.get('koro_depth', 0.2))
        if self.parameter == 'INSET': return float(c.get('koro_inset_amount', 0.025))
        if self.parameter == 'BEVEL': return float(c.get('koro_cutter_bevel_width', 0.01))
        if self.parameter == 'OFFSET': return float(c.get('koro_offset_amount', 0.0))
        if self.parameter == 'TAPER': return float(c.get('koro_taper_factor', 0.0))
        if self.parameter == 'WEDGE': return float(c.get('koro_wedge_factor', 0.0))
        if self.parameter == 'ARRAY_COUNT': return float(c.get('koro_array_count', 2))
        return float(c.get('koro_array_gap', 0.05))

    def _set_value(self, value):
        c = self.cutter
        if self.parameter == 'DEPTH': c['koro_depth'] = max(0.0001, float(value))
        elif self.parameter == 'INSET':
            c['koro_inset_enabled'] = True; c['koro_inset_amount'] = max(0.00001, float(value))
        elif self.parameter == 'BEVEL':
            c['koro_cutter_bevel_enabled'] = True; c['koro_cutter_bevel_width'] = max(0.0, float(value))
        elif self.parameter == 'OFFSET': c['koro_offset_amount'] = float(value)
        elif self.parameter == 'TAPER':
            c['koro_taper_enabled'] = True; c['koro_taper_factor'] = max(-10.0, min(10.0, float(value)))
        elif self.parameter == 'WEDGE':
            c['koro_wedge_enabled'] = True; c['koro_wedge_factor'] = max(-4.0, min(4.0, float(value)))
        elif self.parameter == 'ARRAY_COUNT':
            c['koro_array_count'] = max(2, min(256, int(round(value))))
            if c.get('koro_array_mode', 'OFF') == 'OFF': c['koro_array_mode'] = 'LINEAR'
        elif self.parameter == 'ARRAY_GAP':
            c['koro_array_gap'] = float(value)
            if c.get('koro_array_mode', 'OFF') == 'OFF': c['koro_array_mode'] = 'LINEAR'

    def _snapshot(self):
        keys = [
            'koro_depth','koro_inset_enabled','koro_inset_amount','koro_cutter_bevel_enabled','koro_cutter_bevel_width',
            'koro_offset_amount','koro_taper_enabled','koro_taper_factor','koro_wedge_enabled','koro_wedge_factor','koro_wedge_axis',
            'koro_array_mode','koro_array_count','koro_array_gap'
        ]
        return {k: self.cutter.get(k, None) for k in keys}

    def _restore(self):
        for key, value in self.original.items():
            if value is None:
                try: del self.cutter[key]
                except Exception: pass
            else:
                self.cutter[key] = value
        utils.rebuild_cutter_from_metadata(bpy.context, self.cutter, self.target)

    def _draw_hud(self, context):
        x, y = 28, context.region.height - 42
        font = 0
        def line(text, size=14):
            nonlocal y
            blf.position(font, x, y, 0)
            try: blf.size(font, size)
            except TypeError: blf.size(font, size, 72)
            blf.draw(font, text); y -= 20
        line('KORO PARAMETRIC EDIT v0.9', 18)
        line(f'{self.cutter.name}  |  {self.parameter}: {self._value():.5g}')
        line('Mouse = adjust | Wheel = fine | Tab = next parameter | D/I/B/O/T/W/A/G = direct')
        line('X/Y = Wedge axis | LMB = re-anchor | Enter = finish | Esc/RMB = rollback', 12)

    def _select_param(self, event_type):
        mapping = {'D':'DEPTH','I':'INSET','B':'BEVEL','O':'OFFSET','T':'TAPER','W':'WEDGE','A':'ARRAY_COUNT','G':'ARRAY_GAP'}
        if event_type in mapping:
            self.parameter = mapping[event_type]
            return True
        return False

    def _reanchor(self, event):
        self.start_x = event.mouse_region_x
        self.start_value = self._value()

    def invoke(self, context, event):
        self.cutter = self._find_cutter(context)
        if self.cutter is None:
            self.report({'WARNING'}, 'No KORO cutter found')
            return {'CANCELLED'}
        self.target = utils.find_target_for_cutter(context.scene, self.cutter)
        if not utils.ensure_parametric_metadata(context, self.cutter, self.target):
            self.report({'WARNING'}, 'Could not recover a parametric profile from this cutter')
            return {'CANCELLED'}
        self.original = self._snapshot()
        self.parameter = 'DEPTH'
        self._reanchor(event)
        self.cutter.hide_set(False); self.cutter.hide_viewport = False
        self._handle = bpy.types.SpaceView3D.draw_handler_add(self._draw_hud, (context,), 'WINDOW', 'POST_PIXEL')
        context.window.cursor_modal_set('SCROLL_X')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _cleanup(self, context):
        if self._handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW'); self._handle = None
        try: context.window.cursor_modal_restore()
        except Exception: pass
        context.workspace.status_text_set(None)
        if context.area: context.area.tag_redraw()

    def modal(self, context, event):
        if context.area: context.area.tag_redraw()
        if event.type in {'ESC','RIGHTMOUSE'} and event.value == 'PRESS':
            self._restore(); self._cleanup(context); return {'CANCELLED'}
        if event.type in {'RET','NUMPAD_ENTER'} and event.value == 'PRESS':
            self._cleanup(context); self.report({'INFO'}, f'Parametric edit saved: {self.cutter.name}'); return {'FINISHED'}
        if event.type == 'TAB' and event.value == 'PRESS':
            i = (self.PARAMS.index(self.parameter) + 1) % len(self.PARAMS); self.parameter = self.PARAMS[i]; self._reanchor(event); return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and self._select_param(event.type):
            self._reanchor(event); return {'RUNNING_MODAL'}
        if self.parameter == 'WEDGE' and event.value == 'PRESS' and event.type in {'X','Y'}:
            self.cutter['koro_wedge_axis'] = event.type; utils.rebuild_cutter_from_metadata(context, self.cutter, self.target); return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self._reanchor(event); return {'RUNNING_MODAL'}
        if event.type == 'MOUSEMOVE':
            dx = event.mouse_region_x - self.start_x
            scale = max(self.target.dimensions.length if self.target else self.cutter.dimensions.length, 1.0)
            if self.parameter in {'DEPTH','INSET','BEVEL','OFFSET','ARRAY_GAP'}:
                step = 0.001 * scale
            elif self.parameter == 'ARRAY_COUNT':
                step = 0.05
            else:
                step = 0.01
            value = self.start_value + dx * step
            if event.ctrl:
                if self.parameter == 'ARRAY_COUNT': value = round(value)
                elif self.parameter in {'TAPER','WEDGE'}: value = round(value * 10.0) / 10.0
                else:
                    grid = max(context.scene.koro_hs.grid_size * 0.1, 0.0001); value = round(value / grid) * grid
            self._set_value(value); utils.rebuild_cutter_from_metadata(context, self.cutter, self.target); return {'RUNNING_MODAL'}
        if event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'} and event.value == 'PRESS':
            direction = 1 if event.type == 'WHEELUPMOUSE' else -1
            if self.parameter == 'ARRAY_COUNT': delta = direction
            elif self.parameter in {'TAPER','WEDGE'}: delta = direction * 0.05
            else: delta = direction * max(context.scene.koro_hs.grid_size * 0.05, 0.0001)
            self._set_value(self._value() + delta); utils.rebuild_cutter_from_metadata(context, self.cutter, self.target); self._reanchor(event); return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}


class KORO_OT_array_modal(Operator):
    bl_idname = 'koro.array_modal'
    bl_label = 'Array Modal'
    bl_description = 'Interactive HardOps-style Array count/axis/gap editor'
    bl_options = {'REGISTER','UNDO','BLOCKING'}

    obj = None; mod = None; created = False; axis = 'X'; count = 3; gap = 0.05; start_x = 0; base_gap = 0.05; old = None

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT' and context.active_object and context.active_object.type == 'MESH'

    def _apply(self):
        axis_i = {'X':0,'Y':1,'Z':2}[self.axis]
        self.mod.count = max(2, int(self.count)); self.mod.fit_type='FIXED_COUNT'; self.mod.use_relative_offset=False; self.mod.use_constant_offset=True
        span=max(float(self.obj.dimensions[axis_i]),0.0001); vec=[0.0,0.0,0.0]; vec[axis_i]=span+self.gap; self.mod.constant_offset_displace=vec

    def invoke(self, context, event):
        s=context.scene.koro_hs; self.obj=context.active_object; self.axis=s.quick_array_axis; self.count=s.quick_array_count; self.gap=s.quick_array_gap
        self.mod=self.obj.modifiers.get('KORO_QuickArray'); self.created=self.mod is None
        if self.mod is None: self.mod=self.obj.modifiers.new(name='KORO_QuickArray', type='ARRAY')
        self.old=(self.mod.count, tuple(self.mod.constant_offset_displace), self.mod.use_relative_offset, self.mod.use_constant_offset)
        self.start_x=event.mouse_region_x; self.base_gap=self.gap; self._apply(); context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set('KORO Array Modal: Mouse gap | Wheel count | X/Y/Z axis | Enter/LMB accept | Esc rollback')
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            scale=max(self.obj.dimensions.length,1.0); self.gap=self.base_gap+(event.mouse_region_x-self.start_x)*0.001*scale; self._apply(); return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and event.type in {'X','Y','Z'}:
            self.axis=event.type; self._apply(); return {'RUNNING_MODAL'}
        if event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'} and event.value == 'PRESS':
            self.count=max(2,min(10000,self.count+(1 if event.type=='WHEELUPMOUSE' else -1))); self._apply(); return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and event.type in {'RET','NUMPAD_ENTER','LEFTMOUSE'}:
            s=context.scene.koro_hs; s.quick_array_axis=self.axis; s.quick_array_count=self.count; s.quick_array_gap=self.gap; context.workspace.status_text_set(None); return {'FINISHED'}
        if event.value == 'PRESS' and event.type in {'ESC','RIGHTMOUSE'}:
            if self.created: self.obj.modifiers.remove(self.mod)
            else:
                self.mod.count=self.old[0]; self.mod.constant_offset_displace=self.old[1]; self.mod.use_relative_offset=self.old[2]; self.mod.use_constant_offset=self.old[3]
            context.workspace.status_text_set(None); return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class KORO_OT_dice_modal(Operator):
    bl_idname = 'koro.dice_modal'
    bl_label = 'Dice Modal'
    bl_description = 'Interactive Dice setup; topology is changed only when confirmed'
    bl_options = {'REGISTER','UNDO','BLOCKING'}

    axis = 'X'; original = None

    @classmethod
    def poll(cls, context):
        return context.area and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT' and context.active_object and context.active_object.type == 'MESH'

    def _status(self, context):
        s=context.scene.koro_hs; count={'X':s.dice_count_x,'Y':s.dice_count_y,'Z':s.dice_count_z}[self.axis]
        context.workspace.status_text_set(f'KORO Dice Modal: axis {self.axis} count {count} | X/Y/Z select | Shift+X/Y/Z toggle | Wheel count | Enter apply | Esc cancel')

    def invoke(self, context, event):
        s=context.scene.koro_hs; self.original=(s.dice_x,s.dice_y,s.dice_z,s.dice_count_x,s.dice_count_y,s.dice_count_z); self.axis='X'; self._status(context); context.window_manager.modal_handler_add(self); return {'RUNNING_MODAL'}

    def modal(self, context, event):
        s=context.scene.koro_hs
        if event.value == 'PRESS' and event.type in {'X','Y','Z'}:
            self.axis=event.type
            attr='dice_'+event.type.lower()
            if event.shift: setattr(s,attr,not getattr(s,attr))
            else: setattr(s,attr,True)
            self._status(context); return {'RUNNING_MODAL'}
        if event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'} and event.value == 'PRESS':
            attr='dice_count_'+self.axis.lower(); setattr(s,attr,max(1,min(128,getattr(s,attr)+(1 if event.type=='WHEELUPMOUSE' else -1)))); self._status(context); return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and event.type in {'RET','NUMPAD_ENTER','LEFTMOUSE'}:
            context.workspace.status_text_set(None); return bpy.ops.koro.dice('EXEC_DEFAULT')
        if event.value == 'PRESS' and event.type in {'ESC','RIGHTMOUSE'}:
            s.dice_x,s.dice_y,s.dice_z,s.dice_count_x,s.dice_count_y,s.dice_count_z=self.original; context.workspace.status_text_set(None); return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class KORO_OT_edit_cutter(Operator):
    bl_idname = "koro.edit_cutter"
    bl_label = "Edit Cutter Shape"
    bl_description = "Reveal the cutter driving the active Boolean and enter mesh Edit Mode"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_MESH'} and context.active_object is not None

    def execute(self, context):
        if context.mode == 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='OBJECT')
        active = context.active_object
        cutter = active if active.type == 'MESH' and active.get("koro_cutter", False) else None
        if cutter is None and active.type == 'MESH':
            for mod in reversed(list(active.modifiers)):
                if mod.type == 'BOOLEAN' and getattr(mod, 'operand_type', 'OBJECT') == 'OBJECT':
                    obj = getattr(mod, 'object', None)
                    if obj is not None and obj.type == 'MESH':
                        cutter = obj
                        break
        if cutter is None:
            cutter = utils.last_cutter(context.scene)
        if cutter is None:
            self.report({'WARNING'}, "No editable KORO cutter found")
            return {'CANCELLED'}
        cutter.hide_set(False)
        cutter.hide_viewport = False
        for obj in context.selected_objects:
            obj.select_set(False)
        cutter.select_set(True)
        context.view_layer.objects.active = cutter
        try:
            bpy.ops.object.mode_set(mode='EDIT')
        except Exception as exc:
            self.report({'WARNING'}, f"Could not enter Edit Mode: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Editing live cutter: {cutter.name}")
        return {'FINISHED'}


class KORO_OT_repeat_last_cutter(Operator):
    bl_idname = "koro.repeat_last_cutter"
    bl_label = "Repeat Last Cutter"
    bl_description = "Duplicate the most recent KORO cutter with its live modifiers and Boolean it against the active target"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return context.mode == 'OBJECT' and obj is not None and obj.type == 'MESH'

    def execute(self, context):
        target = context.active_object
        source = utils.last_cutter(context.scene)
        if source is None:
            self.report({'WARNING'}, "No previous KORO cutter to repeat")
            return {'CANCELLED'}
        if source == target:
            self.report({'WARNING'}, "Make the Boolean target active, not the cutter")
            return {'CANCELLED'}
        cutter = utils.duplicate_cutter(context, source, "KORO_Repeat")
        if cutter is None:
            return {'CANCELLED'}
        s = context.scene.koro_hs
        op = source.get("koro_operation", 'DIFFERENCE')
        if op not in {'DIFFERENCE', 'UNION', 'INTERSECT'}:
            op = 'DIFFERENCE'
        utils.add_boolean(target, cutter, op, s.solver)
        if s.auto_bevel:
            utils.ensure_bevel(target, s.bevel_width, s.bevel_segments)
        if s.weighted_normals:
            utils.ensure_weighted_normal(target)
        utils.sort_target_modifiers(target)
        self.report({'INFO'}, f"Repeated cutter: {cutter.name}")
        return {'FINISHED'}


class KORO_OT_stamp_cutter(Operator):
    bl_idname = "koro.stamp_cutter"
    bl_label = "Stamp Cutter"
    bl_description = "Repeatedly stamp the last KORO cutter onto the active target surface"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    source = None
    target = None
    preview = None
    preview_bool = None
    angle = 0.0
    operation = 'DIFFERENCE'

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return context.area and context.area.type == 'VIEW_3D' and context.mode == 'OBJECT' and obj is not None and obj.type == 'MESH'

    def _new_preview(self, context):
        self.preview = utils.duplicate_cutter(context, self.source, "KORO_Stamp")
        if self.preview is None:
            return False
        self.preview_bool = utils.add_boolean(self.target, self.preview, self.operation, context.scene.koro_hs.solver)
        return True

    def _remove_preview(self):
        if self.preview_bool and self.target and self.preview_bool.name in self.target.modifiers:
            self.target.modifiers.remove(self.preview_bool)
        if self.preview:
            utils.delete_object(self.preview)
        self.preview = None
        self.preview_bool = None

    def _place(self, context, event):
        if not self.preview:
            return
        hit = utils.raycast_scene(context, (event.mouse_region_x, event.mouse_region_y), self.target)
        if hit is None:
            return
        loc, normal, _fi, _obj = hit
        x, y, z = utils.surface_basis(context, normal)
        c, si = math.cos(self.angle), math.sin(self.angle)
        xr = (x * c + y * si).normalized()
        yr = (-x * si + y * c).normalized()
        scale = self.source.matrix_world.to_scale()
        mat = utils.basis_matrix(xr, yr, z, loc)
        sm = Matrix.Diagonal((scale.x, scale.y, scale.z, 1.0))
        self.preview.matrix_world = mat @ sm

    def invoke(self, context, event):
        self.target = context.active_object
        selected_sources = [o for o in context.selected_objects if o != self.target and o.type == 'MESH' and o.get("koro_cutter", False)]
        self.source = selected_sources[-1] if selected_sources else utils.last_cutter(context.scene)
        if self.source is None or self.source == self.target:
            self.report({'WARNING'}, "Need a previous/selected KORO cutter and an active target")
            return {'CANCELLED'}
        self.operation = self.source.get("koro_operation", 'DIFFERENCE')
        if self.operation not in {'DIFFERENCE', 'UNION', 'INTERSECT'}:
            self.operation = 'DIFFERENCE'
        self.angle = 0.0
        if not self._new_preview(context):
            return {'CANCELLED'}
        self._place(context, event)
        context.window_manager.modal_handler_add(self)
        context.window.cursor_modal_set('CROSSHAIR')
        context.workspace.status_text_set("KORO Stamp: move mouse | LMB stamp | Wheel rotate 15° | X/J/K operation | Enter/Esc finish")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            self._place(context, event)
            if context.area:
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.value == 'PRESS':
            self.angle += math.radians(15.0) * (1 if event.type == 'WHEELUPMOUSE' else -1)
            self._place(context, event)
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and event.type in {'X', 'J', 'K'}:
            self.operation = {'X':'DIFFERENCE', 'J':'UNION', 'K':'INTERSECT'}[event.type]
            if self.preview_bool:
                self.preview_bool.operation = self.operation
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if self.preview:
                self.preview["koro_operation"] = self.operation
                self.preview.display_type = 'WIRE'
                self.preview.show_in_front = True
                utils.mark_cutter_created(context.scene, self.preview)
            self.preview = None
            self.preview_bool = None
            if not self._new_preview(context):
                return {'FINISHED'}
            self._place(context, event)
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS' and event.type in {'RET', 'NUMPAD_ENTER', 'ESC', 'RIGHTMOUSE'}:
            self._remove_preview()
            try:
                context.window.cursor_modal_restore()
            except Exception:
                pass
            context.workspace.status_text_set(None)
            settings = context.scene.koro_hs
            if settings.auto_bevel:
                utils.ensure_bevel(self.target, settings.bevel_width, settings.bevel_segments)
            if settings.weighted_normals:
                utils.ensure_weighted_normal(self.target)
            utils.sort_target_modifiers(self.target)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


class KORO_OT_collection_boolean(Operator):
    bl_idname = "koro.collection_boolean"
    bl_label = "Collection Boolean"
    bl_description = "Use one native Boolean modifier with an entire cutter collection"
    bl_options = {'REGISTER', 'UNDO'}

    operation: EnumProperty(
        name="Operation",
        items=(('DIFFERENCE', "Difference", "Subtract collection"), ('UNION', "Union", "Union collection"), ('INTERSECT', "Intersect", "Intersect collection")),
        default='DIFFERENCE',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return context.mode == 'OBJECT' and obj is not None and obj.type == 'MESH'

    def execute(self, context):
        s = context.scene.koro_hs
        target = context.active_object
        col = s.collection_operand or bpy.data.collections.get(utils.CUTTER_COLLECTION)
        if col is None:
            self.report({'WARNING'}, "Choose a Boolean Collection or create KORO cutters first")
            return {'CANCELLED'}
        operation = self.operation or s.collection_operation
        solver = s.solver
        if operation == 'INTERSECT' and solver == 'FLOAT':
            solver = 'EXACT'
        utils.add_collection_boolean(target, col, operation, solver)
        if s.auto_bevel:
            utils.ensure_bevel(target, s.bevel_width, s.bevel_segments)
        if s.weighted_normals:
            utils.ensure_weighted_normal(target)
        utils.sort_target_modifiers(target)
        self.report({'INFO'}, f"Collection Boolean: {operation} <- {col.name}")
        return {'FINISHED'}


class KORO_OT_apply_cutter_preset(Operator):
    bl_idname = "koro.apply_cutter_preset"
    bl_label = "Apply Cutter Preset"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.koro_hs
        p = s.cutter_preset
        if p == 'PANEL':
            s.operation = 'DIFFERENCE'; s.inset_enabled = True; s.inset_amount = 0.025
            s.cutter_bevel = True; s.cutter_bevel_width = 0.006; s.cutter_bevel_segments = 3
            s.array_mode = 'OFF'; s.through_cut = False; s.live_solidify = True
        elif p == 'GROOVE':
            s.operation = 'DIFFERENCE'; s.inset_enabled = True; s.inset_amount = 0.012
            s.cutter_bevel = True; s.cutter_bevel_width = 0.003; s.cutter_bevel_segments = 2
            s.array_mode = 'OFF'; s.through_cut = False; s.live_solidify = True
        elif p == 'VENT':
            s.operation = 'DIFFERENCE'; s.inset_enabled = False; s.cutter_bevel = True
            s.cutter_bevel_width = 0.004; s.cutter_bevel_segments = 2; s.array_mode = 'LINEAR'
            s.array_count = max(5, s.array_count); s.array_gap = max(0.015, s.array_gap); s.through_cut = True
        elif p == 'BOLT':
            s.operation = 'DIFFERENCE'; s.inset_enabled = False; s.cutter_bevel = True
            s.cutter_bevel_width = 0.002; s.cutter_bevel_segments = 2; s.array_mode = 'OFF'; s.through_cut = True
            s.circle_segments = max(24, s.circle_segments)
        else:
            s.operation = 'DIFFERENCE'; s.inset_enabled = False; s.cutter_bevel = False
            s.array_mode = 'OFF'; s.taper_enabled = False; s.through_cut = False; s.live_solidify = True
        self.report({'INFO'}, f"Applied cutter preset: {p}")
        return {'FINISHED'}


class KORO_OT_quick_array(Operator):
    bl_idname = "koro.quick_array"
    bl_label = "Quick Array"
    bl_description = "Add or update a general-purpose KORO Array on selected meshes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        s = context.scene.koro_hs
        axis = {'X':0, 'Y':1, 'Z':2}[s.quick_array_axis]
        count = 0
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            name = f"KORO_QuickArray_{s.quick_array_axis}"
            mod = obj.modifiers.get(name)
            if mod is None or mod.type != 'ARRAY':
                mod = obj.modifiers.new(name=name, type='ARRAY')
            mod.fit_type = 'FIXED_COUNT'
            mod.count = s.quick_array_count
            mod.use_relative_offset = False
            mod.use_constant_offset = True
            span = max(float(obj.dimensions[axis]), 0.0001)
            vec = [0.0, 0.0, 0.0]
            vec[axis] = span + s.quick_array_gap
            mod.constant_offset_displace = vec
            count += 1
        self.report({'INFO'}, f"Quick Array configured on {count} object(s)")
        return {'FINISHED'}


class KORO_OT_dice(Operator):
    bl_idname = "koro.dice"
    bl_label = "Dice"
    bl_description = "Destructively add evenly spaced topology cuts along selected local axes"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return context.mode == 'OBJECT' and obj is not None and obj.type == 'MESH'

    def execute(self, context):
        s = context.scene.koro_hs
        obj = context.active_object
        axes = []
        if s.dice_x: axes.append((0, s.dice_count_x, Vector((1,0,0))))
        if s.dice_y: axes.append((1, s.dice_count_y, Vector((0,1,0))))
        if s.dice_z: axes.append((2, s.dice_count_z, Vector((0,0,1))))
        if not axes:
            self.report({'WARNING'}, "Enable at least one Dice axis")
            return {'CANCELLED'}

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        if not bm.verts:
            bm.free(); return {'CANCELLED'}
        coords = [v.co.copy() for v in bm.verts]
        mins = [min(co[i] for co in coords) for i in range(3)]
        maxs = [max(co[i] for co in coords) for i in range(3)]
        cuts = 0
        for axis_index, count, normal in axes:
            lo, hi = mins[axis_index], maxs[axis_index]
            if hi - lo < 1e-10:
                continue
            for i in range(1, int(count) + 1):
                t = i / (count + 1.0)
                pos = lo + (hi - lo) * t
                co = Vector((0.0, 0.0, 0.0)); co[axis_index] = pos
                geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
                bmesh.ops.bisect_plane(
                    bm, geom=geom, dist=s.dice_merge_distance,
                    plane_co=co, plane_no=normal,
                    clear_inner=False, clear_outer=False,
                )
                cuts += 1
        bm.normal_update()
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        self.report({'INFO'}, f"Dice added {cuts} local-axis cutting plane(s)")
        return {'FINISHED'}


class KORO_MT_hardops_q(Menu):
    bl_label = "KORO HardOps v0.9"
    bl_idname = "KORO_MT_hardops_q"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Cutters")
        col = layout.column(align=True)
        op = col.operator("koro.box_cutter", text="Box Cutter", icon='MESH_CUBE')
        op.shape = 'BOX'
        op = col.operator("koro.box_cutter", text="Circle Cutter", icon='MESH_CIRCLE')
        op.shape = 'CIRCLE'
        op = col.operator("koro.box_cutter", text="NGon Cutter", icon='MESH_DATA')
        op.shape = 'NGON'
        op = col.operator("koro.custom_cutter_selected", text="Custom Cutter from Selected", icon='DUPLICATE')
        op.operation = 'DIFFERENCE'
        col.operator("koro.repeat_last_cutter", text="Repeat Last Cutter", icon='DUPLICATE')
        col.operator("koro.stamp_cutter", text="Stamp Last Cutter", icon='BRUSH_DATA')
        col.operator("koro.edit_cutter", text="Edit Mesh Cutter", icon='EDITMODE_HLT')
        col.operator("koro.parametric_cutter_edit", text="Parametric Edit", icon='MODIFIER')

        layout.separator()
        layout.label(text="Boolean")
        op = layout.operator("koro.boolean_selected", text="Difference", icon='MOD_BOOLEAN')
        op.operation = 'DIFFERENCE'
        op = layout.operator("koro.boolean_selected", text="Union", icon='MOD_BOOLEAN')
        op.operation = 'UNION'
        op = layout.operator("koro.boolean_selected", text="Intersect", icon='MOD_BOOLEAN')
        op.operation = 'INTERSECT'
        op = layout.operator("koro.collection_boolean", text="Collection Difference", icon='OUTLINER_COLLECTION')
        op.operation = 'DIFFERENCE'

        layout.separator()
        layout.label(text="Modeling")
        layout.operator("koro.dice_modal", text="Dice Modal", icon='MOD_WIREFRAME')
        layout.operator("koro.array_modal", text="Array Modal", icon='MOD_ARRAY')
        layout.operator("koro.dice", text="Dice Apply", icon='MOD_WIREFRAME')
        layout.operator("koro.quick_array", text="Quick Array Apply", icon='MOD_ARRAY')
        layout.operator("koro.apply_cutter_preset", text="Apply Cutter Preset", icon='PRESET')

        layout.separator()
        layout.label(text="Finish")
        layout.operator("koro.sharpen", text="Sharpen", icon='SHARPCURVE')
        layout.operator("koro.smart_bevel", text="Smart Bevel", icon='MOD_BEVEL')
        layout.operator("koro.weighted_normals", text="Weighted Normals", icon='MOD_NORMALEDIT')

        layout.separator()
        layout.label(text="Stack")
        layout.operator("koro.modifier_scroll", text="Modifier Scroll", icon='MODIFIER')
        layout.operator("koro.sort_stack", text="Sort KORO Stack", icon='SORTSIZE')
        layout.operator("koro.toggle_booleans", text="Toggle Booleans", icon='RESTRICT_VIEW_OFF')
        layout.operator("koro.clean_stack", text="Clean Stack", icon='BRUSH_DATA')
        layout.operator("koro.apply_booleans", text="Apply Booleans", icon='CHECKMARK')
        layout.operator("koro.smart_apply", text="Smart Apply", icon='CHECKMARK')
        layout.operator("koro.toggle_cutters", text="Toggle Cutters", icon='HIDE_OFF')


class KORO_OT_sort_stack(Operator):
    bl_idname = "koro.sort_stack"
    bl_label = "Sort KORO Stack"
    bl_description = "Sort KORO Boolean/Bevel/Weighted Normal modifiers into a stable hard-surface order"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                utils.sort_target_modifiers(obj)
                count += 1
        self.report({'INFO'}, f"Sorted modifier stack on {count} object(s)")
        return {'FINISHED'}


class KORO_OT_toggle_booleans(Operator):
    bl_idname = "koro.toggle_booleans"
    bl_label = "Toggle Booleans"
    bl_description = "Toggle viewport visibility of Boolean modifiers on the active mesh"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        mods = [m for m in obj.modifiers if m.type == 'BOOLEAN']
        if not mods:
            self.report({'INFO'}, "No Boolean modifiers on active object")
            return {'FINISHED'}
        enable = not any(m.show_viewport for m in mods)
        for mod in mods:
            mod.show_viewport = enable
        self.report({'INFO'}, "Booleans enabled" if enable else "Booleans disabled")
        return {'FINISHED'}


class KORO_OT_modifier_scroll(Operator):
    bl_idname = "koro.modifier_scroll"
    bl_label = "Interactive Modifier Manager"
    bl_description = "Scroll, edit, toggle, reorder, apply, or remove modifiers on the active object"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    _handle = None
    index = 0
    param_index = 0

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return context.area and context.area.type == 'VIEW_3D' and obj is not None and len(obj.modifiers) > 0

    def _mods(self, context):
        obj = context.active_object
        return list(obj.modifiers) if obj else []

    def _clamp(self, context):
        mods = self._mods(context)
        self.index = max(0, min(self.index, len(mods) - 1)) if mods else 0
        if mods:
            params = self._params(mods[self.index])
            self.param_index = max(0, min(self.param_index, len(params) - 1)) if params else 0
        else:
            self.param_index = 0
        return mods

    def _params(self, mod):
        # label, attribute, vector component, base step, min, max
        if mod.type == 'BEVEL':
            return [
                ('Width', 'width', None, 0.001, 0.0, None),
                ('Segments', 'segments', None, 1.0, 1, 64),
                ('Profile', 'profile', None, 0.05, 0.0, 1.0),
            ]
        if mod.type == 'SOLIDIFY':
            return [
                ('Thickness', 'thickness', None, 0.005, None, None),
                ('Offset', 'offset', None, 0.1, -1.0, 1.0),
            ]
        if mod.type == 'ARRAY':
            specs = [('Count', 'count', None, 1.0, 1, 10000)]
            if getattr(mod, 'use_constant_offset', False):
                specs.append(('Offset X', 'constant_offset_displace', 0, 0.01, None, None))
            elif getattr(mod, 'use_relative_offset', False):
                specs.append(('Relative X', 'relative_offset_displace', 0, 0.1, None, None))
            return specs
        if mod.type == 'SIMPLE_DEFORM':
            if getattr(mod, 'deform_method', '') == 'BEND':
                return [('Angle', 'angle', None, 0.05, None, None)]
            return [('Factor', 'factor', None, 0.05, None, None)]
        if mod.type == 'SUBSURF':
            return [
                ('Viewport Levels', 'levels', None, 1.0, 0, 6),
                ('Render Levels', 'render_levels', None, 1.0, 0, 8),
            ]
        if mod.type == 'DECIMATE':
            return [('Ratio', 'ratio', None, 0.05, 0.0, 1.0)]
        if mod.type == 'WELD':
            return [('Distance', 'merge_threshold', None, 0.0005, 0.0, None)]
        if mod.type == 'MIRROR':
            return [('Merge Distance', 'merge_threshold', None, 0.0005, 0.0, None)]
        if mod.type == 'WEIGHTED_NORMAL' and hasattr(mod, 'weight'):
            return [('Weight', 'weight', None, 1.0, 1, 100)]
        return []

    def _param_value(self, mod, spec):
        _label, attr, component, _step, _minv, _maxv = spec
        value = getattr(mod, attr)
        return value[component] if component is not None else value

    def _set_param_value(self, mod, spec, value):
        _label, attr, component, _step, minv, maxv = spec
        current = getattr(mod, attr)
        is_int = isinstance(current, int) and not isinstance(current, bool) and component is None
        if minv is not None:
            value = max(minv, value)
        if maxv is not None:
            value = min(maxv, value)
        if is_int:
            value = int(round(value))
        if component is None:
            setattr(mod, attr, value)
        else:
            vec = current.copy()
            vec[component] = value
            setattr(mod, attr, vec)

    def _adjust_param(self, mod, direction, fine=False):
        params = self._params(mod)
        if not params:
            return False
        self.param_index %= len(params)
        spec = params[self.param_index]
        value = self._param_value(mod, spec)
        step = spec[3] * (0.1 if fine and spec[3] < 1.0 else 1.0)
        if isinstance(value, int) and not isinstance(value, bool):
            step = max(1.0, step)
        self._set_param_value(mod, spec, value + direction * step)
        return True

    def _format_param(self, mod):
        params = self._params(mod)
        if not params:
            return "Parameter: —"
        self.param_index %= len(params)
        spec = params[self.param_index]
        value = self._param_value(mod, spec)
        if isinstance(value, float):
            text = f"{value:.5g}"
        else:
            text = str(value)
        return f"Parameter {self.param_index + 1}/{len(params)}: {spec[0]} = {text}"

    def _draw(self, context):
        mods = self._mods(context)
        if not mods:
            return
        self._clamp(context)
        x = 28
        y = context.region.height - 42
        font = 0

        def line(text, size=14):
            nonlocal y
            blf.position(font, x, y, 0)
            try:
                blf.size(font, size)
            except TypeError:
                blf.size(font, size, 72)
            blf.draw(font, text)
            y -= 20

        line("KORO MODIFIER SCROLL v0.8", 18)
        mod = mods[self.index]
        line(f"{self.index + 1}/{len(mods)}  {mod.name}  [{mod.type}]", 14)
        line(f"Viewport {'ON' if mod.show_viewport else 'OFF'} | Render {'ON' if mod.show_render else 'OFF'} | Edit {'ON' if mod.show_in_editmode else 'OFF'}", 12)
        line(self._format_param(mod), 13)
        if mod.type == 'BOOLEAN':
            line(f"Boolean: {mod.operation} | Solver {getattr(mod, 'solver', 'N/A')}", 12)
        line("Wheel select | Shift+Wheel reorder | P parameter | Ctrl+Wheel adjust", 12)
        line("H viewport | R render | E edit-mode | C cage | F expand | D duplicate | A apply | X remove", 12)
        line("Boolean: O operation | S solver | Home sort KORO stack | Enter/Esc close", 12)

    def invoke(self, context, event):
        self.index = 0
        self.param_index = 0
        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            self._draw, (context,), 'WINDOW', 'POST_PIXEL'
        )
        context.window_manager.modal_handler_add(self)
        context.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _finish(self, context):
        if self._handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, 'WINDOW')
            self._handle = None
        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}

    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()
        mods = self._clamp(context)
        if not mods:
            return self._finish(context)

        if event.type in {'ESC', 'RIGHTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            return self._finish(context)

        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}

        obj = context.active_object
        mods = self._clamp(context)
        mod = mods[self.index]

        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            select_direction = -1 if event.type == 'WHEELUPMOUSE' else 1
            value_direction = 1 if event.type == 'WHEELUPMOUSE' else -1
            if event.ctrl:
                self._adjust_param(mod, value_direction, fine=event.shift)
            elif event.shift:
                old = obj.modifiers.find(mod.name)
                new = max(0, min(len(obj.modifiers) - 1, old + select_direction))
                if new != old:
                    obj.modifiers.move(old, new)
                    self.index = new
            else:
                self.index = (self.index + select_direction) % len(mods)
                self.param_index = 0
            return {'RUNNING_MODAL'}

        if event.type == 'P':
            params = self._params(mod)
            if params:
                self.param_index = (self.param_index + 1) % len(params)
            return {'RUNNING_MODAL'}
        if event.type == 'H':
            mod.show_viewport = not mod.show_viewport
            return {'RUNNING_MODAL'}
        if event.type == 'R':
            mod.show_render = not mod.show_render
            return {'RUNNING_MODAL'}
        if event.type == 'E':
            mod.show_in_editmode = not mod.show_in_editmode
            return {'RUNNING_MODAL'}
        if event.type == 'F':
            mod.show_expanded = not mod.show_expanded
            return {'RUNNING_MODAL'}
        if event.type == 'X':
            obj.modifiers.remove(mod)
            self._clamp(context)
            return {'RUNNING_MODAL'}
        if event.type == 'A':
            name = mod.name
            try:
                utils.apply_modifier(context, obj, mod)
                self.report({'INFO'}, f"Applied {name}")
            except Exception as exc:
                self.report({'WARNING'}, f"Could not apply {name}: {exc}")
            self._clamp(context)
            return {'RUNNING_MODAL'}
        if event.type == 'C' and hasattr(mod, 'show_on_cage'):
            mod.show_on_cage = not mod.show_on_cage
            return {'RUNNING_MODAL'}
        if event.type == 'D':
            try:
                bpy.ops.object.modifier_copy(modifier=mod.name)
                self._clamp(context)
            except Exception as exc:
                self.report({'WARNING'}, f"Could not duplicate {mod.name}: {exc}")
            return {'RUNNING_MODAL'}
        if event.type == 'O' and mod.type == 'BOOLEAN':
            order = ['DIFFERENCE', 'UNION', 'INTERSECT']
            current = mod.operation if mod.operation in order else 'DIFFERENCE'
            mod.operation = order[(order.index(current) + 1) % len(order)]
            return {'RUNNING_MODAL'}
        if event.type == 'S' and mod.type == 'BOOLEAN' and hasattr(mod, 'solver'):
            order = ['EXACT', 'MANIFOLD', 'FLOAT']
            current = mod.solver if mod.solver in order else 'EXACT'
            try:
                mod.solver = order[(order.index(current) + 1) % len(order)]
            except Exception:
                mod.solver = 'EXACT'
            return {'RUNNING_MODAL'}
        if event.type == 'HOME':
            utils.sort_target_modifiers(obj)
            self._clamp(context)
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

