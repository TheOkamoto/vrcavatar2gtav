#!/usr/bin/env python3
"""
generate_franklin_atlas.py
==========================
Generate the unified 2048x2048 2x2 Texture Atlas and .ytd texture dictionary
for Franklin's Shinano Casual avatar (player_one), applying lilToon and
MoonButterfly shader color transforms:
  1. Top-Left quadrant     (0, 0): Face with warmed skin tone, blush, and eyes.
  2. Top-Right quadrant    (1, 0): Body skin with matching tone.
  3. Bottom-Left quadrant  (0, 1): Costume (sweater, red skirt, tights, boots).
  4. Bottom-Right quadrant (1, 1): Vibrant saturated indigo-blue hair.
"""

import argparse
import struct
import subprocess
import sys
import zlib
from pathlib import Path
import numpy as numpy_lib
from PIL import Image, ImageDraw, ImageFilter

# Dynamic cross-platform helper resolution compatible with both repo mirrors
_CURRENT_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT_CANDIDATE = _CURRENT_SCRIPT_DIR.parent.parent
for _tools_candidate in (
    _CURRENT_SCRIPT_DIR.parent / "common_tools",
    _REPO_ROOT_CANDIDATE / "scripts" / "common_tools",
    _REPO_ROOT_CANDIDATE / "_deploy_tools",
):
    if _tools_candidate.is_dir() and str(_tools_candidate) not in sys.path:
        sys.path.insert(0, str(_tools_candidate))

import ped_damage_helper
import texture_calibration_helper as calibration_helper
import unity_hair_helper
import vrc2gtav_i18n as project_i18n
import vrc2gtav_paths as project_paths
import vtoon_profile_helper


def read_binary_fbx_nodes(fbx_bytes: bytes) -> list:
    """Parse binary FBX nodes to extract mesh UVs without requiring Blender."""
    fbx_version = struct.unpack_from("<I", fbx_bytes, 23)[0]
    is_64bit = fbx_version >= 7500
    header_fmt = "<QQQB" if is_64bit else "<IIIB"
    header_size = 25 if is_64bit else 13

    def read_property(cursor_pos: int):
        prop_type = chr(fbx_bytes[cursor_pos])
        cursor_pos += 1
        if prop_type == "Y":
            return struct.unpack_from("<h", fbx_bytes, cursor_pos)[0], cursor_pos + 2
        if prop_type == "C":
            return bool(fbx_bytes[cursor_pos]), cursor_pos + 1
        if prop_type == "I":
            return struct.unpack_from("<i", fbx_bytes, cursor_pos)[0], cursor_pos + 4
        if prop_type == "F":
            return struct.unpack_from("<f", fbx_bytes, cursor_pos)[0], cursor_pos + 4
        if prop_type == "D":
            return struct.unpack_from("<d", fbx_bytes, cursor_pos)[0], cursor_pos + 8
        if prop_type == "L":
            return struct.unpack_from("<q", fbx_bytes, cursor_pos)[0], cursor_pos + 8
        if prop_type in ("S", "R"):
            str_len = struct.unpack_from("<I", fbx_bytes, cursor_pos)[0]
            cursor_pos += 4
            raw_slice = fbx_bytes[cursor_pos : cursor_pos + str_len]
            val_out = (
                raw_slice.decode("utf-8", errors="replace")
                if prop_type == "S"
                else raw_slice
            )
            return val_out, cursor_pos + str_len
        if prop_type in ("f", "d", "l", "i", "b"):
            arr_len, encoding_flag, comp_len = struct.unpack_from(
                "<III", fbx_bytes, cursor_pos
            )
            cursor_pos += 12
            raw_slice = fbx_bytes[cursor_pos : cursor_pos + comp_len]
            cursor_pos += comp_len
            if encoding_flag == 1:
                raw_slice = zlib.decompress(raw_slice)
            type_map = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "B"}
            return struct.unpack(f"<{arr_len}{type_map[prop_type]}", raw_slice), cursor_pos
        raise ValueError(f"Unsupported FBX property type: {prop_type}")

    def read_node(cursor_pos: int):
        end_offset, num_props, prop_len, name_len = struct.unpack_from(
            header_fmt, fbx_bytes, cursor_pos
        )
        if end_offset == 0:
            return None, cursor_pos + header_size
        cursor_pos += header_size
        node_name = fbx_bytes[cursor_pos : cursor_pos + name_len].decode(
            "utf-8", errors="replace"
        )
        cursor_pos += name_len
        props_list = []
        props_end = cursor_pos + prop_len
        for _ in range(num_props):
            prop_val, cursor_pos = read_property(cursor_pos)
            props_list.append(prop_val)
        cursor_pos = props_end
        children_list = []
        while cursor_pos < end_offset:
            child_node, cursor_pos = read_node(cursor_pos)
            if child_node is None:
                break
            children_list.append(child_node)
        return (node_name, props_list, children_list), end_offset

    scan_pos = 27
    nodes_out = []
    while scan_pos < len(fbx_bytes) - header_size:
        parsed_node, scan_pos = read_node(scan_pos)
        if parsed_node is None:
            break
        nodes_out.append(parsed_node)
    return nodes_out


