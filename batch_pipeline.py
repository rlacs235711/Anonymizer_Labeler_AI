"""Batch anonymize DICOM inputs and append MedGemma body-part labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .anonymizer_bridge import basic_anonymize_dicom_tree, copy_preanonymized_input, run_rsna_anonymizer
from .medgemma_labeler import label_anonymized_output, merge_anonymizer_and_label_rows
from .pipeline_utils import ensure_dir, next_available_output_dir, prepare_input_tree, write_csv


LABEL_OUTPUT_COLUMNS = ["modality", "body_part_labels"]


def _ordered_combined_fieldnames(rows: list[dict]) -> list[str]:
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in LABEL_OUTPUT_COLUMNS and key not in fieldnames:
                fieldnames.append(key)
    return fieldnames + [key for key in LABEL_OUTPUT_COLUMNS if any(key in row for row in rows)]


def run_pipeline(
    input_path: Path,
    output_dir: Path,
    anonymizer_mode: str,
    rsna_config: Path | None = None,
    rsna_executable: str = "rsna-anonymizer",
    create_numbered_output: bool = True,
) -> dict:
    run_output_dir = next_available_output_dir(output_dir) if create_numbered_output else ensure_dir(output_dir)
    anonymized_output_dir = ensure_dir(run_output_dir / "anonymized_dicom")
    outputs_dir = ensure_dir(run_output_dir / "csv")
    prepared_root, tempdir = prepare_input_tree(input_path)
    try:
        if anonymizer_mode == "rsna":
            if rsna_config is None:
                raise ValueError("--rsna-config is required when --anonymizer-mode rsna")
            completed = run_rsna_anonymizer(rsna_config, executable=rsna_executable)
            anonymizer_rows = [
                {
                    "anonymizer_mode": "rsna",
                    "rsna_config": str(rsna_config),
                    "rsna_stdout": completed.stdout,
                    "rsna_stderr": completed.stderr,
                }
            ]
            # RSNA project config must write anonymized files into this run's
            # anonymized_dicom folder for the labeling stage to scan them.
        elif anonymizer_mode == "basic":
            anonymizer_rows = basic_anonymize_dicom_tree(prepared_root, anonymized_output_dir)
        elif anonymizer_mode == "preanonymized":
            anonymizer_rows = copy_preanonymized_input(prepared_root, anonymized_output_dir)
        else:
            raise ValueError(f"Unsupported anonymizer mode: {anonymizer_mode}")

        label_results, label_rows = label_anonymized_output(anonymized_output_dir)
        combined_rows = merge_anonymizer_and_label_rows(anonymizer_rows, label_rows)

        anonymizer_csv = outputs_dir / "anonymizer_stage.csv"
        labels_csv = outputs_dir / "medgemma_helper_labels.csv"
        combined_csv = outputs_dir / "combined_results.csv"
        labels_json = outputs_dir / "medgemma_helper_labels.json"

        write_csv(anonymizer_rows, anonymizer_csv)
        write_csv(label_rows, labels_csv)
        write_csv(combined_rows, combined_csv, fieldnames=_ordered_combined_fieldnames(combined_rows))
        labels_json.write_text(json.dumps(label_results, indent=2))

        return {
            "output_dir": str(run_output_dir),
            "anonymized_output_dir": str(anonymized_output_dir),
            "anonymizer_csv": str(anonymizer_csv),
            "labels_csv": str(labels_csv),
            "combined_csv": str(combined_csv),
            "labels_json": str(labels_json),
            "n_series_labeled": len(label_rows),
        }
    finally:
        tempdir.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run anonymization + MedGemma labeling pipeline.")
    parser.add_argument("--input", default="pipeline_anonymize_label/input", help="Input folder, ZIP, or DICOM file.")
    parser.add_argument("--output", default="pipeline_anonymize_label/output", help="Output folder. If populated, output (1), output (2), etc. will be used.")
    parser.add_argument(
        "--anonymizer-mode",
        choices=["basic", "preanonymized", "rsna"],
        default="basic",
        help="basic: local metadata cleaner; preanonymized: copy only; rsna: call RSNA Anonymizer config.",
    )
    parser.add_argument("--rsna-config", help="Path to RSNA Anonymizer ProjectModel.json for headless mode.")
    parser.add_argument("--rsna-executable", default="rsna-anonymizer")
    args = parser.parse_args()

    summary = run_pipeline(
        input_path=Path(args.input),
        output_dir=Path(args.output),
        anonymizer_mode=args.anonymizer_mode,
        rsna_config=Path(args.rsna_config) if args.rsna_config else None,
        rsna_executable=args.rsna_executable,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
