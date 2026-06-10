# Batch Pipeline: Anonymize + MedGemma Label

Batch wrapper for:

```text
DICOM input -> anonymized DICOM output -> MedGemma body-part labels -> CSV
```

This is a research prototype and is not for clinical use.

## Folder Layout

```text
pipeline_anonymize_label/
  input/                 # local batch inputs; contents not committed
  output/                # generated run output; not committed
  output (1)/            # created automatically if output/ is populated
```

Input can be:

- DICOM folders
- ZIPs containing DICOMs or DICOM folders
- individual DICOM files

The `input/` folder is intentionally committed empty through `input/.gitkeep`.
Raw DICOMs, generated outputs, model caches, and Python caches are ignored.

## Install

From the project root:

```bash
pip install -r pipeline_anonymize_label/requirements-pipeline.txt
```

The pipeline imports `label_creator`, so keep this folder at the project root
next to `label_creator/`.

## Run

Place DICOM inputs under:

```text
pipeline_anonymize_label/input/
```

Run:

```bash
python -m pipeline_anonymize_label.batch_pipeline
```

If your shell does not expose `python`, use the project virtual environment:

```bash
.venv/bin/python -m pipeline_anonymize_label.batch_pipeline
```

By default, this reads from `pipeline_anonymize_label/input/`, writes to
`pipeline_anonymize_label/output/`, and uses `basic` anonymization mode.

You can also pass explicit paths:

```bash
python -m pipeline_anonymize_label.batch_pipeline \
  --input path/to/dicom_or_zip \
  --output pipeline_anonymize_label/output \
  --anonymizer-mode basic
```

## Outputs

Each run writes:

```text
pipeline_anonymize_label/output/anonymized_dicom/
pipeline_anonymize_label/output/csv/anonymizer_stage.csv
pipeline_anonymize_label/output/csv/medgemma_helper_labels.csv
pipeline_anonymize_label/output/csv/combined_results.csv
pipeline_anonymize_label/output/csv/medgemma_helper_labels.json
```

If `output/` already exists and contains files, the pipeline writes to the next
available folder, such as `output (1)`, `output (2)`, and so on.

`combined_results.csv` includes anonymizer metadata followed by the generated
modality and body-part label columns:

```text
source_series_uid
anonymized_series_uid
anonymized_study_uid
anonymizer_mode
anonymized_series_path
series_uid
modality
body_part_labels
```

## Anonymization Modes

### `basic`

Runs a basic local metadata de-identification fallback implemented in this
pipeline. It blanks common PHI-bearing fields and remaps UIDs.

This is useful for development, but it is not a full replacement for a validated
DICOM anonymizer.

### `preanonymized`

Copies already-anonymized DICOM input into the output folder and runs labeling.

Use this when RSNA Anonymizer or another validated tool has already processed
the DICOMs.

### `rsna`

Calls RSNA Anonymizer in headless mode with an existing project config:

```bash
python -m pipeline_anonymize_label.batch_pipeline \
  --input pipeline_anonymize_label/input \
  --output pipeline_anonymize_label/output \
  --anonymizer-mode rsna \
  --rsna-config path/to/ProjectModel.json
```

The RSNA project config controls where anonymized files are written. For this
mode, configure RSNA Anonymizer to write into the run's `anonymized_dicom/`
folder, or use `preanonymized` mode afterward to label an already-anonymized
folder.

## Privacy

Do not commit raw DICOMs, anonymized DICOMs, model caches, or generated outputs.
For real sensitive data, prefer RSNA Anonymizer or another validated
de-identification tool before running MedGemma labeling.

## Previous Notes

The prior README content, including demo-app notes, is preserved in
`README_reference.md` for future reference.