def build_fbx_uv_island_masks(
    source_fbx_path: Path,
    target_mesh_names: list,
    cell_dimension: int,
    dilate_kernel: int = 9,
) -> dict:
    """Rasterize dilated UV polygon masks from source_fbx_path for per-mesh compositing."""
    if not source_fbx_path or not source_fbx_path.is_file():
        return {}
    fbx_bytes = source_fbx_path.read_bytes()
    if not fbx_bytes.startswith(b"Kaydara FBX Binary"):
        return {}
    nodes = read_binary_fbx_nodes(fbx_bytes)
    objects_node = next((item for item in nodes if item[0] == "Objects"), None)
    conns_node = next((item for item in nodes if item[0] == "Connections"), None)
    if objects_node is None or conns_node is None:
        return {}

    geom_by_id = {}
    model_by_id = {}
    for obj_item in objects_node[2]:
        if (
            obj_item[0] == "Geometry"
            and len(obj_item[1]) >= 3
            and obj_item[1][2] == "Mesh"
        ):
            geom_by_id[obj_item[1][0]] = obj_item
        elif obj_item[0] == "Model" and len(obj_item[1]) >= 2:
            model_by_id[obj_item[1][0]] = obj_item[1][1].split("\x00")[0]

    mesh_to_geom = {}
    for conn_item in conns_node[2]:
        props = conn_item[1]
        if len(props) >= 3 and props[2] in model_by_id and props[1] in geom_by_id:
            mesh_to_geom[model_by_id[props[2]]] = geom_by_id[props[1]]

    island_masks = {}
    for mesh_name in target_mesh_names:
        geom_node = mesh_to_geom.get(mesh_name)
        if geom_node is None:
            continue
        poly_indices_node = next(
            (sub for sub in geom_node[2] if sub[0] == "PolygonVertexIndex"), None
        )
        uv_layer_node = next(
            (sub for sub in geom_node[2] if sub[0] == "LayerElementUV"), None
        )
        if poly_indices_node is None or uv_layer_node is None:
            continue
        uv_coords_node = next(
            (sub for sub in uv_layer_node[2] if sub[0] == "UV"), None
        )
        if uv_coords_node is None:
            continue
        uv_indices_node = next(
            (sub for sub in uv_layer_node[2] if sub[0] == "UVIndex"), None
        )

        poly_vertex_indices = poly_indices_node[1][0]
        uv_flat = uv_coords_node[1][0]
        uv_index_map = uv_indices_node[1][0] if uv_indices_node is not None else None

        mask_img = Image.new("L", (cell_dimension, cell_dimension), 0)
        draw_ctx = ImageDraw.Draw(mask_img)
        polygon_pts = []
        loop_pos = 0
        max_px = float(cell_dimension - 1)
        for vert_idx in poly_vertex_indices:
            resolved_uv_idx = (
                uv_index_map[loop_pos]
                if uv_index_map is not None
                else (vert_idx if vert_idx >= 0 else ~vert_idx)
            )
            u_coord = uv_flat[resolved_uv_idx * 2]
            v_coord = uv_flat[resolved_uv_idx * 2 + 1]
            polygon_pts.append((u_coord * max_px, (1.0 - v_coord) * max_px))
            loop_pos += 1
            if vert_idx < 0:
                if len(polygon_pts) >= 3:
                    draw_ctx.polygon(polygon_pts, fill=255)
                polygon_pts = []

        if dilate_kernel >= 3:
            mask_img = mask_img.filter(ImageFilter.MaxFilter(dilate_kernel))
        island_masks[mesh_name] = numpy_lib.array(mask_img, dtype=numpy_lib.float32) / 255.0
    return island_masks


