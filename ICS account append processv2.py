import os
import shutil
import argparse
import pandas as pd
import tempfile
from collections import Counter
from datetime import datetime

# ==========================
# CONFIGURATION
# ==========================
BASE_DIR = r"C:\Users\james.gilmore\OneDrive - Computer Services, Inc\Desktop\Products\ICS"
LOG_DIR = os.path.join(BASE_DIR, "log")
TRENDS_DIR = os.path.join(BASE_DIR, "trends")
LOG_FILE = os.path.join(LOG_DIR, "automation_log.txt")
SUMMARY_FILE = os.path.join(TRENDS_DIR, "merge_summary.csv")
INCOMING_DIR = os.path.join(BASE_DIR, "incoming")

# --------------------------
# Detection & analysis config
# --------------------------
# Keywords used to detect REF and DM files (case-insensitive substrings)
FILE_KEYWORDS = {
    "REF": ["referral", "ics_detailed referral", "ref"],
    "DM": ["direct mail", "directmail", "new accounts opened", "direct mail new accounts opened"]
}
# How many header rows to probe when trying to auto-detect the header
HEADER_DETECTION_ROWS = 10
# Threshold for anomaly detection (fractional change) e.g. 0.5 == 50%
ANOMALY_THRESHOLD = 0.5

# Global dry-run flag (set by CLI)
DRY_RUN = False
# Control whether to write CSV copy of merged files
NO_CSV_COPY = False
# Control whether to overwrite existing merged files (default True)
OVERWRITE_MERGED = True

def ensure_folders():
    """Create important folders (only run during non-dry runs)."""
    for d in (BASE_DIR, LOG_DIR, TRENDS_DIR):
        if not os.path.exists(d):
            os.makedirs(d)

# ==========================
# UTILITY FUNCTIONS
# ==========================
def write_log(message):
    """Append messages to log file and print to console."""
    prefix = "[DRY-RUN] " if DRY_RUN else ""
    # In dry-run mode, only print actions to console (do not write files)
    if DRY_RUN:
        print(prefix + message)
    else:
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"{datetime.now()} - {message}\n")
        print(message)

def create_folder(path):
    """Create folder if it doesn't exist."""
    if not os.path.exists(path):
        os.makedirs(path)

def read_column(file_path, col_letter, header_row):
    """
    Reads a specific column from Excel or CSV using the correct header row.
    header_row: 1-based index of the header row in the file.
    Returns a DataFrame with one column.
    """
    try:
        col_index = ord(col_letter.upper()) - ord('A')  # Convert letter to index
        if file_path.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file_path, header=header_row-1, dtype=str)
        elif file_path.endswith(".csv"):
            # Try to be tolerant when parsing malformed CSVs: read as strings and skip bad lines
            try:
                df = pd.read_csv(file_path, header=header_row-1, dtype=str, engine='python', on_bad_lines='skip')
            except Exception:
                # Try a conservative pre-clean of the CSV to fix common tokenizing issues
                temp_path = preclean_csv(file_path)
                try:
                    df = pd.read_csv(temp_path, header=header_row-1, dtype=str)
                except Exception as e:
                    write_log(f"Failed to parse CSV even after pre-clean: {file_path}: {e}")
                    df = pd.DataFrame()
                finally:
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
        else:
            write_log(f"Unsupported file format: {file_path}")
            return pd.DataFrame()

        # Return only the desired column (guard against files with fewer columns)
        if df is None or df.empty:
            return pd.DataFrame()
        if col_index >= df.shape[1]:
            # column doesn't exist in this header attempt
            return pd.DataFrame()
        return df.iloc[:, [col_index]]
    except PermissionError:
        write_log(f"Permission denied: {file_path}. File may be open or locked.")
        return pd.DataFrame()
    except Exception as e:
        write_log(f"Error reading {file_path}: {e}")
        return pd.DataFrame()


