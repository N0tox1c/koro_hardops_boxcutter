# KORO HardOps + BoxCutter Core v0.9.0

Independent hard-surface workflow extension for **Blender 5.2+** inspired by modern Boolean-modeling interaction patterns. It contains no Hard Ops / Boxcutter source code or proprietary assets.

## Install

1. Open Blender 5.2 or newer.
2. Go to **Edit > Preferences > Extensions**.
3. Choose **Install from Disk**.
4. Select `koro_hardops_boxcutter-0.9.0.zip`.
5. Enable **KORO HardOps BoxCutter** if needed.
6. Use **Q** in Object Mode or **N > KORO HS**.


## v0.9 highlights

### Draggable parameter handles

Live cutters now expose three viewport handles during the depth stage:

- **Depth** handle — drag cutter depth directly;
- **Inset** handle — drag ring/panel width;
- **Bevel** handle — drag cutter bevel width.

`Ctrl` snaps handle adjustments. Handle size and pick radius are configurable in **N > KORO HS > Cutter Lifecycle**.

### Parametric Cutter Edit

**Q > Parametric Edit** re-opens a confirmed KORO cutter without applying the Boolean. The editor supports:

- `D` Depth;
- `I` Inset;
- `B` cutter Bevel;
- `O` Offset;
- `T` Taper;
- `W` Real Wedge;
- `A` Array Count;
- `G` Array Gap;
- `Tab` next parameter;
- `X/Y` wedge axis;
- mouse / wheel adjustment;
- `Enter` confirm;
- `Esc/RMB` full rollback.

New v0.9 cutters persist their 2D profile and modeling metadata. Legacy v0.8 cutters are automatically migrated when possible by recovering the largest boundary loop from the base cutter mesh and reading existing live modifiers.

### Real Wedge geometry

`Alt+W` enters a real wedge phase. Unlike the existing Simple Deform Taper, the cutter mesh is rebuilt as an actual sloped prism. `X` / `Y` chooses the local slope axis and `Ctrl` quantizes the factor. Wedge and Taper remain separate tools.

### Array Modal

**Q > Array Modal** provides a live hard-surface Array workflow:

- mouse — physical gap;
- wheel — count;
- `X/Y/Z` — local axis;
- `Enter/LMB` — accept;
- `Esc/RMB` — restore the previous modifier state.

### Dice Modal

**Q > Dice Modal** configures destructive Dice before touching topology:

- `X/Y/Z` — select and enable axis;
- `Shift+X/Y/Z` — toggle axis;
- wheel — cutting-plane count on current axis;
- `Enter/LMB` — run the existing BMesh bisect Dice;
- `Esc/RMB` — cancel without modifying the mesh.

## v0.8 highlights

### Edit Live Cutter

**Q > Edit Live Cutter** finds the mesh driving the active Boolean, reveals it, makes it active and enters Edit Mode. Editing vertices/edges/faces updates the live Boolean result immediately.

If the active object is already a KORO cutter it edits that cutter directly; otherwise it falls back to the most recent KORO cutter.

### Repeat Last Cutter

**Q > Repeat Last Cutter** duplicates the most recently created cutter, including its mesh and modifier stack, then adds a new live Boolean to the active target.

KORO assigns cutter serials and remaps KORO helper objects used by radial arrays and mirror/origin workflows so repeated cutters do not intentionally share those helpers.

### Stamp Mode

**Q > Stamp Last Cutter** starts a multi-stamp modal tool:

- move mouse: align preview to the target surface;
- `LMB`: commit a stamp and immediately create the next preview;
- `Wheel`: rotate the stamp in 15-degree increments;
- `X`: Difference;
- `J`: Union;
- `K`: Intersect;
- `Enter / Esc / RMB`: end stamp mode and remove only the uncommitted preview.

Each committed stamp remains a separate editable KORO cutter.

### Native Collection Boolean

A single Boolean modifier can now use a complete Blender collection as its operand.

In **N > KORO HS > Collection Boolean** choose a collection and operation, then press **Add Collection Boolean**. When no collection is chosen, KORO can fall back to `_KORO_CUTTERS`.

This uses Blender's native `BooleanModifier.operand_type = COLLECTION` instead of creating one Boolean modifier per cutter.

### Cutter presets

Built-in workflow presets configure the modal cutter settings without replacing the normal manual controls:

- **Panel**: inset panel cut + small bevel;
- **Groove**: thinner inset ring/groove;
- **Vent Array**: repeated linear through-cutter;
- **Bolt / Hole**: circular-style through-hole settings;
- **Clean Boolean**: minimal non-destructive Boolean setup.

