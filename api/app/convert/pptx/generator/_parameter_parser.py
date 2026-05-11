"""Parameter normalisation and clamping for PPTX generation."""

from __future__ import annotations

from typing import Any


def normalise_parameters(
    text_erase_mode: str = "fill",
    scanned_page_mode: str = "segmented",
    ppt_generation_mode: str = "standard",
    scanned_render_dpi: Any = 200,
    image_bg_clear_expand_min_pt: Any = 0.35,
    image_bg_clear_expand_max_pt: Any = 1.5,
    image_bg_clear_expand_ratio: Any = 0.012,
    scanned_image_region_min_area_ratio: Any = 0.0025,
    scanned_image_region_max_area_ratio: Any = 0.72,
    scanned_image_region_max_aspect_ratio: Any = 4.8,
) -> dict[str, Any]:
    """Normalise and clamp all generation parameters.

    Returns a dict with the normalised values (suffixed with '_id').
    Also returns flag booleans for fast/turbo detection.
    """

    text_erase_mode_id = str(text_erase_mode or "fill").strip().lower()
    if text_erase_mode_id not in {"smart", "fill"}:
        text_erase_mode_id = "fill"

    scanned_page_mode_id = str(scanned_page_mode or "segmented").strip().lower()
    if scanned_page_mode_id in {"chunk", "chunked", "split", "blocks"}:
        scanned_page_mode_id = "segmented"
    if scanned_page_mode_id in {"page", "full", "full_page"}:
        scanned_page_mode_id = "fullpage"
    if scanned_page_mode_id not in {"segmented", "fullpage"}:
        scanned_page_mode_id = "segmented"

    ppt_generation_mode_id = str(ppt_generation_mode or "standard").strip().lower()
    if ppt_generation_mode_id in {"default", "normal", "balanced", "quality"}:
        ppt_generation_mode_id = "standard"
    if ppt_generation_mode_id in {
        "speed",
        "speed_first",
        "speed-first",
        "fast_experimental",
        "experimental_fast",
    }:
        ppt_generation_mode_id = "fast"
    if ppt_generation_mode_id in {"ultra", "extreme", "turbo_fast", "turbo-fast"}:
        ppt_generation_mode_id = "turbo"
    if ppt_generation_mode_id not in {"standard", "fast", "turbo"}:
        ppt_generation_mode_id = "standard"

    is_fast_ppt_generation = ppt_generation_mode_id == "fast"
    is_turbo_ppt_generation = ppt_generation_mode_id == "turbo"
    is_speed_ppt_generation = is_fast_ppt_generation or is_turbo_ppt_generation
    if is_speed_ppt_generation:
        text_erase_mode_id = "fill"
    try:
        scanned_render_dpi = int(scanned_render_dpi)
    except Exception:
        scanned_render_dpi = 200
    if scanned_render_dpi <= 0:
        scanned_render_dpi = 200
    if is_speed_ppt_generation:
        scanned_render_dpi = min(scanned_render_dpi, 120)

    def _clamp_float(value: Any, *, default: float, low: float, high: float) -> float:
        try:
            num = float(value)
        except Exception:
            num = float(default)
        if num < low:
            num = float(low)
        if num > high:
            num = float(high)
        return float(num)

    image_bg_clear_expand_min_pt_id = _clamp_float(
        image_bg_clear_expand_min_pt,
        default=0.35,
        low=0.0,
        high=6.0,
    )
    image_bg_clear_expand_max_pt_id = _clamp_float(
        image_bg_clear_expand_max_pt,
        default=1.5,
        low=0.0,
        high=8.0,
    )
    if image_bg_clear_expand_max_pt_id < image_bg_clear_expand_min_pt_id:
        image_bg_clear_expand_max_pt_id = image_bg_clear_expand_min_pt_id
    image_bg_clear_expand_ratio_id = _clamp_float(
        image_bg_clear_expand_ratio,
        default=0.012,
        low=0.0,
        high=0.12,
    )
    scanned_image_region_min_area_ratio_id = _clamp_float(
        scanned_image_region_min_area_ratio,
        default=0.0025,
        low=0.0,
        high=0.35,
    )
    scanned_image_region_max_area_ratio_id = _clamp_float(
        scanned_image_region_max_area_ratio,
        default=0.72,
        low=0.05,
        high=1.0,
    )
    if scanned_image_region_max_area_ratio_id <= scanned_image_region_min_area_ratio_id:
        scanned_image_region_max_area_ratio_id = min(
            1.0,
            scanned_image_region_min_area_ratio_id + 0.05,
        )
    scanned_image_region_max_aspect_ratio_id = _clamp_float(
        scanned_image_region_max_aspect_ratio,
        default=4.8,
        low=1.2,
        high=30.0,
    )

    return {
        "text_erase_mode_id": text_erase_mode_id,
        "scanned_page_mode_id": scanned_page_mode_id,
        "ppt_generation_mode_id": ppt_generation_mode_id,
        "is_fast_ppt_generation": is_fast_ppt_generation,
        "is_turbo_ppt_generation": is_turbo_ppt_generation,
        "is_speed_ppt_generation": is_speed_ppt_generation,
        "scanned_render_dpi": scanned_render_dpi,
        "image_bg_clear_expand_min_pt": image_bg_clear_expand_min_pt_id,
        "image_bg_clear_expand_max_pt": image_bg_clear_expand_max_pt_id,
        "image_bg_clear_expand_ratio": image_bg_clear_expand_ratio_id,
        "scanned_image_region_min_area_ratio": scanned_image_region_min_area_ratio_id,
        "scanned_image_region_max_area_ratio": scanned_image_region_max_area_ratio_id,
        "scanned_image_region_max_aspect_ratio": scanned_image_region_max_aspect_ratio_id,
    }