def read_data_with_heuristics(file_path):
    """Try multiple header rows and find the best column that looks like account hashes/IDs.

    Returns a DataFrame with a single detected column or an empty DataFrame if detection fails.
    """
    try:
        for header_row in range(1, HEADER_DETECTION_ROWS + 1):
            try:
                if file_path.endswith((".xlsx", ".xls")):
                    df = pd.read_excel(file_path, header=header_row - 1, dtype=str)
                elif file_path.endswith(".csv"):
                    try:
                        df = pd.read_csv(file_path, header=header_row - 1, dtype=str, engine='python', on_bad_lines='skip')
                    except Exception:
                        temp_path = preclean_csv(file_path)
                        try:
                            df = pd.read_csv(temp_path, header=header_row - 1, dtype=str)
                        except Exception as e:
                            write_log(f"Failed to parse CSV even after pre-clean: {file_path}: {e}")
                            df = pd.DataFrame()
                        finally:
                            try:
                                os.remove(temp_path)
                            except Exception:
                                pass
                else:
                    continue
            except Exception:
                continue

            if df.empty:
                continue

            # Prefer columns with header names suggesting account fields
            for col in df.columns:
                cname = str(col).strip().lower()
                if any(k in cname for k in ("acct", "account", "hash", "id", "acct number")):
                    series = df[col].dropna().astype(str)
                    if not series.empty:
                        return series.to_frame()

            # Fallback: pick first non-empty column whose values look like IDs/hashes
            for col in df.columns:
                series = df[col].dropna().astype(str)
                if series.empty:
                    continue
                # simple heuristic: values of reasonable length and alphanumeric
                sample = series.head(10).tolist()
                if any(len(s) >= 6 for s in sample):
                    return series.to_frame()

        return pd.DataFrame()
    except PermissionError:
        write_log(f"Permission denied: {file_path}. File may be open or locked.")
        return pd.DataFrame()
    except Exception as e:
        write_log(f"Error auto-detecting column in {file_path}: {e}")
        return pd.DataFrame()


def detect_best_file(files, folder, kind):
    """Select the best candidate file from a list for a given kind ('REF' or 'DM').

    Returns (filename_or_None, reason_str).
    """
    kws = FILE_KEYWORDS.get(kind, [])
    matches = []
    for f in files:
        low = f.lower()
        if any(kw in low for kw in kws):
            matches.append(f)

    if not matches:
        return None, "No keyword match"

    # Prefer files that produce non-empty detected column
    non_empty = []
    for f in matches:
        path = os.path.join(folder, f)
        dfcol = read_data_with_heuristics(path)
        if not dfcol.empty:
            non_empty.append((f, os.path.getmtime(path)))

    if non_empty:
        # choose most recent non-empty
        chosen = max(non_empty, key=lambda x: x[1])[0]
        return chosen, "keyword match (non-empty), chose newest"

    # If none non-empty, choose newest match and log that read was empty
    newest = max(matches, key=lambda x: os.path.getmtime(os.path.join(folder, x)))
    return newest, "keyword match (all empty), chose newest"

# ==========================
# STEP 1: ORGANIZE FILES
# ==========================
def organize_files():
    """Organize files into folders by first 4 digits of filename (skip non-numeric prefixes)."""
    for filename in os.listdir(BASE_DIR):
        file_path = os.path.join(BASE_DIR, filename)
        # Skip directories and important files/folders
        if os.path.isdir(file_path):
            continue
        if filename in (os.path.basename(LOG_FILE), os.path.basename(SUMMARY_FILE)):
            continue
        # Only move files that start with 4 numeric characters (client id)
        prefix = filename[:4]
        if prefix.isdigit():
            client_id = prefix
            target_folder = os.path.join(BASE_DIR, client_id)
            create_folder(target_folder)
            try:
                if DRY_RUN:
                    write_log(f"DRY-RUN: Would move {filename} to {target_folder}")
                else:
                    shutil.move(file_path, os.path.join(target_folder, filename))
                    write_log(f"Moved {filename} to {target_folder}")
            except Exception as e:
                write_log(f"Failed to move {filename}: {e}")
        else:
            # Route any other files into an incoming folder so the BASE_DIR stays clean
            incoming = INCOMING_DIR
            try:
                if DRY_RUN:
                    write_log(f"DRY-RUN: Would move {filename} to {incoming}")
                else:
                    create_folder(incoming)
                    shutil.move(file_path, os.path.join(incoming, filename))
                    write_log(f"Moved {filename} to {incoming}")
            except Exception as e:
                write_log(f"Failed to move {filename} to incoming: {e}")