Choose a preset in the top of **N > KORO HS** and press **Apply**.

### HardOps-style Dice

**Dice Active Mesh** performs real destructive topology bisects in local object space.

Enable X/Y/Z independently and set the number of cutting planes for each axis. KORO calls BMesh plane bisects at evenly spaced positions inside the current local bounding box.

This adds topology cuts; it does not merely display guide planes.

### Quick Array

**Quick Array** adds/updates a general-purpose Array modifier on selected mesh objects:

- local X / Y / Z axis;
- configurable count;
- constant physical gap;
- spacing automatically includes the selected object's dimension along the chosen axis.

This is separate from the specialized BoxCutter live Array mode.

## Q menu v0.8

The Q menu now includes:

- Box / Circle / NGon cutter;
- Custom Cutter from Selected;
- Repeat Last Cutter;
- Stamp Last Cutter;
- Edit Live Cutter;
- selected-object Difference / Union / Intersect;
- Collection Difference;
- Dice;
- Quick Array;
- Apply Cutter Preset;
- Sharpen / Smart Bevel / Weighted Normals;
- Modifier Scroll / Sort / Toggle / Clean / Apply / Smart Apply.

## Main interactive cutter controls

| Input | Action |
|---|---|
| Q | KORO HardOps menu |
| LMB drag | Draw Box/Circle |
| LMB points | Add NGon points |
| Enter | Close NGon / confirm phase |
| Space before depth | Lazorcut and confirm |
| X | Difference, or X-axis while G/S/R is active |
| J | Union |
| K | Slice |
| Shift+K | Knife / Imprint |
| T | Extract |
| P | Make cutter as object |
| G | Live Move |
| S | Live Scale |
| R | Live Rotate |
| X/Y/Z during G/S/R | Local axis constraint |
| L | Pause / Release Lock |
| F | Cycle extrusion direction |
| Ctrl+D | Toggle Mini Helper |
| W | Live Taper |
| O | Live Offset |
| I | Live Inset |
| E | Through / Extend |
| A | Off / Linear / Radial Array |
| Shift+A | Radial Array directly |
| Shift+O | Move Radial pivot |
| Alt+O | Cycle Mirror Origin |
| M | Mirror Off / X / Y / XY |
| Z | Live Solidify when not in G/S/R axis selection |
| V | Surface / View / World orientation |
| C | Corner / Center Box drawing |
| Ctrl while drawing | Geometry snap dots |
| Shift+S | Grid Snap toggle |
| Shift+G | Geometry Snap toggle |
| D | Toggle profile dots |
| Alt+Wheel | Array count |
| [ / ] | Radial sweep |
| , / . | Linear Array spacing |
| Wheel | Bevel segments |
| Shift+Wheel | Bevel width |
| Ctrl+Wheel | Inset quick adjust |
| Esc / RMB | Cancel or roll back active transform |

## Retained from v0.1-v0.7

- Box / Circle / NGon drawing.
- Difference / Union / Slice.
- destructive Knife / Imprint.
- Extract / Make.
- Exact / Manifold / Float solver selection.
- Surface / View / World orientation.
- Corner / Center drawing.
- Through / Extend and Lazorcut.
- vertex / midpoint / edge snap dots.
- Grid and geometry snapping.
- Live Offset / Inset / Solidify / Taper.
- Cutter Bevel and target Auto Bevel.
- Linear and Radial Array with movable pivot.
- Mirror with Cutter / Target / Cursor origin.
- Live Move / Scale / Rotate with local-axis constraints.
- Pause / Release Lock and Mini Helper.
- Custom Cutter from Selected.
- Weighted Normals / Sharpen.
- Modifier Scroll parameter editing.
- cutter lifecycle and `_KORO_CUTTERS` collection management.

## Notes / limitations

- **Knife / Imprint** and **Dice** are destructive. Duplicate important production meshes before using them.
- Stamp aligns the cutter's local Z axis to the hit surface normal; highly asymmetric custom cutters may need an initial local-orientation cleanup before stamping.
- Collection Boolean is driven by every mesh in the selected collection; keep unrelated meshes out of the operand collection.
- Custom/Repeat cutters deep-copy mesh data. KORO helper references are remapped where recognized, but third-party modifier dependencies remain Blender data-block references and should be reviewed.
- The build environment performs Python/TOML/archive validation but does not contain an interactive Blender 5.2 executable. Viewport runtime behavior still needs a Blender smoke test.
