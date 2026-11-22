#!/usr/bin/env python3
"""
texture_calibration_helper.py
=============================
Shared image calibration and graceful fallback helpers for Shinano and Miltina
GTA V texture atlas generation.

Supports full VRChat lilToon / MoonButterfly / AWEyes material calibration
when companion masks, MatCaps, and normal maps exist locally, while degrading
cleanly to base avatar textures without raising FileNotFoundError when optional
third-party packs are unconfigured or absent.
"""

from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Union

import numpy as numpy_lib
from PIL import Image


PathLike = Union[str, Path, None]


def resolve_existing_file(
    primary_path: PathLike,
    fallback_candidates: Iterable[PathLike] = (),
) -> Optional[Path]:
    """Return the first existing file path among primary and fallback candidates."""
    candidate_list: List[PathLike] = [primary_path, *list(fallback_candidates)]
    for candidate_entry in candidate_list:
        if not candidate_entry:
            continue
        candidate_path = Path(str(candidate_entry).strip())
        if candidate_path.is_file():
            return candidate_path
    return None


def _resolve_shinano_roots(base_hair_path: Path, shinano_tex_root: PathLike) -> List[Path]:
    """Collect candidate root directories for Shinano companion Map/Mask folders."""
    candidate_roots: List[Path] = []
    if shinano_tex_root:
        explicit_root = Path(str(shinano_tex_root).strip())
        if explicit_root.is_dir():
            candidate_roots.append(explicit_root)
    parent_dir = base_hair_path.parent
    if parent_dir.is_dir() and parent_dir not in candidate_roots:
        candidate_roots.append(parent_dir)
    grandparent_dir = parent_dir.parent
    if (
        grandparent_dir.name.lower() == "color"
        and grandparent_dir.parent.is_dir()
        and grandparent_dir.parent not in candidate_roots
    ):
        candidate_roots.append(grandparent_dir.parent)
    elif grandparent_dir.is_dir() and (grandparent_dir / "Mask").is_dir():
        if grandparent_dir not in candidate_roots:
            candidate_roots.append(grandparent_dir)
    return candidate_roots


def _find_relative_companion(root_candidates: List[Path], relative_subpath: str) -> Optional[Path]:
    """Locate an optional companion texture under candidate asset roots."""
    for root_dir in root_candidates:
        direct_candidate = root_dir / relative_subpath
        if direct_candidate.is_file():
            return direct_candidate
        alt_filename = Path(relative_subpath).name
        direct_name_candidate = root_dir / alt_filename
        if direct_name_candidate.is_file():
            return direct_name_candidate
    return None


def apply_shinano_vibrant_hair_tint(image_rgba_object: Image.Image) -> Image.Image:
    """
    Transform monochrome/slate hair albedo into Shinano's calibrated sapphire-cobalt
    palette (#2956b8 lit / ~#386fd4 albedo) matching Unity Blue.mat lilToon shading.
    """
    image_pixel_array = numpy_lib.array(image_rgba_object.convert("RGBA"), dtype=numpy_lib.float32)
    red_channel = image_pixel_array[:, :, 0]
    green_channel = image_pixel_array[:, :, 1]
    blue_channel = image_pixel_array[:, :, 2]
    alpha_channel = image_pixel_array[:, :, 3]

    weighted_luminance = (
        0.299 * red_channel + 0.587 * green_channel + 0.114 * blue_channel
    )
    normalized_luminance = numpy_lib.clip(weighted_luminance / 255.0, 0.0, 1.0)

    transformed_red = numpy_lib.clip(normalized_luminance * 76.0, 0.0, 255.0)
    transformed_green = numpy_lib.clip(normalized_luminance * 144.0 + 4.0, 0.0, 255.0)
    transformed_blue = numpy_lib.clip(
        numpy_lib.power(normalized_luminance, 0.78) * 246.0 + 8.0, 0.0, 255.0
    )

    result_pixel_array = numpy_lib.stack(
        [transformed_red, transformed_green, transformed_blue, alpha_channel],
        axis=-1,
    ).astype(numpy_lib.uint8)
    return Image.fromarray(result_pixel_array, "RGBA")


