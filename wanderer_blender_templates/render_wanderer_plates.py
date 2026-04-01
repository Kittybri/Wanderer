import json
import math
import os
import sys

import bpy


A_KEY = "\u3042"
I_KEY = "\u3044"
U_KEY = "\u3046"
E_KEY = "\u3048"
O_KEY = "\u304a"
N_KEY = "\u3093"
BLINK_KEY = "\u307e\u3070\u305f\u304d"
SERIOUS_KEY = "\u771f\u9762\u76ee"
TROUBLED_KEY = "\u56f0\u308b"
CALM_KEY = "\u306a\u3054\u307f"
ANGER_KEY = "\u6012\u308a"
SIDE_EYE_KEY = "\u3058\u3068\u76ee"
SMILE_KEY = "\u53e3\u89d2\u4e0a\u3052"


def read_arg(name: str, default: str = "") -> str:
    argv = sys.argv
    if "--" not in argv:
        return default
    args = argv[argv.index("--") + 1 :]
    if name in args:
        idx = args.index(name)
        if idx + 1 < len(args):
            return args[idx + 1]
    return default


def find_screen(scene):
    return next((obj for obj in scene.objects if obj.name.split(".")[0] == "SLIDE_SCREEN"), None)


def find_wanderer_mesh(scene):
    for obj in scene.objects:
        if obj.type == "MESH" and obj.data.shape_keys:
            keys = obj.data.shape_keys.key_blocks.keys()
            if A_KEY in keys and O_KEY in keys:
                return obj
    return None


def find_wanderer_root(scene):
    attach = next((obj for obj in scene.objects if obj.name.split(".")[0] == "WANDERER_ATTACH"), None)
    if attach is None:
        return None
    for obj in scene.objects:
        if obj.parent is not attach:
            continue
        stem = obj.name.split(".")[0]
        if stem.startswith("WANDERER_GUIDE") or stem.startswith("PARTNER_GUIDE"):
            continue
        if obj.type in {"EMPTY", "ARMATURE"}:
            return obj
    return next((obj for obj in scene.objects if obj.parent is attach), None)


def find_wanderer_armature(scene, root):
    if root is None:
        return None
    for obj in scene.objects:
        if obj.type != "ARMATURE":
            continue
        current = obj.parent
        while current is not None:
            if current is root:
                return obj
            current = current.parent
    return None


def bind_mesh_to_armature(mesh_obj, armature):
    if mesh_obj is None:
        return
    if armature is None and mesh_obj.parent is not None and mesh_obj.parent.type == "ARMATURE":
        armature = mesh_obj.parent
    if armature is None:
        return
    for modifier in mesh_obj.modifiers:
        if modifier.type == "ARMATURE":
            modifier.object = armature


def collect_descendants(root):
    descendants = []
    stack = list(root.children)
    seen = set()
    while stack:
        obj = stack.pop()
        if obj in seen:
            continue
        seen.add(obj)
        descendants.append(obj)
        stack.extend(list(obj.children))
    return descendants


def prune_scene_for_fast_render(scene, presenter_only=False):
    root = find_wanderer_root(scene)
    mesh = find_wanderer_mesh(scene)
    armature = find_wanderer_armature(scene, root)
    keep = {obj for obj in (root, mesh, armature) if obj is not None}

    if root is not None:
        for obj in collect_descendants(root):
            if obj not in keep:
                bpy.data.objects.remove(obj, do_unlink=True)

    for obj in list(scene.objects):
        stem = obj.name.split(".")[0]
        if stem in {"WANDERER_GUIDE_TORSO", "WANDERER_GUIDE_HEAD", "PARTNER_GUIDE_TORSO", "PARTNER_GUIDE_HEAD"}:
            obj.hide_render = True
            obj.hide_viewport = True
            continue
        if presenter_only and obj.type != "CAMERA" and obj not in keep:
            obj.hide_render = True
            obj.hide_viewport = True