# ==========================
# STEP 2: MERGE FILES AND LOG COUNTS
# ==========================
def update_summary(new_rows):
    """
    Append new summary rows (list of [Month, Client ID, REF Rows, DM Rows, Total Merged])
    to SUMMARY_FILE in TRENDS_DIR and compute growth metrics.
    """
    # Ensure trends dir exists
    create_folder(TRENDS_DIR)

    cols = ["Month", "Client ID", "REF Rows", "DM Rows", "Total Merged", "REF Status", "DM Status"]
    new_df = pd.DataFrame(new_rows, columns=cols)

    if os.path.exists(SUMMARY_FILE):
        old_df = pd.read_csv(SUMMARY_FILE)
        combined_df = pd.concat([old_df, new_df], ignore_index=True)
    else:
        combined_df = new_df

    combined_df.sort_values(by=["Client ID", "Month"], inplace=True)

    # Parse Month into a Period for time-aware calculations
    def parse_month(m):
        try:
            # expected format YYYY.MM
            return pd.Period(m.replace('.', '-'), freq='M')
        except Exception:
            try:
                return pd.to_datetime(m).to_period('M')
            except Exception:
                return pd.NaT

    combined_df['MonthPeriod'] = combined_df['Month'].apply(parse_month)

    # Numeric month-over-month pct changes (keep numeric columns for analysis)
    combined_df['REF_pct_change'] = combined_df.groupby('Client ID')['REF Rows'].pct_change()
    combined_df['DM_pct_change'] = combined_df.groupby('Client ID')['DM Rows'].pct_change()
    combined_df['Total_pct_change'] = combined_df.groupby('Client ID')['Total Merged'].pct_change()

    # Absolute delta vs previous month and 3-month rolling average
    combined_df['Total_delta'] = combined_df.groupby('Client ID')['Total Merged'].diff()
    combined_df['Total_3mo_avg'] = combined_df.groupby('Client ID')['Total Merged'].rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)

    # Apply per-group cumulative and streak calculations
    def enrich_group(sub):
        sub = sub.copy()
        # month numeric for simple arithmetic
        sub['month_num'] = sub['MonthPeriod'].apply(lambda p: (p.year * 12 + p.month) if pd.notnull(p) else None)

        # months with data (cumulative count of months with Total > 0)
        sub['months_with_data'] = (sub['Total Merged'] > 0).cumsum()

        # months since last present
        last_present = None
        months_since = []
        current_missing_streak = []
        longest_missing = []
        current_streak = 0
        for mn, val in zip(sub['month_num'], sub['Total Merged']):
            if val > 0:
                months_since.append(0)
                last_present = mn
                current_streak = 0
            else:
                if last_present is None or mn is None:
                    months_since.append(None)
                else:
                    months_since.append(mn - last_present)
                current_streak += 1
            current_missing_streak.append(current_streak)
            longest_missing.append(max(longest_missing[-1] if longest_missing else 0, current_streak))

        sub['months_since_last_present'] = months_since
        sub['current_missing_streak'] = current_missing_streak
        sub['longest_missing_streak'] = longest_missing

        # YoY percent (12-month shift)
        sub['Total_YoY_pct'] = sub['Total Merged'].pct_change(periods=12)

        # Anomaly flag if change greater than threshold
        prev = sub['Total Merged'].shift(1)
        delta = sub['Total_delta']
        sub['Total_anomaly'] = False
        mask = (prev > 0) & (delta.abs() / prev > ANOMALY_THRESHOLD)
        sub.loc[mask, 'Total_anomaly'] = True

        return sub

    combined_df = combined_df.groupby('Client ID', group_keys=False).apply(enrich_group)

    # Keep human-friendly percent strings for backward compatibility
    combined_df['REF Δ%'] = combined_df['REF_pct_change'].fillna(0).apply(lambda x: f"{x*100:.1f}%")
    combined_df['DM Δ%'] = combined_df['DM_pct_change'].fillna(0).apply(lambda x: f"{x*100:.1f}%")
    combined_df['Total Δ%'] = combined_df['Total_pct_change'].fillna(0).apply(lambda x: f"{x*100:.1f}%")

    def trend(val):
        if val > 0: return "↑"
        elif val < 0: return "↓"
        else: return "→"
    combined_df['Trend'] = combined_df['Total_delta'].fillna(0).apply(trend)

    if DRY_RUN:
        write_log(f"DRY-RUN: Would update comprehensive summary at {SUMMARY_FILE}")
    else:
        combined_df.to_csv(SUMMARY_FILE, index=False)
        write_log(f"Comprehensive summary updated at {SUMMARY_FILE}")

