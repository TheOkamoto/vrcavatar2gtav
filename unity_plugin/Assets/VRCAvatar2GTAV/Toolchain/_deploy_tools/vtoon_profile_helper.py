"""
vtoon_profile_helper.py
=======================
Generate VToon character shader profiles, UV-region material LUTs, MatCaps,
8x4 mip0 texture watermark stamps, and multi-character `GTAVVToon.ini` files
from Unity `lilToon` material (.mat) properties.
"""

from pathlib import Path
import re
import shutil

import numpy as numpy_mod
from PIL import Image

import modular_avatar_yaml_layer as ma_yaml_layer


MAX_VTOON_SLOTS = 16

SLOT_CLOTH = 0
SLOT_SKIN = 1
SLOT_FACE = 2
SLOT_EYES = 3
SLOT_HAIR = 4
SLOT_HAIR_ALPHA = 5
SLOT_NAILS = 6
SLOT_METAL = 7


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _srgb_to_linear_channel(val: float) -> float:
    clamped = _clamp_unit(val)
    return pow(clamped, 2.2)


def stamp_vtoon_watermark_block(rgba_image: Image.Image, char_id: int) -> Image.Image:
    """Stamp an 8x4 DXT-safe bottom-right signature identifying char_id (1..15)."""
    if char_id < 1 or char_id > 15:
        raise ValueError(f"VToon char_id must be in 1..15, got {char_id}")
    out_img = rgba_image.convert("RGBA") if rgba_image.mode != "RGBA" else rgba_image.copy()
    width, height = out_img.size
    if width < 16 or height < 16:
        raise ValueError(f"Texture too small for VToon watermark: {width}x{height}")

    arr = numpy_mod.array(out_img, dtype=numpy_mod.uint8)
    # Two adjacent 4x4 BC-aligned solid blocks so DXT1/DXT5 encodes exact signature
    arr[height - 4 : height, width - 8 : width - 4] = [255, 0, 255, 255]
    arr[height - 4 : height, width - 4 : width] = [min(255, char_id * 16), 255, 16, 255]
    return Image.fromarray(arr, mode="RGBA")


