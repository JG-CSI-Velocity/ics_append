# ICS Append -- Usage Guide

## What This Tool Does

`ics_append` prepares ICS (Insured Cash Sweep) data for the downstream `ics_analysis` pipeline. It replaces the monolithic `ICS account append processv2.py` script.

**Pipeline flow:**

```
ICS Portal (REF/DM exports)
        |
        v
  ics_append          <-- this tool
  (organize, merge, match)
        |
        v
  Annotated ODD files
  (ICS Account: Yes/No, ICS Source: REF/DM)
        |
        v
  ics_analysis         <-- downstream analytics
  (33 analyses, charts, Excel, PPTX)
```

---

## Prerequisites

1. Python 3.11+
2. Install the package:

```bash
cd ~/Desktop/ics_append
pip install -e .
```

Or install dependencies directly:

```bash
pip install -r requirements.txt
```

---

## After Running the ARS Script

Once you have run your monthly ARS prework (`run_prework.py`) and have the ODD files ready, follow these steps.

### Step 1: Gather Your Files

You need two sets of files:

**ICS files** (from the ICS portal):
- REF file: `{clientID}-ICS_Detailed Referral-{YYYY.MM}.xlsx`
- DM file: `{clientID}-Direct Mail New Accounts-{YYYY.MM}.xlsx`

**ARS files** (from the ARS run):
- ODD file: `{clientID}_oddd.xlsx` (inside the ARS month folder)

### Step 2: Set Up Your Directories

**ICS base directory** -- where you drop REF/DM files:

```
~/Desktop/Products/ICS/
  1453-ICS_Detailed Referral-2026.01.xlsx
  1453-Direct Mail New Accounts-2026.01.xlsx
  1217-ICS_Detailed Referral-2026.01.xlsx
  notes.txt
```

**ARS directory** -- where the ARS script wrote ODD files:

```
~/Desktop/ARS/
  2026.01/
    1453/
      1453_oddd.xlsx
    1217/
      1217_oddd.xlsx
```

### Step 3: Run the Pipeline

**Full pipeline (recommended):**

```bash
python -m ics_append \
  --base-dir ~/Desktop/Products/ICS \
  --ars-dir ~/Desktop/ARS \
  --match-month 2026.01 \
  run-all
```

This runs all three steps in sequence: organize, merge, match.

**Or run steps individually:**

```bash
# Step 1: Sort loose files into client folders
python -m ics_append --base-dir ~/Desktop/Products/ICS organize

# Step 2: Merge REF + DM into combined ICS list per client
python -m ics_append --base-dir ~/Desktop/Products/ICS -m 2026.01 merge

# Step 3: Match ICS accounts into ODD files
python -m ics_append \
  --base-dir ~/Desktop/Products/ICS \
  --ars-dir ~/Desktop/ARS \
  -m 2026.01 \
  match
```

### Step 4: Check the Output

After the pipeline runs:

**ICS directory** (merged files created):

```
~/Desktop/Products/ICS/
  1453/
    1453-ICS_Detailed Referral-2026.01.xlsx
    1453-Direct Mail New Accounts-2026.01.xlsx
    1453-ICS Accounts-All-2026.01.xlsx          <-- merged
  1217/
    ...
  trends/
    merge_summary.csv                            <-- month-over-month tracking
```

**ARS directory** (annotated ODD files created):

```
~/Desktop/ARS/
  2026.01/
    1453/
      1453_oddd.xlsx                             <-- original
      1453_oddd_annotated.xlsx                   <-- annotated with ICS columns
      1453_match_metadata.json                   <-- match stats
    1217/
      ...
```

### Step 5: Feed Into ics_analysis

The annotated ODD file (`*_annotated.xlsx`) is ready for `ics_analysis`:

```bash
python -m ics_analysis ~/Desktop/ARS/2026.01/1453/1453_oddd_annotated.xlsx \
  --client-id 1453 \
  --client-name "Sample Credit Union"
```

The annotated file contains two new columns:
- `ICS Account` -- "Yes" or "No"
- `ICS Source` -- "REF", "DM", "Both", or blank

---

## CLI Reference

```
python -m ics_append [OPTIONS] COMMAND
```

### Global Options (before the command)

| Flag | Short | Description |
|------|-------|-------------|
| `--base-dir PATH` | `-d` | Base ICS directory with client files |
| `--ars-dir PATH` | | ARS directory with monthly ODD folders |
| `--match-month YYYY.MM` | `-m` | Target month (defaults to current) |
| `--dry-run` | `-n` | Preview without writing files |
| `--config PATH` | `-c` | Path to config.yaml |
| `--verbose` | `-v` | Debug logging |