def merge_client_files():
    """Merge REF and DM files for each client folder and log row counts."""
    summary_rows = []  # Collect summary rows for update_summary
    month_stamp = datetime.now().strftime("%Y.%m")

    for client_id in os.listdir(BASE_DIR):
        client_folder = os.path.join(BASE_DIR, client_id)
        if not os.path.isdir(client_folder):
            continue

        # Only process actual client folders named with exactly 4 digits
        if not (client_id.isdigit() and len(client_id) == 4):
            write_log(f"Skipping non-client folder: {client_id}")
            continue

        files = os.listdir(client_folder)
        ref_file, ref_reason = detect_best_file(files, client_folder, 'REF')
        dm_file, dm_reason = detect_best_file(files, client_folder, 'DM')
        if ref_file:
            write_log(f"{client_id}: REF selected: {ref_file} ({ref_reason})")
        if dm_file:
            write_log(f"{client_id}: DM selected: {dm_file} ({dm_reason})")

        merged_data = []
        ref_count = 0
        dm_count = 0
        ref_status = "Missing"
        dm_status = "Missing"

        # Process REF file
        if ref_file:
            ref_status = "Present"
            ref_path = os.path.join(client_folder, ref_file)
            # For REF files prefer column G with header row 1 (legacy format). Fall back to heuristics if empty.
            ref_df = read_column(ref_path, "G", 1)
            if ref_df.empty:
                ref_df = read_data_with_heuristics(ref_path)
            if not ref_df.empty:
                # Count non-null values in the detected column
                ref_count = ref_df.iloc[:, 0].dropna().shape[0]
                for val in ref_df.iloc[:, 0].dropna():
                    merged_data.append([val, "REF"])
            else:
                write_log(f"{client_id}: REF file read produced no detectable column")
        else:
            write_log(f"{client_id}: REF file missing")

        # Process DM file
        if dm_file:
            dm_status = "Present"
            dm_path = os.path.join(client_folder, dm_file)
            # For DM files prefer column I with header row 10 (legacy format). Fall back to heuristics if empty.
            dm_df = read_column(dm_path, "I", 10)
            if dm_df.empty:
                dm_df = read_data_with_heuristics(dm_path)
            if not dm_df.empty:
                dm_count = dm_df.iloc[:, 0].dropna().shape[0]
                for val in dm_df.iloc[:, 0].dropna():
                    merged_data.append([val, "DM"])
            else:
                write_log(f"{client_id}: DM file read produced no detectable column")
        else:
            write_log(f"{client_id}: DM file missing")

        # Log counts for this client
        write_log(f"{client_id}: REF rows={ref_count}, DM rows={dm_count}, Total merged={len(merged_data)}")
        summary_rows.append([month_stamp, client_id, ref_count, dm_count, len(merged_data), ref_status, dm_status])

        # Create merged file if data exists
        if merged_data:
            date_stamp = month_stamp
            if dm_file:
                # try to extract date-like part from dm filename parts
                parts = dm_file.split("-")
                for p in parts:
                    if "." in p and len(p) == 7:
                        date_stamp = p
                        break

            # Define output file and dataframe regardless of DM presence
            output_file = os.path.join(client_folder, f"{client_id}-ICS Accounts-All-{date_stamp}.xlsx")
            merged_df = pd.DataFrame(merged_data, columns=["Acct Hash", "Source"])
            # Ensure Acct Hash values are strings (do NOT prefix with Excel apostrophe; preserve strings via dtype)
            merged_df['Acct Hash'] = merged_df['Acct Hash'].astype(str)
            # Standardize: if output exists, remove or create unique name depending on OVERWRITE_MERGED
            if os.path.exists(output_file):
                if OVERWRITE_MERGED:
                    if DRY_RUN:
                        write_log(f"DRY-RUN: Would overwrite existing merged file {output_file}")
                    else:
                        try:
                            os.remove(output_file)
                        except Exception as e:
                            write_log(f"Failed to remove existing merged file {output_file}: {e}")
                        # also remove csv counterpart if exists
                        csv_out_existing = os.path.splitext(output_file)[0] + '.csv'
                        if os.path.exists(csv_out_existing):
                            try:
                                os.remove(csv_out_existing)
                            except Exception:
                                pass
                else:
                    # create a unique filename to avoid silent overwrite
                    base, ext = os.path.splitext(output_file)
                    i = 1
                    while os.path.exists(f"{base}_v{i}{ext}"):
                        i += 1
                    output_file = f"{base}_v{i}{ext}"
            if DRY_RUN:
                write_log(f"{client_id}: DRY-RUN: Would create merged file {output_file} with {len(merged_data)} rows")
            else:
                try:
                    merged_df.to_excel(output_file, index=False)
                except Exception as e:
                    write_log(f"{client_id}: Failed to write merged file {output_file}: {e}")
                # Optionally save a CSV copy (strings preserved) for reliability
                if not NO_CSV_COPY:
                    try:
                        csv_out = os.path.splitext(output_file)[0] + '.csv'
                        merged_df.to_csv(csv_out, index=False)
                    except Exception as e:
                        write_log(f"{client_id}: Failed to write CSV copy: {e}")
                write_log(f"{client_id}: Created merged file with {len(merged_data)} rows")

            # Move originals to processed folder (move whichever exist)
            processed_folder = os.path.join(client_folder, "processed")
            if DRY_RUN:
                for f in [ref_file, dm_file]:
                    if f:
                        write_log(f"{client_id}: DRY-RUN: Would move {f} to {processed_folder}")
            else:
                create_folder(processed_folder)
                for f in [ref_file, dm_file]:
                    if f:
                        try:
                            shutil.move(os.path.join(client_folder, f), os.path.join(processed_folder, f))
                        except Exception as e:
                            write_log(f"{client_id}: Failed to move {f} to processed: {e}")
        else:
            write_log(f"{client_id}: No data to merge")

    # Update comprehensive trends summary (in TRENDS_DIR)
    update_summary(summary_rows)
    # Also write a per-run summary for this run (does NOT overwrite comprehensive summary)
    run_file = os.path.join(TRENDS_DIR, f"merge_summary_run_{month_stamp}.csv")
    summary_df = pd.DataFrame([[r[1], r[2], r[3], r[4], r[5], r[6]] for r in summary_rows],
                              columns=["Client ID", "REF Rows", "DM Rows", "Total Merged", "REF Status", "DM Status"])
    if DRY_RUN:
        write_log(f"DRY-RUN: Would export per-run summary to {run_file}")
    else:
        summary_df.to_csv(run_file, index=False)
        write_log(f"Per-run summary exported to {run_file}")