def apply_shinano_skin_warmth(
    image_rgba_object: Image.Image,
    red_gain: float = 0.97,
    green_gain: float = 0.87,
    blue_gain: float = 0.85,
) -> Image.Image:
    """Apply warm peach skin tint calibration matching Unity Lueur/lilToon skin tones."""
    skin_array = numpy_lib.array(image_rgba_object.convert("RGBA"), dtype=numpy_lib.float32)
    skin_array[:, :, 0] = numpy_lib.clip(skin_array[:, :, 0] * red_gain, 0.0, 255.0)
    skin_array[:, :, 1] = numpy_lib.clip(skin_array[:, :, 1] * green_gain, 0.0, 255.0)
    skin_array[:, :, 2] = numpy_lib.clip(skin_array[:, :, 2] * blue_gain, 0.0, 255.0)
    return Image.fromarray(skin_array.astype(numpy_lib.uint8), "RGBA")


def composite_shinano_face_with_fallback(
    face_path: PathLike,
    target_size: int,
    makeup_path: PathLike = None,
    eye_sky_path: PathLike = None,
    eye_cloud_path: PathLike = None,
    eye_cloud_mask_path: PathLike = None,
    eye_highlight_path: PathLike = None,
) -> Tuple[Image.Image, List[str]]:
    """
    Composite Shinano's face with optional makeup and MoonButterfly eye layers.

    Missing optional textures are skipped gracefully so the base face eyes
    remain intact without raising FileNotFoundError. Returns (face_rgba,
    missing_optional_layer_names).
    """
    resolved_face = resolve_existing_file(face_path)
    if resolved_face is None:
        raise FileNotFoundError(f"Base Shinano face texture not found: {face_path}")

    canvas_dimension = int(target_size)
    raw_face_image = (
        Image.open(resolved_face)
        .convert("RGBA")
        .resize((canvas_dimension, canvas_dimension), Image.Resampling.LANCZOS)
    )
    composite_face = apply_shinano_skin_warmth(raw_face_image, 0.97, 0.87, 0.85)
    missing_optional_layers: List[str] = []

    resolved_makeup = resolve_existing_file(makeup_path)
    if resolved_makeup is not None:
        makeup_layer = (
            Image.open(resolved_makeup)
            .convert("RGBA")
            .resize((canvas_dimension, canvas_dimension), Image.Resampling.LANCZOS)
        )
        composite_face.alpha_composite(makeup_layer)
    elif makeup_path:
        missing_optional_layers.append("makeup")

    resolved_sky = resolve_existing_file(eye_sky_path)
    if resolved_sky is not None:
        sky_layer = (
            Image.open(resolved_sky)
            .convert("RGBA")
            .resize((canvas_dimension, canvas_dimension), Image.Resampling.LANCZOS)
        )
        composite_face.alpha_composite(sky_layer)
    elif eye_sky_path:
        missing_optional_layers.append("eye_sky")

    resolved_cloud = resolve_existing_file(eye_cloud_path)
    resolved_cloud_mask = resolve_existing_file(eye_cloud_mask_path)
    if resolved_cloud is not None and resolved_cloud_mask is not None:
        cloud_layer = (
            Image.open(resolved_cloud)
            .convert("RGBA")
            .resize((canvas_dimension, canvas_dimension), Image.Resampling.LANCZOS)
        )
        cloud_mask = (
            Image.open(resolved_cloud_mask)
            .convert("L")
            .resize((canvas_dimension, canvas_dimension), Image.Resampling.LANCZOS)
        )
        cloud_array = numpy_lib.array(cloud_layer, dtype=numpy_lib.float32)
        normalized_mask = (numpy_lib.array(cloud_mask, dtype=numpy_lib.float32) / 255.0) * 0.434
        cloud_array[:, :, 3] = numpy_lib.clip(normalized_mask * 255.0, 0.0, 255.0).astype(
            numpy_lib.uint8
        )
        composite_face.alpha_composite(
            Image.fromarray(cloud_array.astype(numpy_lib.uint8), "RGBA")
        )
    elif eye_cloud_path or eye_cloud_mask_path:
        missing_optional_layers.append("eye_cloud")

    resolved_highlight = resolve_existing_file(eye_highlight_path)
    if resolved_highlight is not None:
        highlight_layer = (
            Image.open(resolved_highlight)
            .convert("RGBA")
            .resize((canvas_dimension, canvas_dimension), Image.Resampling.LANCZOS)
        )
        composite_face.alpha_composite(highlight_layer)
    elif eye_highlight_path:
        missing_optional_layers.append("eye_highlight")

    return composite_face, missing_optional_layers