def build_hierarchy_costume_textures(
    shinano_textures_directory: Path,
    fallback_costume_path: Path,
    source_fbx_path: Path,
    cell_dimension: int,
):
    """
    Composite Franklin's Costume quadrant matching the Unity hierarchy lilToon
    materials:
      - Cloth_sweater: Shinano_costume _kikyo.mat (Shinano_costume_kikyo.png)
      - Cloth_dress & Cloth_skirt: Shinano_costume _winter.mat
      - Cloth_tights: Shinano_costume _autumn.mat + tights_color2 * 0.8396
      - Cloth_boots: Shinano_costume _summer.mat
      - Normal map: Map/Shinano_costume_normal.png scaled by _BumpScale (0.5)
    """
    color_costume_dir = shinano_textures_directory / "Color" / "Costume"
    mask_dir = shinano_textures_directory / "Mask"
    map_dir = shinano_textures_directory / "Map"

    kikyo_path = color_costume_dir / "Shinano_costume_kikyo.png"
    winter_path = color_costume_dir / "Shinano_costume_winter.png"
    autumn_path = color_costume_dir / "Shinano_costume_autumn.png"
    summer_path = color_costume_dir / "Shinano_costume_summer.png"
    tights_color2_path = color_costume_dir / "Shinano_costume_tights_color2.png"
    tights_mask_path = mask_dir / "Shinano_costume_tights_mask.png"

    costume_norm_array = None
    costume_norm_path = map_dir / "Shinano_costume_normal.png"
    if costume_norm_path.is_file():
        norm_img = (
            Image.open(costume_norm_path)
            .convert("RGBA")
            .resize((cell_dimension, cell_dimension), Image.Resampling.LANCZOS)
        )
        norm_float = numpy_lib.array(norm_img, dtype=numpy_lib.float32)
        # Apply Unity lilToon _BumpScale = 0.5 centered around tangent-flat (128, 128, 255)
        norm_float[:, :, 0] = 128.0 + (norm_float[:, :, 0] - 128.0) * 0.5
        norm_float[:, :, 1] = 128.0 + (norm_float[:, :, 1] - 128.0) * 0.5
        norm_float[:, :, 2] = 255.0 - (255.0 - norm_float[:, :, 2]) * 0.5
        norm_float[:, :, 3] = 255.0
        costume_norm_array = numpy_lib.clip(norm_float, 0.0, 255.0).astype(numpy_lib.uint8)

    base_source_path = (
        kikyo_path if kikyo_path.is_file() else fallback_costume_path
    )
    if base_source_path is None or not Path(base_source_path).is_file():
        return None, costume_norm_array

    def load_resized_rgba(img_path: Path) -> numpy_lib.ndarray:
        opened_img = (
            Image.open(img_path)
            .convert("RGBA")
            .resize((cell_dimension, cell_dimension), Image.Resampling.LANCZOS)
        )
        return numpy_lib.array(opened_img, dtype=numpy_lib.float32)

    composite_array = load_resized_rgba(Path(base_source_path))
    costume_mesh_names = [
        "Cloth_sweater",
        "Cloth_dress",
        "Cloth_skirt",
        "Cloth_tights",
        "Cloth_boots",
    ]
    island_masks = build_fbx_uv_island_masks(
        source_fbx_path, costume_mesh_names, cell_dimension, dilate_kernel=9
    )

    if island_masks:
        if winter_path.is_file():
            winter_array = load_resized_rgba(winter_path)
            for piece_name in ("Cloth_dress", "Cloth_skirt"):
                piece_mask = island_masks.get(piece_name)
                if piece_mask is not None:
                    alpha_weight = piece_mask[:, :, None]
                    composite_array = (
                        composite_array * (1.0 - alpha_weight)
                        + winter_array * alpha_weight
                    )

        if autumn_path.is_file() and "Cloth_tights" in island_masks:
            autumn_array = load_resized_rgba(autumn_path)
            if tights_color2_path.is_file() and tights_mask_path.is_file():
                tights_color2 = load_resized_rgba(tights_color2_path)
                # Shinano_costume _autumn.mat: _Color2nd = (0.83962, 0.83962, 0.83962)
                tights_color2[:, :, :3] *= 0.83962
                tights_mask_img = (
                    Image.open(tights_mask_path)
                    .convert("L")
                    .resize((cell_dimension, cell_dimension), Image.Resampling.LANCZOS)
                )
                tights_mask = (
                    numpy_lib.array(tights_mask_img, dtype=numpy_lib.float32) / 255.0
                )[:, :, None] * 0.65
                autumn_array[:, :, :3] = (
                    autumn_array[:, :, :3] * (1.0 - tights_mask)
                    + tights_color2[:, :, :3] * tights_mask
                )
            tights_island = island_masks["Cloth_tights"][:, :, None]
            composite_array = (
                composite_array * (1.0 - tights_island)
                + autumn_array * tights_island
            )

        if summer_path.is_file() and "Cloth_boots" in island_masks:
            summer_array = load_resized_rgba(summer_path)
            boots_island = island_masks["Cloth_boots"][:, :, None]
            composite_array = (
                composite_array * (1.0 - boots_island)
                + summer_array * boots_island
            )

    composite_uint8 = numpy_lib.clip(composite_array, 0.0, 255.0).astype(
        numpy_lib.uint8
    )
    return composite_uint8, costume_norm_array