def find_odd_file(client_folder):
    """Locate the ODD file in a client folder. Return filename or None."""
    try:
        for f in os.listdir(client_folder):
            low = f.lower()
            # be tolerant: accept any filename containing 'odd' but ignore backup-like files
            if 'odd' in low and not low.endswith(('.bak', '.old')):
                return f
        return None
    except Exception as e:
        write_log(f"Failed to list {client_folder}: {e}")
        return None


def read_full_with_heuristics(file_path):
    """Read ODD file with Acct Number preserved as string."""
    try:
        if file_path.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file_path, header=0, dtype={"Acct Number": str})
        elif file_path.endswith(".csv"):
            df = pd.read_csv(file_path, header=0, dtype={"Acct Number": str})
        else:
            write_log(f"Unsupported file format: {file_path}")
            return None, None

        if "Acct Number" not in df.columns:
            write_log(f"'Acct Number' column not found in {file_path}")
            return None, None

        return df, "Acct Number"
    except Exception as e:
        write_log(f"Error reading {file_path}: {e}")
        return None, None

def normalize_acct(val):
    """
    Normalize account/hash strings for reliable matching.
    - Keep original casing and leading zeros.
    - Remove only non-alphanumeric characters (except keep digits and letters as-is).
    """
    try:
        if val is None:
            return ""
        s = str(val).strip()  # Trim whitespace only
        # Remove non-alphanumeric characters but keep digits and letters as-is
        import re
        s = re.sub(r'[^A-Za-z0-9]', '', s)
        return s
    except Exception:
        return str(val).strip()