def build_shinano_face_specular(
    spec_size: int,
    shinano_tex_root: PathLike,
    emission_mask_path: PathLike = None,
) -> Optional[numpy_lib.ndarray]:
    """
    Build a boolean mask for glossy eye catchlight specular pixels using
    Shinano_face_emission_mask.png when present.
    """
    candidate_paths: List[PathLike] = []
    if shinano_tex_root:
        root_path = Path(str(shinano_tex_root).strip())
        candidate_paths.extend(
            [
                root_path / "Mask" / "Shinano_face_emission_mask.png",
                root_path / "Shinano_face_emission_mask.png",
            ]
        )
    resolved_mask = resolve_existing_file(emission_mask_path, candidate_paths)
    if resolved_mask is None:
        return None

    mask_image = (
        Image.open(resolved_mask)
        .convert("L")
        .resize((int(spec_size), int(spec_size)), Image.Resampling.LANCZOS)
    )
    mask_normalized = numpy_lib.array(mask_image, dtype=numpy_lib.float32) / 255.0
    return mask_normalized > 0.20


def generate_directional_hair_normal(
    luminance_array: Union[numpy_lib.ndarray, Image.Image],
    strength: float = 2.0,
) -> Image.Image:
    """Generate a tangent-space normal map from hair luminance gradients."""
    raw_array = numpy_lib.asarray(luminance_array, dtype=numpy_lib.float32)
    if raw_array.ndim == 3:
        if raw_array.shape[2] >= 3:
            raw_array = (
                0.299 * raw_array[..., 0]
                + 0.587 * raw_array[..., 1]
                + 0.114 * raw_array[..., 2]
            )
        else:
            raw_array = raw_array[..., 0]
    norm_luma = raw_array / 255.0
    grad_y, grad_x = numpy_lib.gradient(norm_luma)

    normal_x = -grad_x * strength
    normal_y = grad_y * strength
    normal_z = numpy_lib.ones_like(norm_luma, dtype=numpy_lib.float32)
    vec_length = numpy_lib.sqrt(normal_x * normal_x + normal_y * normal_y + normal_z * normal_z)
    vec_length = numpy_lib.maximum(vec_length, 1e-6)

    encoded_red = numpy_lib.clip(((normal_x / vec_length) * 0.5 + 0.5) * 255.0, 0.0, 255.0)
    encoded_green = numpy_lib.clip(((normal_y / vec_length) * 0.5 + 0.5) * 255.0, 0.0, 255.0)
    encoded_blue = numpy_lib.clip(((normal_z / vec_length) * 0.5 + 0.5) * 255.0, 0.0, 255.0)
    opaque_alpha = numpy_lib.full_like(encoded_red, 255.0)

    normal_rgba = numpy_lib.stack(
        [encoded_red, encoded_green, encoded_blue, opaque_alpha], axis=-1
    ).astype(numpy_lib.uint8)
    return Image.fromarray(normal_rgba, "RGBA")