def apply_screen_image(scene, image_path: str):
    screen = find_screen(scene)
    if screen is None or not image_path:
        return
    material = screen.active_material
    if material is None:
        return
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    image_node = nodes.get("SlideImage")
    if image_node is None:
        image_node = nodes.new("ShaderNodeTexImage")
        image_node.name = "SlideImage"
        image_node.location = (-420, 220)
    image_node.image = bpy.data.images.load(image_path, check_existing=True)
    for socket_name in ("Base Color", "Emission Color"):
        socket = principled.inputs[socket_name]
        for link in list(socket.links):
            links.remove(link)
        links.new(image_node.outputs["Color"], socket)
    principled.inputs["Emission Strength"].default_value = 1.2


def reset_face(mesh_obj):
    shape_keys = mesh_obj.data.shape_keys.key_blocks
    for name in [A_KEY, I_KEY, U_KEY, E_KEY, O_KEY, N_KEY, BLINK_KEY, SERIOUS_KEY, TROUBLED_KEY, CALM_KEY, ANGER_KEY, SIDE_EYE_KEY, SMILE_KEY]:
        if name in shape_keys:
            shape_keys[name].value = 0.0


def mood_expression(mesh_obj, mood: str):
    shape_keys = mesh_obj.data.shape_keys.key_blocks
    values = {
        "lecture": {SERIOUS_KEY: 0.30, SMILE_KEY: 0.05},
        "confession": {TROUBLED_KEY: 0.18, CALM_KEY: 0.20},
        "mission": {SERIOUS_KEY: 0.36, ANGER_KEY: 0.08},
        "debate": {SIDE_EYE_KEY: 0.16, SMILE_KEY: 0.08},
        "late_night": {CALM_KEY: 0.16},
    }.get(mood, {SERIOUS_KEY: 0.24})
    for name, value in values.items():
        if name in shape_keys:
            shape_keys[name].value = value


def stabilize_materials():
    for mat in bpy.data.materials:
        if not mat or not mat.use_nodes:
            continue
        blend_method = getattr(mat, "blend_method", "")
        if blend_method == "BLEND":
            mat.blend_method = "HASHED"
        shadow_method = getattr(mat, "shadow_method", "")
        if shadow_method == "NONE":
            mat.shadow_method = "HASHED"
        if mat.blend_method in {"HASHED", "CLIP"}:
            try:
                mat.use_backface_culling = True
            except Exception:
                pass


def reset_pose(armature):
    if armature is None:
        return
    for bone in armature.pose.bones:
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = (0.0, 0.0, 0.0)
        bone.location = (0.0, 0.0, 0.0)
        bone.scale = (1.0, 1.0, 1.0)


def apply_presenter_pose(armature):
    if armature is None:
        return
    reset_pose(armature)
    pose_map = {
        "肩.R": (0.0, 0.0, -26.0),
        "肩.L": (0.0, 0.0, 26.0),
        "腕.R": (0.0, 0.0, -66.0),
        "腕.L": (0.0, 0.0, 66.0),
        "ひじ.R": (0.0, 0.0, 14.0),
        "ひじ.L": (0.0, 0.0, -14.0),
        "手首.R": (0.0, 0.0, 2.0),
        "手首.L": (0.0, 0.0, -2.0),
    }
    for bone_name, degrees_xyz in pose_map.items():
        bone = armature.pose.bones.get(bone_name)
        if bone is None:
            continue
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = tuple(math.radians(value) for value in degrees_xyz)
    bpy.context.view_layer.update()


def apply_presenter_pose(armature):
    if armature is None:
        return
    reset_pose(armature)
    pose_map = {
        "\u80a9.R": (0.0, 0.0, -8.0),
        "\u80a9.L": (0.0, 0.0, -8.0),
        "\u8155.R": (0.0, 0.0, 96.0),
        "\u8155.L": (0.0, 0.0, 96.0),
        "\u3072\u3058.R": (0.0, 0.0, 12.0),
        "\u3072\u3058.L": (0.0, 0.0, 12.0),
        "\u624b\u9996.R": (0.0, 0.0, -2.0),
        "\u624b\u9996.L": (0.0, 0.0, -2.0),
    }
    for bone_name, degrees_xyz in pose_map.items():
        bone = armature.pose.bones.get(bone_name)
        if bone is None:
            continue
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = tuple(math.radians(value) for value in degrees_xyz)
    bpy.context.view_layer.update()