def build_franklin_atlas(
    target_character: str = None,
    hair_override: str = None,
    hair_mat_override: str = None,
    hair_tex_override: str = None,
    unity_scene_override: str = None,
    unity_avatar_override: str = None,
    output_dir_override: str = None,
) -> bool:
    """Build the 2048x2048 2x2 texture atlas and compile Franklin's .ytd archive."""
    try:
        franklin_cfg = (
            project_paths.get_character_paths(
                target_character,
                avatar_override="shinano_casual",
            )
            if target_character
            else project_paths.get_avatar_paths("shinano_casual")
        )

        output_directory = (
            Path(output_dir_override)
            if output_dir_override
            else Path(franklin_cfg["ytd_dir"])
        )
        textures_subfolder = (
            Path(output_dir_override)
            if output_dir_override
            else Path(franklin_cfg["textures_dir"])
        )
        output_directory.mkdir(parents=True, exist_ok=True)
        textures_subfolder.mkdir(parents=True, exist_ok=True)

        shinano_textures_directory = Path(franklin_cfg["tex_shinano_dir"])
        source_textures_directory = Path(franklin_cfg["staging_textures_src_dir"])

        if not shinano_textures_directory.exists():
            print(
                project_i18n.translate(
                    "franklin.tex_dir_missing", path=shinano_textures_directory
                )
            )
            return False

        cell_dimension = 1024
        canvas_dimension = 2 * cell_dimension

        print(
            project_i18n.translate(
                "franklin.generating_atlas",
                path=textures_subfolder,
                size=canvas_dimension,
            )
        )

        diffuse_pixel_array = numpy_lib.full(
            (canvas_dimension, canvas_dimension, 4),
            [128, 128, 128, 255],
            dtype=numpy_lib.uint8,
        )
        specular_pixel_array = numpy_lib.full(
            (canvas_dimension, canvas_dimension, 4),
            [18, 16, 18, 40],
            dtype=numpy_lib.uint8,
        )
        normal_pixel_array = numpy_lib.full(
            (canvas_dimension, canvas_dimension, 4),
            [128, 128, 255, 255],
            dtype=numpy_lib.uint8,
        )

        # 1. Face (Shinano_face) -> Top-Left quadrant
        face_raw_path = calibration_helper.resolve_existing_file(
            franklin_cfg.get("tex_face"),
            [shinano_textures_directory / "Shinano_face.png"],
        )
        if face_raw_path is None:
            raise FileNotFoundError(
                f"Shinano face texture not found: {franklin_cfg.get('tex_face')}"
            )

        composite_face_image, missing_face_layers = (
            calibration_helper.composite_shinano_face_with_fallback(
                face_path=face_raw_path,
                target_size=2048,
                makeup_path=franklin_cfg.get("tex_makeup"),
                eye_sky_path=franklin_cfg.get("tex_eye_sky"),
                eye_cloud_path=franklin_cfg.get("tex_eye_cloud"),
                eye_cloud_mask_path=franklin_cfg.get("tex_eye_cloud_mask"),
                eye_highlight_path=franklin_cfg.get("tex_eye_highlight"),
            )
        )
        if missing_face_layers:
            print(
                project_i18n.translate(
                    "franklin.atlas.eye_fallback",
                    layers=", ".join(missing_face_layers),
                )
            )

        final_face_quadrant = composite_face_image.resize(
            (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
        )
        diffuse_pixel_array[0:cell_dimension, 0:cell_dimension] = numpy_lib.array(
            final_face_quadrant
        )

        face_spec_mask = calibration_helper.build_shinano_face_specular(
            cell_dimension,
            shinano_textures_directory,
            franklin_cfg.get("tex_face_emission", ""),
        )
        if face_spec_mask is not None:
            specular_pixel_array[0:cell_dimension, 0:cell_dimension][face_spec_mask] = [
                95,
                110,
                130,
                200,
            ]

        # 2. Body (Shinano_body) -> Top-Right quadrant
        body_raw_path = calibration_helper.resolve_existing_file(
            franklin_cfg.get("tex_body"),
            [shinano_textures_directory / "Shinano_body.png"],
        )
        if body_raw_path is not None:
            raw_body_image = (
                Image.open(body_raw_path)
                .convert("RGBA")
                .resize(
                    (cell_dimension, cell_dimension), Image.Resampling.LANCZOS
                )
            )
            warm_body_image = calibration_helper.apply_shinano_skin_warmth(
                raw_body_image
            )
            diffuse_pixel_array[
                0:cell_dimension, cell_dimension : 2 * cell_dimension
            ] = numpy_lib.array(warm_body_image)

        # 3. Costume -> Bottom-Left quadrant (Unity hierarchy lilToon variants or fallback)
        costume_source_candidates = [
            source_textures_directory / "shinano_costume.png",
            textures_subfolder / "shinano_costume.png",
            franklin_cfg.get("tex_costume"),
            shinano_textures_directory / "Shinano_costume.png",
        ]
        found_costume_path = calibration_helper.resolve_existing_file(
            None, costume_source_candidates
        )
        source_fbx_raw = franklin_cfg.get("source_fbx")
        source_fbx_path = Path(source_fbx_raw) if source_fbx_raw else None
        composited_costume, costume_normal_quad = build_hierarchy_costume_textures(
            shinano_textures_directory=shinano_textures_directory,
            fallback_costume_path=found_costume_path,
            source_fbx_path=source_fbx_path,
            cell_dimension=cell_dimension,
        )
        if composited_costume is not None:
            diffuse_pixel_array[
                cell_dimension : 2 * cell_dimension, 0:cell_dimension
            ] = composited_costume
        if costume_normal_quad is not None:
            normal_pixel_array[
                cell_dimension : 2 * cell_dimension, 0:cell_dimension
            ] = costume_normal_quad

        # 4. Hair (custom Unity hair or Shinano_hair default) -> Bottom-Right quadrant
        hair_spec_input = (
            hair_override
            if hair_override is not None
            else (
                str(franklin_cfg.get("custom_hair", "")).strip()
                or str(franklin_cfg.get("fbx_hair", "")).strip()
                or "default"
            )
        )
        hair_spec = unity_hair_helper.resolve_custom_hair_spec(
            hair_spec_input=hair_spec_input,
            unity_scene=unity_scene_override or franklin_cfg.get("unity_scene"),
            unity_avatar_name=unity_avatar_override
            or str(franklin_cfg.get("unity_avatar_name", "Shinano")),
            hair_mat_override=hair_mat_override or franklin_cfg.get("hair_mat"),
            hair_tex_override=hair_tex_override or franklin_cfg.get("hair_tex"),
            is_calibrated_er_default=False,
        )

        if hair_spec.get("mode") == "custom":
            print(
                project_i18n.translate(
                    "common.hair_custom_packed",
                    source=hair_spec.get("source_input", ""),
                    tiles=len(hair_spec.get("materials", [])),
                )
            )
            quad_diff, quad_norm, quad_spec, tile_entries = (
                unity_hair_helper.pack_hair_materials_into_quadrant(
                    hair_spec.get("materials", []),
                    quad_size=(cell_dimension, cell_dimension),
                    quad_uv_rect=(0.5, 0.0, 0.5, 0.5),
                    gutter_px=4,
                )
            )
            diffuse_pixel_array[
                cell_dimension : 2 * cell_dimension,
                cell_dimension : 2 * cell_dimension,
            ] = numpy_lib.array(quad_diff.convert("RGBA"))
            specular_pixel_array[
                cell_dimension : 2 * cell_dimension,
                cell_dimension : 2 * cell_dimension,
            ] = numpy_lib.array(quad_spec.convert("RGBA"))
            normal_pixel_array[
                cell_dimension : 2 * cell_dimension,
                cell_dimension : 2 * cell_dimension,
            ] = numpy_lib.array(quad_norm.convert("RGBA"))
            unity_hair_helper.save_custom_hair_manifest(
                textures_subfolder, hair_spec, tile_entries
            )
        else:
            configured_hair_path = str(franklin_cfg.get("tex_hair", "")).strip()
            hair_source_candidates = [
                source_textures_directory / "shinano_hair.png",
                textures_subfolder / "shinano_hair.png",
                configured_hair_path,
                shinano_textures_directory / "Shinano_hair.png",
            ]
            found_hair_path = calibration_helper.resolve_existing_file(
                None, hair_source_candidates
            )
            base_shinano_hair = shinano_textures_directory / "Shinano_hair.png"
            if configured_hair_path and not Path(configured_hair_path).is_file():
                print(project_i18n.translate("franklin.atlas.hair_fallback"))

            if found_hair_path is not None:
                hair_diffuse_quad, hair_spec_quad, hair_norm_quad = (
                    calibration_helper.calibrate_shinano_default_hair(
                        base_hair_path=base_shinano_hair
                        if base_shinano_hair.is_file()
                        else found_hair_path,
                        shinano_tex_root=shinano_textures_directory,
                        output_size=cell_dimension,
                        target_tint_path=found_hair_path,
                    )
                )
                diffuse_pixel_array[
                    cell_dimension : 2 * cell_dimension,
                    cell_dimension : 2 * cell_dimension,
                ] = numpy_lib.array(hair_diffuse_quad)
                specular_pixel_array[
                    cell_dimension : 2 * cell_dimension,
                    cell_dimension : 2 * cell_dimension,
                ] = numpy_lib.array(hair_spec_quad)
                normal_pixel_array[
                    cell_dimension : 2 * cell_dimension,
                    cell_dimension : 2 * cell_dimension,
                ] = numpy_lib.array(hair_norm_quad)
            unity_hair_helper.save_custom_hair_manifest(
                textures_subfolder, hair_spec, []
            )

        # Save final PNG channels configured via vrc2gtav.cfg
        diffuse_final_path = (
            textures_subfolder / Path(franklin_cfg["atlas_png"]).name
            if output_dir_override
            else Path(franklin_cfg["atlas_png"])
        )
        specular_final_path = (
            textures_subfolder / Path(franklin_cfg["spec_png"]).name
            if output_dir_override
            else Path(franklin_cfg["spec_png"])
        )
        normal_final_path = (
            textures_subfolder / Path(franklin_cfg["normal_png"]).name
            if output_dir_override
            else Path(franklin_cfg["normal_png"])
        )

        final_diffuse_img = vtoon_profile_helper.stamp_vtoon_watermark_block(
            Image.fromarray(diffuse_pixel_array, "RGBA"), char_id=2
        )
        final_diffuse_img.save(diffuse_final_path, format="PNG")
        Image.fromarray(specular_pixel_array, "RGBA").save(
            specular_final_path, format="PNG"
        )
        Image.fromarray(normal_pixel_array, "RGBA").save(
            normal_final_path, format="PNG"
        )

        print(project_i18n.translate("franklin.atlas_saved", path=diffuse_final_path))

        # Compile the .ytd texture dictionary
        rage_cli_binary = project_paths.get_rage_cli()
        output_ytd_file = (
            output_directory / Path(franklin_cfg["ytd_file"]).name
            if output_dir_override
            else Path(franklin_cfg["ytd_file"])
        )

        texture_build_command = [
            rage_cli_binary,
            "textures",
            "build",
            "-o",
            str(output_ytd_file),
            str(diffuse_final_path),
            str(specular_final_path),
            str(normal_final_path),
        ]
        print(project_i18n.translate("franklin.compiling_ytd"))
        subprocess.run(
            texture_build_command,
            capture_output=True,
            text=True,
            check=True,
        )
        ped_damage_helper.enforce_ytd_rpf7_size_budget(
            rage_cli_binary,
            output_ytd_file,
            [diffuse_final_path, specular_final_path, normal_final_path],
        )
        print(project_i18n.translate("franklin.ytd_generated", path=output_ytd_file))
        _generate_franklin_vtoon_profile(
            franklin_cfg=franklin_cfg,
            shinano_textures_directory=shinano_textures_directory,
            face_spec_mask=face_spec_mask,
            output_directory=output_directory,
            custom_output_mode=bool(output_dir_override),
        )
        return True

    except Exception as runtime_error:
        print(
            project_i18n.translate("franklin.atlas_failed", error=runtime_error)
        )
        return False


def _generate_franklin_vtoon_profile(
    *,
    franklin_cfg: dict,
    shinano_textures_directory: Path,
    face_spec_mask: object,
    output_directory: Path,
    custom_output_mode: bool,
) -> None:
    """Create UV LUT, MatCap, and synced INI entry for char_id=2 (Shinano Casual)."""
    assets_root = shinano_textures_directory.parent.parent
    mat_dir = shinano_textures_directory.parent / "Material"
    face_mat = mat_dir / "Shinano_face.mat"
    body_mat = mat_dir / "Shinano_body.mat"
    hair_mat = mat_dir / "Shinano_hair.mat"

    slot_materials = {
        vtoon_profile_helper.SLOT_CLOTH: vtoon_profile_helper.build_vtoon_slot_from_mat(
            None, vtoon_profile_helper.SLOT_CLOTH, albedo_color_already_baked=True
        ),
        vtoon_profile_helper.SLOT_SKIN: vtoon_profile_helper.build_vtoon_slot_from_mat(
            vtoon_profile_helper.parse_liltoon_mat_file(body_mat, assets_root=assets_root),
            vtoon_profile_helper.SLOT_SKIN,
            albedo_color_already_baked=True,
        ),
        vtoon_profile_helper.SLOT_FACE: vtoon_profile_helper.build_vtoon_slot_from_mat(
            vtoon_profile_helper.parse_liltoon_mat_file(face_mat, assets_root=assets_root),
            vtoon_profile_helper.SLOT_FACE,
            albedo_color_already_baked=True,
        ),
        vtoon_profile_helper.SLOT_EYES: vtoon_profile_helper.build_vtoon_slot_from_mat(
            vtoon_profile_helper.parse_liltoon_mat_file(face_mat, assets_root=assets_root),
            vtoon_profile_helper.SLOT_EYES,
            albedo_color_already_baked=True,
        ),
        vtoon_profile_helper.SLOT_HAIR: vtoon_profile_helper.build_vtoon_slot_from_mat(
            vtoon_profile_helper.parse_liltoon_mat_file(hair_mat, assets_root=assets_root),
            vtoon_profile_helper.SLOT_HAIR,
            albedo_color_already_baked=True,
        ),
    }
    lut_regions = [
        {"u0": 0.00, "v0": 0.00, "u1": 0.50, "v1": 0.50, "slot_id": vtoon_profile_helper.SLOT_FACE, "shadow_mask": 0.88, "rim_mask": 0.15},
        {"u0": 0.50, "v0": 0.00, "u1": 1.00, "v1": 0.50, "slot_id": vtoon_profile_helper.SLOT_SKIN, "shadow_mask": 0.90, "rim_mask": 0.28},
        {"u0": 0.00, "v0": 0.50, "u1": 0.50, "v1": 1.00, "slot_id": vtoon_profile_helper.SLOT_CLOTH, "shadow_mask": 0.95, "rim_mask": 0.45},
        {"u0": 0.50, "v0": 0.50, "u1": 1.00, "v1": 1.00, "slot_id": vtoon_profile_helper.SLOT_HAIR, "shadow_mask": 0.92, "rim_mask": 0.88},
    ]

    repo_root = project_paths.get_project_root()
    pkg_dir = (
        Path(franklin_cfg["character_dir"]) / "5_rpf_package"
        if not custom_output_mode
        else output_directory
    )
    sync_dirs = []
    if not custom_output_mode:
        for cand_dir in (
            project_paths.get_gtav_root_dir(),
            repo_root / "2_Michael_Shinano_EternalReunion" / "5_rpf_package",
            repo_root / "3_Trevor_Miltina_Maid" / "5_rpf_package",
        ):
            if cand_dir and Path(cand_dir).is_dir():
                sync_dirs.append(Path(cand_dir))

    lut_path, _matcap = vtoon_profile_helper.generate_character_vtoon_assets(
        char_id=2,
        char_name="Shinano_Casual",
        slug="shinano_franklin",
        package_dir=pkg_dir,
        lut_regions=lut_regions,
        slot_materials=slot_materials,
        mat_paths_for_matcap=[hair_mat],
        assets_root=assets_root if assets_root.is_dir() else None,
        sync_dirs=sync_dirs,
    )

    if face_spec_mask is not None and lut_path.is_file():
        lut_img = Image.open(lut_path).convert("RGBA")
        lut_width, lut_height = lut_img.size
        face_width = lut_width // 2
        face_height = lut_height // 2
        mask_arr = (
            numpy_lib.array(
                Image.fromarray((face_spec_mask.astype(numpy_lib.uint8) * 255)).resize(
                    (face_width, face_height), Image.Resampling.NEAREST
                )
            )
            > 127
        )
        lut_arr = numpy_lib.array(lut_img)
        eye_region = lut_arr[0:face_height, 0:face_width]
        eye_region[mask_arr] = [
            int(round((vtoon_profile_helper.SLOT_EYES / 15.0) * 255.0)),
            85,
            185,
            78,
        ]
        lut_arr[0:face_height, 0:face_width] = eye_region
        updated_lut = Image.fromarray(lut_arr, mode="RGBA")
        updated_lut.save(lut_path)
        for extra_dir in sync_dirs:
            dst_lut = extra_dir / "vtoon_profiles" / lut_path.name
            if dst_lut.parent.is_dir():
                import shutil
                shutil.copy2(lut_path, dst_lut)


def main() -> int:
    """CLI entrypoint for Franklin texture atlas generation."""
    project_i18n.set_active_language()
    arg_parser = argparse.ArgumentParser(
        description=project_i18n.translate("franklin.atlas_cli_description")
    )
    arg_parser.add_argument(
        "--lang",
        choices=["auto", "en", "ja", "pt"],
        default="auto",
        help=project_i18n.translate("common.language_option_help"),
    )
    arg_parser.add_argument(
        "--target-character",
        choices=["michael", "franklin", "trevor"],
        default=None,
        help=project_i18n.translate("franklin.build.arg_target_char"),
    )
    arg_parser.add_argument("--output-dir", default=None)
    arg_parser.add_argument("--hair", default=None)
    arg_parser.add_argument("--hair-mat", default=None)
    arg_parser.add_argument("--hair-tex", default=None)
    arg_parser.add_argument("--unity-scene", default=None)
    arg_parser.add_argument("--unity-avatar-name", default=None)
    parsed_args = arg_parser.parse_args()
    project_i18n.set_active_language(parsed_args.lang)
    return (
        0
        if build_franklin_atlas(
            target_character=parsed_args.target_character,
            hair_override=parsed_args.hair,
            hair_mat_override=parsed_args.hair_mat,
            hair_tex_override=parsed_args.hair_tex,
            unity_scene_override=parsed_args.unity_scene,
            unity_avatar_override=parsed_args.unity_avatar_name,
            output_dir_override=parsed_args.output_dir,
        )
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