def calibrate_shinano_default_hair(
    base_hair_path: PathLike,
    shinano_tex_root: PathLike,
    output_size: int,
    target_tint_path: PathLike = None,
) -> Tuple[Image.Image, Image.Image, Image.Image]:
    """
    Calibrate Shinano's default hair diffuse, specular, and normal textures.

    Applies optional cyan inner streaks (Shinano_hair_mesh_mask3.png), silky
    MatCap & rim highlights (Map/Matcap.png + Mask/Shinano_hair_lim_mask.png),
    and Map/Shinano_hair_normal.png when available locally, degrading cleanly
    when only the base hair PNG is present.
    """
    chosen_source = resolve_existing_file(target_tint_path, [base_hair_path])
    if chosen_source is None:
        raise FileNotFoundError(f"Base Shinano hair texture not found: {base_hair_path}")

    cell_dim = int(output_size)
    raw_hair_image = Image.open(chosen_source).convert("RGBA")
    tinted_hair_image = apply_shinano_vibrant_hair_tint(raw_hair_image).resize(
        (cell_dim, cell_dim), Image.Resampling.LANCZOS
    )
    diffuse_array = numpy_lib.array(tinted_hair_image, dtype=numpy_lib.float32)

    specular_array = numpy_lib.full((cell_dim, cell_dim, 4), [34, 48, 64, 96], dtype=numpy_lib.uint8)

    root_candidates = _resolve_shinano_roots(chosen_source, shinano_tex_root)
    mesh_mask3_path = _find_relative_companion(root_candidates, "Mask/Shinano_hair_mesh_mask3.png")
    if mesh_mask3_path is not None:
        mesh_mask_img = (
            Image.open(mesh_mask3_path)
            .convert("L")
            .resize((cell_dim, cell_dim), Image.Resampling.LANCZOS)
        )
        mesh_mask_weight = (numpy_lib.array(mesh_mask_img, dtype=numpy_lib.float32) / 255.0) * 0.25
        cyan_tint = numpy_lib.array([65.0, 195.0, 255.0], dtype=numpy_lib.float32)
        for ch_idx in range(3):
            diffuse_array[:, :, ch_idx] = (
                diffuse_array[:, :, ch_idx] * (1.0 - mesh_mask_weight)
                + cyan_tint[ch_idx] * mesh_mask_weight
            )

    lim_mask_path = _find_relative_companion(root_candidates, "Mask/Shinano_hair_lim_mask.png")
    matcap_path = _find_relative_companion(root_candidates, "Map/Matcap.png")
    matcap_gain = 1.0
    if matcap_path is not None:
        matcap_image = Image.open(matcap_path).convert("RGB")
        matcap_mean = float(numpy_lib.mean(numpy_lib.array(matcap_image, dtype=numpy_lib.float32))) / 255.0
        matcap_gain = 0.85 + (matcap_mean * 0.45)

    if lim_mask_path is not None:
        lim_mask_img = (
            Image.open(lim_mask_path)
            .convert("L")
            .resize((cell_dim, cell_dim), Image.Resampling.LANCZOS)
        )
        lim_weight = (numpy_lib.array(lim_mask_img, dtype=numpy_lib.float32) / 255.0) * 0.30 * matcap_gain
        diffuse_array[:, :, 0] += lim_weight * 48.0
        diffuse_array[:, :, 1] += lim_weight * 66.0
        diffuse_array[:, :, 2] += lim_weight * 82.0

        highlight_mask = lim_weight > 0.14
        specular_array[highlight_mask] = [92, 112, 128, 196]

    diffuse_final = Image.fromarray(
        numpy_lib.clip(diffuse_array, 0.0, 255.0).astype(numpy_lib.uint8), "RGBA"
    )
    specular_final = Image.fromarray(specular_array, "RGBA")

    hair_normal_path = _find_relative_companion(root_candidates, "Map/Shinano_hair_normal.png")
    if hair_normal_path is not None:
        normal_rgb = (
            Image.open(hair_normal_path)
            .convert("RGB")
            .resize((cell_dim, cell_dim), Image.Resampling.LANCZOS)
        )
        normal_final = Image.new("RGBA", (cell_dim, cell_dim), (128, 128, 255, 255))
        normal_final.paste(normal_rgb, (0, 0))
    else:
        gray_luma = numpy_lib.array(
            raw_hair_image.convert("L").resize((cell_dim, cell_dim), Image.Resampling.LANCZOS),
            dtype=numpy_lib.float32,
        )
        normal_final = generate_directional_hair_normal(gray_luma, strength=2.2)

    return diffuse_final, specular_final, normal_final


def _resolve_miltina_material_roots(
    base_hair_path: Path,
    dolosart_mat_dir: PathLike,
) -> List[Path]:
    """Collect candidate root directories for Milltina Material Mask/Matcap files."""
    roots: List[Path] = []
    if dolosart_mat_dir:
        explicit_dir = Path(str(dolosart_mat_dir).strip())
        if explicit_dir.is_dir():
            roots.append(explicit_dir)
    for ancestor in (base_hair_path.parent, base_hair_path.parent.parent):
        if ancestor.is_dir() and ancestor not in roots:
            roots.append(ancestor)
    return roots