def decode_vtoon_watermark_block(rgba_image: Image.Image) -> int:
    """Read back the 8x4 bottom-right VToon signature; returns 0 if absent."""
    img = rgba_image.convert("RGBA") if rgba_image.mode != "RGBA" else rgba_image
    width, height = img.size
    if width < 16 or height < 16:
        return 0
    arr = numpy_mod.array(img, dtype=numpy_mod.uint8)
    blk0 = arr[height - 2, width - 6]
    blk1 = arr[height - 2, width - 2]
    if blk0[0] >= 210 and blk0[1] <= 45 and blk0[2] >= 210 and blk1[1] >= 210 and blk1[2] <= 48:
        decoded = int((int(blk1[0]) + 8) // 16)
        if 1 <= decoded <= 15:
            return decoded
    return 0


def _infer_assets_root_from_mat(mat_path: Path) -> Path | None:
    """Locate the enclosing Unity Assets directory for a material path when present."""
    for ancestor in mat_path.parents:
        if ancestor.name.lower() == "assets" and ancestor.is_dir():
            return ancestor
    return None


def parse_liltoon_mat_file(
    mat_path: Path | str | None,
    assets_root: Path | str | None = None,
    _visited_paths: set[str] | None = None,
) -> dict:
    """Extract lilToon float/color/texture-guid fields, resolving m_Parent inheritance."""
    result = {"floats": {}, "colors": {}, "tex_guids": {}, "shader_guid": ""}
    if not mat_path:
        return result
    path_obj = Path(mat_path)
    if not path_obj.is_file():
        return result

    resolved_key = str(path_obj.resolve()).lower()
    seen_set = set() if _visited_paths is None else set(_visited_paths)
    if resolved_key in seen_set:
        return result
    seen_set.add(resolved_key)

    text = path_obj.read_text(encoding="utf-8", errors="ignore")
    parent_match = re.search(r"m_Parent:\s*\{[^}]*guid:\s*([0-9a-fA-F]{32})", text)
    if parent_match:
        import unity_hair_bake_layer as hair_bake_layer

        root_dir = Path(assets_root) if assets_root else _infer_assets_root_from_mat(path_obj)
        parent_path = hair_bake_layer.resolve_unity_guid(
            parent_match.group(1).lower(),
            path_obj,
            unity_assets_root=root_dir,
        )
        if parent_path and Path(parent_path).is_file():
            result = parse_liltoon_mat_file(parent_path, assets_root=root_dir, _visited_paths=seen_set)

    shader_match = re.search(r"m_Shader:\s*\{[^}]*guid:\s*([0-9a-fA-F]{32})", text)
    if shader_match:
        result["shader_guid"] = shader_match.group(1).lower()

    for float_match in re.finditer(r"^\s*-\s*(_[A-Za-z0-9_]+):\s*([-+]?\d+(?:\.\d+)?)\s*$", text, re.M):
        result["floats"][float_match.group(1)] = float(float_match.group(2))

    color_pat = re.compile(
        r"^\s*-\s*(_[A-Za-z0-9_]+):\s*\{r:\s*([-+]?\d+(?:\.\d+)?),\s*g:\s*([-+]?\d+(?:\.\d+)?),\s*b:\s*([-+]?\d+(?:\.\d+)?),\s*a:\s*([-+]?\d+(?:\.\d+)?)\}",
        re.M,
    )
    for col_match in color_pat.finditer(text):
        result["colors"][col_match.group(1)] = (
            float(col_match.group(2)),
            float(col_match.group(3)),
            float(col_match.group(4)),
            float(col_match.group(5)),
        )

    tex_block_pat = re.compile(
        r"^\s*-\s*(_[A-Za-z0-9_]+):\s*\n\s*m_Texture:\s*\{[^}]*guid:\s*([0-9a-fA-F]{32})",
        re.M,
    )
    for tex_match in tex_block_pat.finditer(text):
        result["tex_guids"][tex_match.group(1)] = tex_match.group(2).lower()

    return result


def build_vtoon_slot_from_mat(
    parsed_mat: dict | None,
    slot_type: int = SLOT_CLOTH,
    override_params: dict | None = None,
    albedo_color_already_baked: bool = False,
) -> dict:
    """Convert parsed lilToon .mat properties into calibrated VToon slot fields."""
    floats = (parsed_mat or {}).get("floats", {})
    colors = (parsed_mat or {}).get("colors", {})

    def _color_lin(key: str, default_rgb: tuple[float, float, float]) -> tuple[float, float, float]:
        raw_col = colors.get(key)
        if not raw_col:
            return default_rgb
        return (
            _srgb_to_linear_channel(raw_col[0]),
            _srgb_to_linear_channel(raw_col[1]),
            _srgb_to_linear_channel(raw_col[2]),
        )

    # Baked atlas textures already carry lilToneCorrection * _Color, so emit neutral tint (1,1,1)
    # to avoid double-multiplying hair/skin pigments in the runtime shader.
    base_tint = (1.0, 1.0, 1.0) if albedo_color_already_baked else _color_lin("_Color", (1.0, 1.0, 1.0))
    use_shadow = floats.get("_UseShadow", 1.0) >= 0.5
    raw_shadow_col = _color_lin("_ShadowColor", (0.92, 0.80, 0.83)) if use_shadow else (1.0, 1.0, 1.0)
    raw_shadow2_col = _color_lin("_Shadow2ndColor", (0.85, 0.76, 0.84)) if use_shadow else (1.0, 1.0, 1.0)
    raw_border_col = _color_lin("_ShadowBorderColor", (1.0, 0.65, 0.74))
    raw_rim_col = _color_lin("_RimColor", (0.72, 0.74, 0.82))
    rim_raw_alpha = (colors.get("_RimColor") or (1, 1, 1, 0.5))[3]
    raw_mc_col = _color_lin("_MatCapColor", (1.0, 1.0, 1.0))
    mc_raw_alpha = (colors.get("_MatCapColor") or (1, 1, 1, 0.35))[3]

    shadow_strength = floats.get("_ShadowStrength", 0.85 if use_shadow else 0.0)
    shadow_border = floats.get("_ShadowBorder", 0.50)
    shadow_blur = floats.get("_ShadowBlur", 0.14)
    shadow_2nd_border = floats.get("_Shadow2ndBorder", 0.38)
    shadow_2nd_blur = floats.get("_Shadow2ndBlur", 0.25)
    shadow_border_range = floats.get("_ShadowBorderRange", 0.08 if slot_type in (SLOT_SKIN, SLOT_FACE) else 0.04)
    shadow_receive = floats.get("_ShadowReceive", 0.75)

    # Calibrated lilToon defaults per surface role
    if slot_type in (SLOT_SKIN, SLOT_FACE):
        # Skin & face: prevent chalky GTA V HDR blowout, preserve warm peach terminator
        shadow_strength = min(0.85, max(0.50, shadow_strength))
        shadow_blur = max(shadow_blur, 0.16)
        shadow_border_range = max(shadow_border_range, 0.08)
        if min(raw_shadow_col) > 0.78:
            raw_shadow_col = (0.84, 0.68, 0.69)
        light_min = max(floats.get("_LightMinLimit", 0.08), 0.20)
        light_max = min(floats.get("_LightMaxLimit", 1.0), 0.78)
        use_rim_default = 0.25 if slot_type == SLOT_SKIN else 0.0
        use_mc_default = 0.0
    elif slot_type == SLOT_EYES:
        shadow_strength = min(shadow_strength, 0.25)
        light_min = max(floats.get("_LightMinLimit", 0.25), 0.48)
        light_max = floats.get("_LightMaxLimit", 1.0)
        use_rim_default = 0.0
        use_mc_default = 1.0
    elif slot_type in (SLOT_HAIR, SLOT_HAIR_ALPHA):
        light_min = max(floats.get("_LightMinLimit", 0.10), 0.15)
        light_max = min(floats.get("_LightMaxLimit", 1.0), 0.94)
        raw_shadow2_col = tuple(
            min(raw_shadow_col[ch_idx], raw_shadow2_col[ch_idx])
            for ch_idx in range(3)
        )
        use_rim_default = 1.0 if floats.get("_UseRim", 1.0) >= 0.5 else 0.4
        use_mc_default = 1.0
    elif slot_type == SLOT_NAILS:
        light_min = max(floats.get("_LightMinLimit", 0.12), 0.18)
        light_max = min(floats.get("_LightMaxLimit", 1.0), 0.92)
        use_rim_default = 1.0
        use_mc_default = 1.0
    elif slot_type == SLOT_METAL:
        light_min = max(floats.get("_LightMinLimit", 0.12), 0.22)
        light_max = min(floats.get("_LightMaxLimit", 1.0), 0.92)
        use_rim_default = 1.0
        use_mc_default = 1.0
        if raw_mc_col == (1.0, 1.0, 1.0):
            raw_mc_col = (0.80, 0.72, 0.68)
        mc_raw_alpha = max(mc_raw_alpha, 0.58)
    else:
        light_min = max(floats.get("_LightMinLimit", 0.06), 0.14)
        light_max = min(floats.get("_LightMaxLimit", 1.0), 0.92)
        use_rim_default = 1.0 if floats.get("_UseRim", 0.0) >= 0.5 else 0.0
        use_mc_default = 1.0 if floats.get("_UseMatCap", 0.0) >= 0.5 else 0.0

    cull_mode = floats.get("_Cull", 2.0)
    double_sided = 1.0 if cull_mode < 0.5 else 0.0
    spec_val = 0.75 if slot_type == SLOT_METAL else (0.65 if slot_type in (SLOT_HAIR, SLOT_NAILS, SLOT_EYES) else 0.0)
    rim_blur_val = floats.get("_RimBlur", 0.18)
    rim_fresnel_val = floats.get("_RimFresnelPower", 3.0)
    if slot_type in (SLOT_HAIR, SLOT_HAIR_ALPHA):
        rim_blur_val = max(rim_blur_val, 0.18)
        rim_fresnel_val = max(rim_fresnel_val, 2.2)
        rim_alpha_scale = min(1.0, rim_raw_alpha)
    else:
        rim_alpha_scale = max(0.3, rim_raw_alpha)

    slot_dict = {
        "color": base_tint,
        "cutoff": floats.get("_Cutoff", 0.38 if slot_type == SLOT_HAIR else 0.001),
        "shadow_color": raw_shadow_col,
        "shadow_border": shadow_border,
        "shadow_2nd_color": raw_shadow2_col,
        "shadow_blur": shadow_blur,
        "shadow_border_color": raw_border_col,
        "shadow_border_range": shadow_border_range,
        "rim_color": tuple(ch_val * rim_alpha_scale for ch_val in raw_rim_col),
        "rim_border": floats.get("_RimBorder", 0.52),
        "matcap_color": (raw_mc_col[0], raw_mc_col[1], raw_mc_col[2], min(0.75, max(0.20, mc_raw_alpha))),
        "shadow_strength": shadow_strength if use_shadow else 0.0,
        "shadow_2nd_border": shadow_2nd_border,
        "shadow_2nd_blur": shadow_2nd_blur,
        "shadow_receive": shadow_receive,
        "light_min_limit": light_min,
        "light_max_limit": light_max,
        "rim_blur": rim_blur_val,
        "rim_fresnel": rim_fresnel_val,
        "rim_main_strength": floats.get("_RimMainStrength", 0.35),
        "use_rim": use_rim_default,
        "use_matcap": use_mc_default,
        "specular_intensity": spec_val,
        "slot_type": float(slot_type),
        "double_sided": double_sided,
    }
    if override_params:
        slot_dict.update(override_params)
    return slot_dict


def create_default_studio_matcap(size_px: int = 256) -> Image.Image:
    """Synthesize a smooth anime hair & nail anisotropic angel-ring MatCap texture."""
    coords = numpy_mod.linspace(-1.0, 1.0, size_px, dtype=numpy_mod.float32)
    grid_y, grid_x = numpy_mod.meshgrid(coords, coords, indexing="ij")
    radius_sq = grid_x * grid_x + grid_y * grid_y

    # Soft studio dome glow + crisp curved upper-front angel-ring highlight
    ring_band = numpy_mod.exp(-numpy_mod.square((grid_y + 0.36 - 0.14 * grid_x * grid_x) * 4.2))
    ring_band *= numpy_mod.clip(1.0 - numpy_mod.abs(grid_x) * 0.72, 0.0, 1.0)
    upper_sheen = numpy_mod.exp(-radius_sq * 2.6) * 0.18
    rim_arc = numpy_mod.exp(-numpy_mod.square((numpy_mod.sqrt(numpy_mod.maximum(radius_sq, 1e-5)) - 0.86) * 6.5)) * 0.22

    intensity = numpy_mod.clip(ring_band * 0.82 + upper_sheen + rim_arc, 0.0, 1.0)
    inside_sphere = radius_sq <= 1.02
    intensity = numpy_mod.where(inside_sphere, intensity, 0.0)

    rgb = numpy_mod.stack(
        [
            numpy_mod.clip(intensity * 255.0, 0.0, 255.0),
            numpy_mod.clip(intensity * 252.0, 0.0, 255.0),
            numpy_mod.clip(intensity * 255.0, 0.0, 255.0),
            numpy_mod.full_like(intensity, 255.0),
        ],
        axis=-1,
    ).astype(numpy_mod.uint8)
    return Image.fromarray(rgb, mode="RGBA")


def blender_uv_rect_to_lut_rect(
    u_offset: float,
    v_offset: float,
    u_scale: float,
    v_scale: float,
    slot_id: int,
    shadow_mask: float = 1.0,
    rim_mask: float = 0.5,
    emission_mask: float = 0.0,
) -> dict:
    """Convert Blender/manifest bottom-up UV rect into DX top-down LUT region spec."""
    u_min = max(0.0, min(1.0, float(u_offset)))
    u_max = max(u_min, min(1.0, float(u_offset) + float(u_scale)))
    v_top_dx = max(0.0, min(1.0, 1.0 - (float(v_offset) + float(v_scale))))
    v_bot_dx = max(v_top_dx, min(1.0, 1.0 - float(v_offset)))
    return {
        "u0": u_min,
        "v0": v_top_dx,
        "u1": u_max,
        "v1": v_bot_dx,
        "slot_id": int(slot_id),
        "shadow_mask": float(shadow_mask),
        "rim_mask": float(rim_mask),
        "emission_mask": float(emission_mask),
    }


def create_character_lut_image(
    lut_regions: list[dict],
    lut_size: int = 512,
    default_slot: int = 0,
    extra_eye_rects: list[tuple[float, float, float, float]] | None = None,
) -> Image.Image:
    """
    Paint 512x512 UV LUT image (DX top-down V in [0..1]):
      - R = slotId / 15 * 255
      - G = shadowStrengthMask (0..255)
      - B = rim/MatCapMask (0..255)
      - A = emission/eye-protect mask (0..255)
    """
    arr = numpy_mod.zeros((lut_size, lut_size, 4), dtype=numpy_mod.uint8)
    arr[..., 0] = int(round((default_slot / 15.0) * 255.0))
    arr[..., 1] = 240
    arr[..., 2] = 100
    arr[..., 3] = 0

    for region in lut_regions:
        u_min = max(0.0, min(1.0, float(region["u0"])))
        u_max = max(0.0, min(1.0, float(region["u1"])))
        v_min = max(0.0, min(1.0, float(region["v0"])))
        v_max = max(0.0, min(1.0, float(region["v1"])))
        slot_id = max(0, min(15, int(region.get("slot_id", 0))))
        sh_byte = int(round(_clamp_unit(region.get("shadow_mask", 1.0)) * 255.0))
        rim_byte = int(round(_clamp_unit(region.get("rim_mask", 0.5)) * 255.0))
        em_byte = int(round(_clamp_unit(region.get("emission_mask", 0.0)) * 255.0))

        px_x0 = max(0, min(lut_size - 1, int(round(u_min * lut_size))))
        px_x1 = max(px_x0 + 1, min(lut_size, int(round(u_max * lut_size))))
        px_y0 = max(0, min(lut_size - 1, int(round(v_min * lut_size))))
        px_y1 = max(px_y0 + 1, min(lut_size, int(round(v_max * lut_size))))

        arr[px_y0:px_y1, px_x0:px_x1, 0] = int(round((slot_id / 15.0) * 255.0))
        arr[px_y0:px_y1, px_x0:px_x1, 1] = sh_byte
        arr[px_y0:px_y1, px_x0:px_x1, 2] = rim_byte
        arr[px_y0:px_y1, px_x0:px_x1, 3] = em_byte

    if extra_eye_rects:
        for eye_u0, eye_v0, eye_u1, eye_v1 in extra_eye_rects:
            px_x0 = max(0, min(lut_size - 1, int(round(eye_u0 * lut_size))))
            px_x1 = max(px_x0 + 1, min(lut_size, int(round(eye_u1 * lut_size))))
            px_y0 = max(0, min(lut_size - 1, int(round(eye_v0 * lut_size))))
            px_y1 = max(px_y0 + 1, min(lut_size, int(round(eye_v1 * lut_size))))
            arr[px_y0:px_y1, px_x0:px_x1, 0] = int(round((SLOT_EYES / 15.0) * 255.0))
            arr[px_y0:px_y1, px_x0:px_x1, 1] = 85
            arr[px_y0:px_y1, px_x0:px_x1, 2] = 180
            arr[px_y0:px_y1, px_x0:px_x1, 3] = 72

    return Image.fromarray(arr, mode="RGBA")


DEFAULT_GLOBAL_CONFIG = {
    "enabled": "1",
    "debug_mode": "0",
    "daylight_scale": "0.94",
    "min_world_lum": "0.25",
    "max_world_lum": "0.86",
    "sun_soft_cap": "0.96",
    "ambient_boost": "1.00",
    "shadow_scale": "0.85",
    "alpha_boost": "1.00",
}

LEGACY_UNCALIBRATED_GLOBALS = {
    "daylight_scale": "1.00",
    "min_world_lum": "0.26",
    "max_world_lum": "1.02",
    "sun_soft_cap": "1.10",
    "ambient_boost": "1.08",
    "shadow_scale": "0.82",
}


def _parse_existing_ini(ini_path: Path) -> tuple[dict[str, str], dict[int, dict]]:
    """Read an existing GTAVVToon.ini into global keys + per-char dicts."""
    global_cfg = dict(DEFAULT_GLOBAL_CONFIG)
    chars: dict[int, dict] = {}
    if not ini_path.is_file():
        return global_cfg, chars

    cur_sec = ""
    cur_char = 0
    cur_slot = -1
    for raw_line in ini_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.split(";")[0].split("#")[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            cur_sec = line[1:-1].strip()
            cur_char = 0
            cur_slot = -1
            low = cur_sec.lower()
            if low.startswith("char_") and low[5:].isdigit():
                cur_char = int(low[5:])
                chars.setdefault(cur_char, {"meta": {}, "slots": {}})
            elif low.startswith("mat_"):
                parts = low.split("_")
                if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                    cur_char = int(parts[1])
                    cur_slot = int(parts[2])
                    chars.setdefault(cur_char, {"meta": {}, "slots": {}})
                    chars[cur_char]["slots"].setdefault(cur_slot, {})
            continue
        if "=" not in line:
            continue
        key, val = [part.strip() for part in line.split("=", 1)]
        if cur_sec.lower() == "global":
            low_key = key.lower()
            if LEGACY_UNCALIBRATED_GLOBALS.get(low_key) == val:
                global_cfg[low_key] = DEFAULT_GLOBAL_CONFIG[low_key]
            else:
                global_cfg[low_key] = val
        elif cur_char > 0 and cur_slot < 0:
            chars[cur_char]["meta"][key.lower()] = val
        elif cur_char > 0 and cur_slot >= 0:
            chars[cur_char]["slots"][cur_slot][key.lower()] = val
    return global_cfg, chars


def _format_vec(vals: tuple | list) -> str:
    return ", ".join(f"{float(item):.4f}" for item in vals)


def _format_vtoon_ini(global_cfg: dict[str, str], chars_map: dict[int, dict]) -> str:
    """Serialize `GTAVVToon.ini` `[Global]` and `[Char_*]`/`[Mat_*]` sections deterministically."""
    lines_out = [
        "; GTAVVToon.ini - Auto-calibrated from Unity lilToon materials (press F10 in-game to hot-reload)",
        "[Global]",
    ]
    for g_key, g_val in global_cfg.items():
        lines_out.append(f"{g_key} = {g_val}")

    for char_key_id in sorted(chars_map):
        char_entry = chars_map[char_key_id]
        lines_out.append("")
        lines_out.append(f"[Char_{char_key_id}]")
        for meta_key, meta_val in char_entry["meta"].items():
            lines_out.append(f"{meta_key} = {meta_val}")
        for slot_key_id in sorted(char_entry["slots"]):
            lines_out.append("")
            lines_out.append(f"[Mat_{char_key_id}_{slot_key_id}]")
            for field_key, field_val in char_entry["slots"][slot_key_id].items():
                lines_out.append(f"{field_key} = {field_val}")

    return "\n".join(lines_out) + "\n"


def upsert_vtoon_ini_character(
    ini_paths: list[Path],
    char_id: int,
    char_name: str,
    lut_rel_path: str,
    matcap_rel_path: str,
    slots_dict: dict[int, dict],
) -> None:
    """Merge [Char_<id>] and [Mat_<id>_<slot>] blocks into every target GTAVVToon.ini."""
    serialized_slots = {}
    for slot_id, slot_data in sorted(slots_dict.items()):
        slot_lines = {}
        for field_key, field_val in slot_data.items():
            if isinstance(field_val, (tuple, list)):
                slot_lines[field_key] = _format_vec(field_val)
            else:
                slot_lines[field_key] = f"{float(field_val):.4f}"
        serialized_slots[int(slot_id)] = slot_lines

    for ini_path in ini_paths:
        if not ini_path:
            continue
        ini_path.parent.mkdir(parents=True, exist_ok=True)
        global_cfg, existing_chars = _parse_existing_ini(ini_path)
        existing_chars[int(char_id)] = {
            "meta": {
                "name": char_name,
                "lut_png": lut_rel_path,
                "matcap_png": matcap_rel_path,
            },
            "slots": serialized_slots,
        }
        ini_path.write_text(_format_vtoon_ini(global_cfg, existing_chars), encoding="utf-8")


def remove_vtoon_ini_character(
    ini_paths: list[Path],
    *,
    char_ids: tuple[int, ...] = (),
    char_names: tuple[str, ...] = (),
) -> int:
    """Remove matching `[Char_<id>]` entries from one or more `GTAVVToon.ini` files."""
    target_ids = {int(cid) for cid in char_ids if cid is not None}
    target_names = {str(cname).strip().lower() for cname in char_names if str(cname).strip()}
    removed_total = 0
    for ini_path in ini_paths:
        if not ini_path or not Path(ini_path).is_file():
            continue
        global_cfg, existing_chars = _parse_existing_ini(Path(ini_path))
        to_delete = [
            cid
            for cid, entry in existing_chars.items()
            if cid in target_ids
            or str(entry.get("meta", {}).get("name", "")).strip().lower() in target_names
        ]
        if not to_delete:
            continue
        for cid in to_delete:
            del existing_chars[cid]
            removed_total += 1
        Path(ini_path).write_text(_format_vtoon_ini(global_cfg, existing_chars), encoding="utf-8")
    return removed_total


def find_best_matcap_image_for_mats(
    mat_paths: list[Path | str | None],
    assets_root: Path | None,
) -> Image.Image:
    """Resolve hair/studio _MatCapTex from character materials, skipping rainbow bubble maps."""
    import unity_hair_bake_layer as hair_bake_layer

    resolved_root = Path(assets_root) if assets_root and Path(assets_root).is_dir() else None
    fallback_path: Path | None = None
    for mat_path in mat_paths:
        if not mat_path:
            continue
        parsed = parse_liltoon_mat_file(mat_path, assets_root=resolved_root)
        matcap_guid = parsed["tex_guids"].get("_MatCapTex")
        if matcap_guid:
            matcap_path = hair_bake_layer.resolve_unity_guid(
                matcap_guid, Path(mat_path), unity_assets_root=resolved_root
            )
            if matcap_path and Path(matcap_path).is_file():
                low_stem = Path(matcap_path).stem.lower()
                if "accessories mat" in low_stem or "pin mat" in low_stem:
                    fallback_path = fallback_path or Path(matcap_path)
                    continue
                try:
                    return Image.open(matcap_path).convert("RGBA").resize((256, 256), Image.Resampling.LANCZOS)
                except Exception:
                    pass
    if fallback_path and fallback_path.is_file():
        try:
            return Image.open(fallback_path).convert("RGBA").resize((256, 256), Image.Resampling.LANCZOS)
        except Exception:
            pass
    return create_default_studio_matcap(256)


def generate_character_vtoon_assets(
    char_id: int,
    char_name: str,
    slug: str,
    package_dir: Path,
    lut_regions: list[dict],
    slot_materials: dict[int, dict],
    mat_paths_for_matcap: list[Path | str | None] | None = None,
    assets_root: Path | None = None,
    sync_dirs: list[Path] | None = None,
    extra_eye_rects: list[tuple[float, float, float, float]] | None = None,
) -> tuple[Path, Path]:
    """Build vtoon_lut_<slug>.png, vtoon_matcap_<slug>.png, and update GTAVVToon.ini."""
    package_dir = Path(package_dir)
    prof_dir = package_dir / "vtoon_profiles"
    prof_dir.mkdir(parents=True, exist_ok=True)

    lut_rel = f"vtoon_profiles\\vtoon_lut_{slug}.png"
    matcap_rel = f"vtoon_profiles\\vtoon_matcap_{slug}.png"
    lut_path = prof_dir / f"vtoon_lut_{slug}.png"
    matcap_path = prof_dir / f"vtoon_matcap_{slug}.png"

    lut_img = create_character_lut_image(lut_regions, lut_size=512, extra_eye_rects=extra_eye_rects)
    lut_img.save(lut_path)

    matcap_img = find_best_matcap_image_for_mats(mat_paths_for_matcap or [], assets_root)
    matcap_img.save(matcap_path)

    ini_targets = [package_dir / "GTAVVToon.ini"]
    for extra_dir in sync_dirs or []:
        if extra_dir and Path(extra_dir).is_dir():
            extra_prof = Path(extra_dir) / "vtoon_profiles"
            extra_prof.mkdir(parents=True, exist_ok=True)
            shutil.copy2(lut_path, extra_prof / lut_path.name)
            shutil.copy2(matcap_path, extra_prof / matcap_path.name)
            ini_targets.append(Path(extra_dir) / "GTAVVToon.ini")

    upsert_vtoon_ini_character(
        ini_paths=ini_targets,
        char_id=char_id,
        char_name=char_name,
        lut_rel_path=lut_rel,
        matcap_rel_path=matcap_rel,
        slots_dict=slot_materials,
    )
    return lut_path, matcap_path