### Commands

| Command | Description |
|---------|-------------|
| `organize` | Sort loose files into client folders by ID |
| `merge` | Merge REF + DM files into combined ICS list |
| `match` | Annotate ODD files with ICS Account Yes/No |
| `run-all` | Execute all steps in sequence |

### Command-Specific Options

```bash
# Merge or match a single client
python -m ics_append --base-dir /path merge --client 1453
python -m ics_append --base-dir /path --ars-dir /path match --client 1453
```

---

## Configuration

For repeated use, create a `config.yaml` (copy from `config.example.yaml`):

```yaml
base_dir: "~/Desktop/Products/ICS"
ars_dir: "~/Desktop/ARS"
overwrite: true
csv_copy: false
match_rate_warn_threshold: 0.5

# Per-client column overrides (when auto-detection doesn't work)
clients:
  "1453":
    ref_column: "G"
    ref_header_row: 1
    dm_column: "I"
    dm_header_row: 10
```

With a config file, the command simplifies to:

```bash
python -m ics_append -m 2026.01 run-all
```

Priority order: CLI flags > environment variables > config.yaml > defaults.

---

## File Detection Rules

The tool auto-detects file types by keywords in the filename:

| File Type | Keywords (case-insensitive) |
|-----------|---------------------------|
| REF | `referral`, `ref`, `ics_detailed` |
| DM | `direct mail`, `directmail`, `new accounts` |
| ODD | `odd` in filename, `.xlsx`/`.xls`/`.csv` extension |

Files must start with a 4-digit client ID (e.g., `1453-`) to be sorted into client folders. Unrecognized files go to the `incoming/` folder.

---

## Per-Client Column Overrides

Most REF/DM files have the account hash in a detectable column. When auto-detection fails, specify the column in `config.yaml`:

```yaml
clients:
  "1453":
    ref_column: "G"        # Column letter (A, B, C...) or column name
    ref_header_row: 1      # 0-indexed row containing headers
    dm_column: "I"
    dm_header_row: 10
```

---

## Dry Run

Preview what will happen without writing any files:

```bash
python -m ics_append --base-dir ~/Desktop/Products/ICS --dry-run run-all
```

---

## Troubleshooting

**"No REF/DM file found"**
- Check that filenames contain one of the detection keywords
- Check that files start with the 4-digit client ID
- Add per-client config if the file naming is non-standard

**"No ODD file found"**
- Verify the ARS directory structure: `{ars_dir}/{YYYY.MM}/{clientID}/`
- Ensure the ODD file has "odd" somewhere in the filename

**"Low match rate warning"**
- Account hashes in REF/DM may be formatted differently than in the ODD
- Check for leading zeros, special characters, or encoding differences
- The default warning threshold is 50% -- adjust via `match_rate_warn_threshold`

**"Missing required column"**
- The ODD file needs an `Acct Number` column (or similar)
- If the column name differs, the tool tries heuristic detection
- Add a per-client column override in config.yaml if needed

---

## Python API (Jupyter/REPL)

```python
from ics_append import run_client

result = run_client(
    base_dir="~/Desktop/Products/ICS",
    ars_dir="~/Desktop/ARS",
    match_month="2026.01",
)

# Check results
for mr in result.merge_results:
    print(f"{mr.client_id}: REF={mr.ref_count} DM={mr.dm_count} Total={mr.total}")

for mm in result.match_metadata:
    print(mm.summary)
```

---

## Migrating from the Old Script

| Old script (`ICS account append processv2.py`) | New tool (`ics_append`) |
|---|---|
| `python "ICS account append processv2.py"` | `python -m ics_append --base-dir /path run-all` |
| `--dry-run` | `--dry-run` (same) |
| `--base-dir /path` | `--base-dir /path` (same) |
| `--match-ars --ars-dir /path` | `--ars-dir /path` (match runs automatically) |
| `--match-month 2026.01` | `-m 2026.01` (same) |
| `--no-csv-copy` | `csv_copy: false` in config (default) |
| `--no-overwrite` | `overwrite: false` in config |
| Hardcoded `BASE_DIR` in script | `base_dir` in config.yaml or `--base-dir` flag |
| `automation_log.txt` | Python logging to stderr (use `-v` for debug) |
| Outputs `"ICS Acct"` with raw hashes | Outputs `"ICS Account"` with Yes/No values |