def calibrate_miltina_default_hair(
    base_hair_path: PathLike,
    dolosart_mat_dir: PathLike,
    output_size: int,
) -> Tuple[Image.Image, Image.Image, Image.Image]:
    """
    Calibrate Miltina's default sapphire-blue hair replicating Milltina_Hair.mat
    (_Color, _MainTexHSVG, Hair_matcap.png + Matcap_Mask, RimLight_Mask), with
    procedural tangent-space strand normals and clean fallback if masks are absent.
    """
    resolved_hair = resolve_existing_file(base_hair_path)
    if resolved_hair is None:
        raise FileNotFoundError(f"Base Miltina hair texture not found: {base_hair_path}")

    cell_dim = int(output_size)
    raw_hair_image = (
        Image.open(resolved_hair)
        .convert("RGBA")
        .resize((cell_dim, cell_dim), Image.Resampling.LANCZOS)
    )
    hair_array = numpy_lib.array(raw_hair_image, dtype=numpy_lib.float32)

    # Milltina_Hair.mat: _Color=(0.3317, 0.7755, 0.9906) modulated with _MainTexHSVG
    # calibrated to preserve strand highlights without blowing out white peaks.
    base_red = hair_array[:, :, 0]
    base_green = hair_array[:, :, 1]
    base_blue = hair_array[:, :, 2]
    hair_luma = (0.299 * base_red + 0.587 * base_green + 0.114 * base_blue) / 255.0
    gamma_luma = numpy_lib.power(numpy_lib.clip(hair_luma, 0.0, 1.0), 0.90)

    # Blend original shading with Material _Color sapphire ratio
    sapphire_color = numpy_lib.array([0.3317, 0.7755, 0.9906], dtype=numpy_lib.float32)
    tinted_red = (base_red * 0.45 + gamma_luma * 255.0 * 0.55) * (sapphire_color[0] * 1.18)
    tinted_green = (base_green * 0.45 + gamma_luma * 255.0 * 0.55) * (sapphire_color[1] * 0.98)
    tinted_blue = (base_blue * 0.45 + gamma_luma * 255.0 * 0.55) * (sapphire_color[2] * 1.12)

    hair_array[:, :, 0] = tinted_red
    hair_array[:, :, 1] = tinted_green
    hair_array[:, :, 2] = tinted_blue

    specular_array = numpy_lib.full(
        (cell_dim, cell_dim, 4), [140, 140, 140, 255], dtype=numpy_lib.uint8
    )

    mat_roots = _resolve_miltina_material_roots(resolved_hair, dolosart_mat_dir)
    matcap_mask_path = _find_relative_companion(mat_roots, "Mask/Milltina_Hair_Matcap_Mask.png")
    matcap_tex_path = _find_relative_companion(mat_roots, "Matcap/Hair_matcap.png")
    rim_mask_path = _find_relative_companion(mat_roots, "Mask/Milltina_Hair_RimLight_Mask.png")
    rim_alpha_mask_path = _find_relative_companion(mat_roots, "Mask/Milltina_Hair_RimLight_Alpha_Mask.png")

    if rim_alpha_mask_path is not None:
        alpha_mask_img = (
            Image.open(rim_alpha_mask_path)
            .convert("RGBA")
            .resize((cell_dim, cell_dim), Image.Resampling.LANCZOS)
        )
        alpha_mask_r = numpy_lib.array(alpha_mask_img, dtype=numpy_lib.float32)[:, :, 0] / 255.0
        hair_array[:, :, 3] = numpy_lib.clip(hair_array[:, :, 3] * alpha_mask_r, 0.0, 255.0)

    if matcap_mask_path is not None:
        matcap_mask = (
            Image.open(matcap_mask_path)
            .convert("L")
            .resize((cell_dim, cell_dim), Image.Resampling.LANCZOS)
        )
        matcap_weight = numpy_lib.array(matcap_mask, dtype=numpy_lib.float32) / 255.0
        matcap_boost = 1.0
        if matcap_tex_path is not None:
            matcap_img = Image.open(matcap_tex_path).convert("RGB")
            matcap_peak = float(numpy_lib.max(numpy_lib.array(matcap_img, dtype=numpy_lib.float32))) / 255.0
            matcap_boost = 0.85 + 0.35 * matcap_peak

        # _MatCapColor: (2.12, 1.90, 1.79, a=0.4) attenuated for LDR atlas headroom
        spec_lift = matcap_weight * 0.26 * matcap_boost
        hair_array[:, :, 0] += spec_lift * 115.0
        hair_array[:, :, 1] += spec_lift * 135.0
        hair_array[:, :, 2] += spec_lift * 155.0

        silky_region = matcap_weight > 0.35
        specular_array[silky_region] = [180, 195, 180, 255]

    if rim_mask_path is not None:
        rim_mask = (
            Image.open(rim_mask_path)
            .convert("L")
            .resize((cell_dim, cell_dim), Image.Resampling.LANCZOS)
        )
        rim_weight = (numpy_lib.array(rim_mask, dtype=numpy_lib.float32) / 255.0) * 0.16
        # _RimColor: (0.436, 0.474, 0.717)
        hair_array[:, :, 0] += rim_weight * 111.0
        hair_array[:, :, 1] += rim_weight * 121.0
        hair_array[:, :, 2] += rim_weight * 183.0

    diffuse_final = Image.fromarray(
        numpy_lib.clip(hair_array, 0.0, 255.0).astype(numpy_lib.uint8), "RGBA"
    )
    specular_final = Image.fromarray(specular_array, "RGBA")
    normal_final = generate_directional_hair_normal(hair_luma * 255.0, strength=2.0)

    return diffuse_final, specular_final, normal_final


