"""High-level MedGemma body-part labeling API for DICOM series."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .config import DEFAULT_CT_WINDOW_LEVEL, DEFAULT_CT_WINDOW_WIDTH
from .dicom_utils import collect_dicom_files, group_by_series, is_dicom_file, load_series, safe_extract_zip
from .medgemma_inference import run_medgemma
from .metadata_utils import extract_metadata_body_labels, extract_modality, get_safe_series_metadata
from .series_rendering import render_adaptive_series_montages


def dedupe_labels(labels: list[str]) -> list[str]:
    cleaned = []
    for label in labels:
        if label and label not in cleaned:
            cleaned.append(label)
    if len(cleaned) > 1 and "unknown" in cleaned:
        cleaned.remove("unknown")
    return cleaned or ["unknown"]


def apply_label_consistency_rules(labels: list[str], metadata_labels: list[str]) -> tuple[list[str], list[str]]:
    """Apply conservative rules to reduce common VLM label drift."""
    warnings = []
    cleaned = dedupe_labels(labels)
    metadata_set = set(metadata_labels) - {"unknown"}
    output_set = set(cleaned) - {"unknown"}

    torso_labels = {"chest_lung", "abdomen", "pelvis"}
    neuro_labels = {"brain", "head_neck"}
    if ((metadata_set | output_set) & torso_labels) and (output_set & neuro_labels) and "whole_body" not in output_set:
        cleaned = [label for label in cleaned if label not in neuro_labels]
        warnings.append("Removed brain/head_neck from a non-whole-body torso label set.")

    if cleaned == ["unknown"] and metadata_set:
        cleaned = [label for label in metadata_labels if label != "unknown"]
        warnings.append("MedGemma returned unknown; using metadata-derived body label as a fallback.")

    return dedupe_labels(cleaned), warnings


def label_series(series_paths: list[Path], source_path: str | Path | None = None) -> dict:
    series_data = load_series(series_paths)
    warnings = list(series_data.get("warnings", []))
    metadata = get_safe_series_metadata(series_data)
    modality = extract_modality(metadata)
    metadata_labels = extract_metadata_body_labels(metadata)
    montages, selected_indices = render_adaptive_series_montages(
        series_data,
        max_slices=64,
        max_tiles_per_montage=64,
        window_level=DEFAULT_CT_WINDOW_LEVEL,
        window_width=DEFAULT_CT_WINDOW_WIDTH,
    )

    page_results = []
    all_labels = []
    for montage in montages:
        result = run_medgemma(montage, modality, metadata)
        page_results.append(result)
        if result.get("warning"):
            warnings.append(result["warning"])
        all_labels.extend(result.get("visible_body_regions", []))

    body_labels, consistency_warnings = apply_label_consistency_rules(all_labels, metadata_labels)
    warnings.extend(consistency_warnings)

    return {
        "source_path": str(source_path or ""),
        "series_uid": series_data.get("series_uid", ""),
        "study_uid": metadata.get("StudyInstanceUID", ""),
        "modality": modality,
        "body_part_labels": body_labels,
        "metadata_body_labels": metadata_labels,
        "n_files": series_data.get("n_files", len(series_paths)),
        "n_frames": int(series_data["volume"].shape[0]),
        "adaptive_slice_count": int(len(selected_indices)),
        "montage_page_count": int(len(montages)),
        "safe_metadata": metadata,
        "warnings": warnings,
        "page_results": page_results,
    }


def _series_map_from_path(input_path: Path) -> tuple[dict[str, list[Path]], tempfile.TemporaryDirectory | None]:
    tempdir = None
    if input_path.is_file() and input_path.suffix.lower() == ".zip":
        tempdir = tempfile.TemporaryDirectory()
        root = safe_extract_zip(input_path, Path(tempdir.name))
        paths = collect_dicom_files(root)
    elif input_path.is_file():
        paths = [input_path] if is_dicom_file(input_path) else []
    else:
        paths = collect_dicom_files(input_path)
    return group_by_series(paths), tempdir


def label_input_path(input_path: str | Path) -> list[dict]:
    input_path = Path(input_path)
    series_map, tempdir = _series_map_from_path(input_path)
    try:
        results = []
        for _, paths in sorted(series_map.items()):
            results.append(label_series(paths, source_path=input_path))
        return results
    finally:
        if tempdir is not None:
            tempdir.cleanup()