def preclean_csv(file_path):
    """Conservative pre-clean for malformed CSVs.

    Strategy:
    - Read file lines and count commas per non-empty line.
    - Determine the most common number of fields (mode of commas+1).
    - For lines with more fields than expected, collapse extra fields into the last field.
    - Write cleaned output to a temp file and return its path.
    This is lossy but often fixes tokenization caused by stray/unbalanced commas.
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception:
        # fallback: try with latin-1
        with open(file_path, 'r', encoding='latin-1', errors='replace') as f:
            lines = f.readlines()

    # Compute commas per non-empty line
    comma_counts = [line.count(',') for line in lines if line.strip()]
    if not comma_counts:
        # empty or unreadable; return original path
        return file_path

    # expected fields = mode(commas) + 1
    most_common = Counter(comma_counts).most_common(1)[0][0]
    expected_fields = most_common + 1

    temp_fd, temp_path = tempfile.mkstemp(suffix='.csv')
    try:
        with os.fdopen(temp_fd, 'w', encoding='utf-8', errors='replace') as out:
            for line in lines:
                if not line.strip():
                    out.write('\n')
                    continue
                parts = line.rstrip('\n').split(',')
                if len(parts) <= expected_fields:
                    out.write(line)
                else:
                    # collapse extra parts into last field
                    new_parts = parts[:expected_fields-1] + [','.join(parts[expected_fields-1:])]
                    out.write(','.join(new_parts) + '\n')
    except Exception:
        try:
            os.remove(temp_path)
        except Exception:
            pass
        return file_path

    write_log(f"Pre-cleaned CSV {file_path} -> {temp_path} (expected fields={expected_fields})")
    return temp_path




def match_and_annotate(client_id, month, odd_path, merged_path):
    """
    Match ICS accounts to ODD file and append ICS Acct and ICS Source columns.
    Preserves leading zeros and casing.
    """
    summary = {"client": client_id, "month": month, "matched": 0, "orphans": 0, "issues": []}

    # Read ODD file
    odd_df, odd_col = read_full_with_heuristics(odd_path)
    if odd_df is None or odd_col is None:
        summary['issues'].append('Failed to detect account column in ODD')
        write_log(f"{client_id} {month}: Failed to read ODD or detect account column")
        return summary


    # Read merged ICS file
    try:
        if merged_path.endswith(".xlsx"):
            mdf = pd.read_excel(merged_path, dtype=str)
        elif merged_path.endswith(".csv"):
            mdf = pd.read_csv(merged_path, dtype=str)
        else:
            raise ValueError(f"Unsupported file format: {merged_path}")
    except Exception as e:
        summary['issues'].append(f'Failed to read merged: {e}')
        write_log(f"{client_id} {month}: Failed to read merged {merged_path}: {e}")
        return summary


    if 'Acct Hash' not in mdf.columns or 'Source' not in mdf.columns:
        summary['issues'].append('Merged file missing required columns')
        write_log(f"{client_id} {month}: merged file missing 'Acct Hash' or 'Source'")
        return summary

    # Build lookup dictionary
    from collections import defaultdict
    lookup = defaultdict(list)
    for acct, src in zip(mdf['Acct Hash'], mdf['Source']):
        lookup[normalize_acct(acct)].append(src)

    # Normalize ODD accounts
    odd_vals = odd_df[odd_col].astype(str).str.strip().apply(normalize_acct)

    ic_acct_col, ic_source_col, orphans = [], [], []
    for raw_val, norm_val in zip(odd_df[odd_col], odd_vals):
        if norm_val in lookup:
            ic_acct_col.append(raw_val)
            ic_source_col.append(", ".join(lookup[norm_val]))
        else:
            ic_acct_col.append('')
            ic_source_col.append('')
            orphans.append(raw_val)

    # Append columns
    odd_df['ICS Acct'] = ic_acct_col
    odd_df['ICS Source'] = ic_source_col

    summary['matched'] = sum(1 for s in ic_source_col if s)
    summary['orphans'] = len(orphans)

    # Save output
    out_dir = os.path.dirname(odd_path)
    out_name = os.path.splitext(os.path.basename(odd_path))[0] + '_with_ICS_Accts.xlsx'
    out_path = os.path.join(out_dir, out_name)

    try:
        odd_df.to_excel(out_path, index=False)
        write_log(f"Wrote matched ODD for {client_id} {month} to {out_path}")
    except Exception as e:
        summary['issues'].append(f'Failed to write matched ODD: {e}')
        write_log(f"{client_id} {month}: Failed to write matched ODD to {out_path}: {e}")

    return summary





def match_ics_to_ars(ars_base_dir, month=None):
    """
    Walk ARS month folders and match ICS merged accounts into ODD files.
    Patch:
    - Allows matching without REF/DM merge step.
    - Improves ICS merged file detection (case-insensitive, flexible).
    - Adds diagnostics for skipped clients.
    """
    if not os.path.exists(ars_base_dir):
        write_log(f"ARS base dir not found: {ars_base_dir}")
        return

    months = [m for m in os.listdir(ars_base_dir) if os.path.isdir(os.path.join(ars_base_dir, m))]
    if month:
        months = [m for m in months if m == month]

    for m in sorted(months):
        month_folder = os.path.join(ars_base_dir, m)
        write_log(f"Processing ARS month folder: {m}")
        month_log = os.path.join(LOG_DIR, f"ics_to_ars_match_{m}.txt")
        results, skipped_missing, processed = [], 0, 0

        for client_id in os.listdir(month_folder):
            client_folder = os.path.join(month_folder, client_id)
            if not os.path.isdir(client_folder):
                continue
            if not (client_id.isdigit() and len(client_id) == 4):
                write_log(f"Skipping non-client folder in ARS month: {client_id}")
                continue

            odd_file = find_odd_file(client_folder)
            if not odd_file:
                write_log(f"{m} {client_id}: ODD file not found")
                continue

            odd_path = os.path.join(client_folder, odd_file)

            # Locate ICS merged file
            client_ics_folder = os.path.join(BASE_DIR, client_id)
            merged_path = None
            candidates = []

            if os.path.isdir(client_ics_folder):
                month_variants = {m, m.replace('.', '-'), m.replace('-', '.')}

                # Flexible filename detection
                for fname in os.listdir(client_ics_folder):
                    if f"{client_id}-ics accounts-all" in fname.lower():
                        if any(mv in fname for mv in month_variants):
                            candidates.append(os.path.join(client_ics_folder, fname))

                # Fallback: any ICS Accounts-All file for client
                if not candidates:
                    for fname in os.listdir(client_ics_folder):
                        if f"{client_id}-ics accounts-all" in fname.lower():
                            candidates.append(os.path.join(client_ics_folder, fname))

                if candidates:
                    merged_path = max(candidates, key=lambda p: os.path.getmtime(p))

            # If merged file not found, log and skip
            if not merged_path or not os.path.exists(merged_path):
                write_log(f"{m} {client_id}: Merged ICS file not found. Checked {client_ics_folder}; candidates={len(candidates)}")
                skipped_missing += 1
                continue

            # Perform matching
            try:
                res = match_and_annotate(client_id, m, odd_path, merged_path)
                results.append(res)
                processed += 1
                line = f"{client_id}: matched={res.get('matched',0)} orphans={res.get('orphans',0)} issues={res.get('issues',[])}"
                with open(month_log, 'a', encoding='utf-8') as f:
                    f.write(line + '\n')
            except Exception as e:
                write_log(f"{m} {client_id}: Error during matching: {e}")

        # Summary for this month
        write_log(f"{m}: Processed {processed} clients; skipped {skipped_missing} clients with missing ICS files")
        write_log(f"Completed ARS matching for {m}. Results written to {month_log}")

# ==========================
# MAIN EXECUTION
# ==========================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge ICS REF and DM files per client and track trends.")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Run without writing or moving files; actions are printed to console.")
    parser.add_argument("--base-dir", "-b", help="Override the BASE_DIR for testing (e.g., a temporary folder).")
    parser.add_argument("--match-ars", action="store_true", help="Match ICS merged files into ARS ODD folders")
    parser.add_argument("--ars-dir", help="Base ARS directory with monthly YYYY.MM folders")
    parser.add_argument("--match-month", help="Limit matching to specific month YYYY.MM (optional)")
    parser.add_argument("--no-csv-copy", action="store_true", help="Do not write CSV copies of merged All files.")
    parser.add_argument("--no-overwrite", action="store_true", help="Do not overwrite existing merged All files; create unique versioned filename instead.")
    args = parser.parse_args()

    # Set DRY_RUN based on CLI
    DRY_RUN = bool(args.dry_run)

    # set csv copy and overwrite behavior
    NO_CSV_COPY = bool(getattr(args, 'no_csv_copy', False))
    OVERWRITE_MERGED = not bool(getattr(args, 'no_overwrite', False))

    # Optionally override BASE_DIR and recompute derived paths
    if args.base_dir:
        BASE_DIR = args.base_dir
        LOG_DIR = os.path.join(BASE_DIR, "log")
        TRENDS_DIR = os.path.join(BASE_DIR, "trends")
        LOG_FILE = os.path.join(LOG_DIR, "automation_log.txt")
        SUMMARY_FILE = os.path.join(TRENDS_DIR, "merge_summary.csv")

    if DRY_RUN:
        write_log("=== DRY-RUN: Automation Started (no files will be moved or written) ===")
    else:
        # Ensure important folders exist (only when not a dry-run)
        ensure_folders()
        write_log("=== Automation Started ===")

    organize_files()
    merge_client_files()

    # Optionally run ARS matching
    if args.match_ars:
        if not args.ars_dir:
            write_log("ARS matching requested but --ars-dir not provided. Skipping.")
        else:
            # Default to current month if not provided; allow user to override to run historical months
            if not args.match_month:
                args.match_month = datetime.now().strftime("%Y.%m")
                write_log(f"No --match-month provided; defaulting to current month {args.match_month}")
            match_ics_to_ars(args.ars_dir, month=args.match_month)