def set_viseme(mesh_obj, viseme: str, mood: str):
    reset_face(mesh_obj)
    mood_expression(mesh_obj, mood)
    shape_keys = mesh_obj.data.shape_keys.key_blocks
    if viseme == "blink":
        if BLINK_KEY in shape_keys:
            shape_keys[BLINK_KEY].value = 1.0
        return
    key_map = {
        "a": A_KEY,
        "i": I_KEY,
        "u": U_KEY,
        "e": E_KEY,
        "o": O_KEY,
        "n": N_KEY,
    }
    target_key = key_map.get(viseme, viseme)
    if viseme != "rest" and target_key in shape_keys:
        shape_keys[target_key].value = 0.72


def main():
    blend_path = read_arg("--blend")
    scene_name = read_arg("--scene", "01_Lecture_Explainer")
    spec_path = read_arg("--spec")
    output_dir = read_arg("--output-dir")
    mood = read_arg("--mood", "lecture")
    width = int(read_arg("--width", "1280"))
    height = int(read_arg("--height", "720"))
    engine = read_arg("--engine", "BLENDER_WORKBENCH")
    presenter_only = read_arg("--presenter-only", os.getenv("DUO_PRESENTER_ONLY", "")).strip().lower() in {"1", "true", "yes", "on"}

    if not blend_path or not os.path.exists(blend_path):
        raise SystemExit("Missing --blend <path>")
    if not spec_path or not os.path.exists(spec_path):
        raise SystemExit("Missing --spec <path>")
    if not output_dir:
        raise SystemExit("Missing --output-dir <path>")

    os.makedirs(output_dir, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=blend_path)
    scene = bpy.data.scenes.get(scene_name)
    if scene is None:
        raise SystemExit(f"Scene not found: {scene_name}")

    with open(spec_path, "r", encoding="utf-8") as handle:
        spec = json.load(handle)

    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    if presenter_only:
        scene.render.image_settings.color_mode = "RGBA"
        try:
            scene.render.film_transparent = True
        except Exception:
            pass
    try:
        scene.render.engine = engine
    except Exception:
        pass
    if scene.render.engine == "BLENDER_WORKBENCH":
        try:
            scene.display.shading.color_type = "TEXTURE"
            scene.display.shading.light = "STUDIO"
            scene.display.shading.show_object_outline = False
        except Exception:
            pass
    scene.frame_current = max(1, scene.frame_end // 2)
    prune_scene_for_fast_render(scene, presenter_only=presenter_only)

    root = find_wanderer_root(scene)
    mesh_obj = find_wanderer_mesh(scene)
    if mesh_obj is None:
        raise SystemExit("Could not find Wanderer mesh with viseme shape keys.")
    armature = find_wanderer_armature(scene, root)
    bind_mesh_to_armature(mesh_obj, armature)
    apply_presenter_pose(armature)
    stabilize_materials()

    visemes = ["rest", "a", "i", "u", "e", "o", "n", "blink"]
    output_manifest = {"plates": {}}

    for index, segment in enumerate(spec.get("segments", []), start=1):
        slide_path = segment.get("slide_path", "")
        apply_screen_image(scene, slide_path)
        output_manifest["plates"][str(index)] = {}
        for viseme in visemes:
            set_viseme(mesh_obj, viseme, mood)
            target = os.path.join(output_dir, f"segment_{index:02d}_{viseme}.png")
            scene.render.filepath = target
            bpy.ops.render.render(write_still=True, scene=scene.name)
            output_manifest["plates"][str(index)][viseme] = target

    with open(os.path.join(output_dir, "plates_manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(output_manifest, handle, indent=2)
    print(json.dumps(output_manifest, indent=2))


if __name__ == "__main__":
    main()