def composite_miltina_eyes_with_fallback(
    face_rgba: Image.Image,
    eye_base_path: PathLike,
    eye_highlight_path: PathLike = None,
    nagima_mat_dir: PathLike = None,
) -> Tuple[Image.Image, Optional[numpy_lib.ndarray], bool]:
    """
    Composite Miltina AWEyes layers (iris, optional Light/MatCap/MatLight masks,
    and highlight) over base Milltina_Face.png.

    If eye_base_path is unset or missing on disk, returns the original face_rgba
    unchanged with used_custom_eyes=False so Milltina's default painted eyes
    render cleanly without errors.
    """
    resolved_eye_base = resolve_existing_file(eye_base_path)
    if resolved_eye_base is None:
        return face_rgba.convert("RGBA"), None, False

    working_face = face_rgba.convert("RGBA").copy()
    face_width, face_height = working_face.size

    eye_base_layer = (
        Image.open(resolved_eye_base)
        .convert("RGBA")
        .resize((face_width, face_height), Image.Resampling.LANCZOS)
    )
    working_face = Image.alpha_composite(working_face, eye_base_layer)
    eye_base_alpha = numpy_lib.array(eye_base_layer, dtype=numpy_lib.float32)[:, :, 3] / 255.0
    iris_region_mask = eye_base_alpha > 0.08

    mat_candidates: List[Path] = []
    if nagima_mat_dir:
        explicit_mat_dir = Path(str(nagima_mat_dir).strip())
        if explicit_mat_dir.is_dir():
            mat_candidates.append(explicit_mat_dir)
    if resolved_eye_base.parent.parent.is_dir():
        mat_candidates.append(resolved_eye_base.parent.parent)

    resolved_highlight = resolve_existing_file(eye_highlight_path)
    if resolved_highlight is not None:
        highlight_layer = (
            Image.open(resolved_highlight)
            .convert("RGBA")
            .resize((face_width, face_height), Image.Resampling.LANCZOS)
        )
        working_face = Image.alpha_composite(working_face, highlight_layer)

    # Apply iris-only additive luminous lift from Light UV mask (never overlay opaque
    # black-background masks or view-space MatCap spheres onto face skin UVs).
    light_mask_file = _find_relative_companion(mat_candidates, "Mask/Milltina_AWEyes_Light.png")
    if light_mask_file is not None and numpy_lib.any(iris_region_mask):
        light_luma = (
            numpy_lib.array(
                Image.open(light_mask_file)
                .convert("L")
                .resize((face_width, face_height), Image.Resampling.LANCZOS),
                dtype=numpy_lib.float32,
            )
            / 255.0
        )
        face_rgb = numpy_lib.array(working_face, dtype=numpy_lib.float32)
        iris_boost = numpy_lib.where(iris_region_mask, light_luma * 0.28, 0.0)
        for ch_idx, tint_scale in enumerate((0.80, 0.92, 1.15)):
            face_rgb[:, :, ch_idx] = numpy_lib.clip(
                face_rgb[:, :, ch_idx] + iris_boost * 255.0 * tint_scale,
                0.0,
                255.0,
            )
        working_face = Image.fromarray(face_rgb.astype(numpy_lib.uint8), "RGBA")

    eye_spec_mask: Optional[numpy_lib.ndarray] = None
    mat_light_file = _find_relative_companion(mat_candidates, "Mask/Milltina_AWEyes_MatLight.png")
    if mat_light_file is None:
        mat_light_file = light_mask_file
    if mat_light_file is not None and numpy_lib.any(iris_region_mask):
        spec_gray = (
            Image.open(mat_light_file)
            .convert("L")
            .resize((face_width, face_height), Image.Resampling.LANCZOS)
        )
        eye_spec_mask = ((numpy_lib.array(spec_gray, dtype=numpy_lib.float32) / 255.0) > 0.25) & iris_region_mask

    return working_face, eye_spec_mask, True
