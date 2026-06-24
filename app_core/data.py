from pathlib import Path
import re
from tempfile import NamedTemporaryFile

import pandas as pd

ROLLUP_VENUES = {"Total US by Region"}


def parse_week_start(time_value, date_label):
    source = str(time_value or "")
    match = re.search(r"(\d{2})-(\d{2})-(\d{4})", source)
    if match:
        month, day, year = match.groups()
        return f"{year}-{month}-{day}"

    label = str(date_label or "")
    match = re.search(r"(\d{4}):\s*(\d{2})-(\d{2})", label)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"
    return None


COLUMN_RENAMES = {
    "Item": "item",
    "Venue": "venue",
    "Time": "time",
    "Week Start": "weekStart",
    "Week Ending": "weekEnding",
    "Dollar Sales": "dollarSales",
    "Dollar Sales Year Ago": "dollarSalesYearAgo",
    "Unit Sales": "unitSales",
    "Unit Sales Year Ago": "unitSalesYearAgo",
    "Warehouses Selling": "warehousesSelling",
    "Whse Selling": "warehousesSelling",
    "Avg. $ Sales Whse Selling": "avgSalesPerWarehouse",
    "Avg. $ Sales  Whse Selling": "avgSalesPerWarehouse",
    "Warehouses Selling Year Ago": "warehousesSellingYearAgo",
    "Number of Warehouses": "numberOfWarehouses",
    "Number of Warehouses Year Ago": "numberOfWarehousesYearAgo",
    "Inventory On Hand": "inventoryOnHand",
    "Common Names": "commonName",
    "Dates": "dateLabel",
}


NUMERIC_FIELDS = [
    "dollarSales",
    "dollarSalesYearAgo",
    "unitSales",
    "unitSalesYearAgo",
    "warehousesSelling",
    "warehousesSellingYearAgo",
    "numberOfWarehouses",
    "numberOfWarehousesYearAgo",
    "inventoryOnHand",
    "avgSalesPerWarehouse",
]


def clean_columns(df):
    df = df.copy()
    df.columns = [str(col).strip() for col in df.columns]
    return df.rename(columns=COLUMN_RENAMES)


def remove_rollup_rows(df):
    if "venue" not in df:
        return df
    return df[~df["venue"].isin(ROLLUP_VENUES)].copy()


def extract_item_code(value):
    text = str(value or "")
    if "ITEM " not in text:
        return None
    return text.split("ITEM ", 1)[1].split(" ", 1)[0]


def safe_parse_week(time_value, date_label):
    if pd.isna(time_value):
        time_value = ""
    if pd.isna(date_label):
        date_label = ""
    return parse_week_start(str(time_value), str(date_label))


def parse_week_ending_date(value):
    if pd.isna(value):
        return pd.NaT
    if not isinstance(value, str):
        return pd.to_datetime(value, errors="coerce")
    match = re.search(r"(\d{2})-(\d{2})-(\d{4})", value)
    if match:
        month, day, year = match.groups()
        return pd.Timestamp(year=int(year), month=int(month), day=int(day))
    return pd.to_datetime(value, errors="coerce")


def normalize_frame(df, source_name, source_sheet, source_order=0, source_modified=None):
    df = clean_columns(df).dropna(how="all")
    df = remove_rollup_rows(df)
    warnings = []

    for field in NUMERIC_FIELDS:
        if field in df:
            df[field] = pd.to_numeric(df[field], errors="coerce")
        else:
            df[field] = pd.NA

    if df["warehousesSelling"].isna().all() and "avgSalesPerWarehouse" in df:
        df["warehousesSelling"] = df["dollarSales"] / df["avgSalesPerWarehouse"].replace({0: pd.NA})

    if "dateLabel" not in df:
        df["dateLabel"] = pd.NA
    if "time" not in df:
        df["time"] = pd.NA
    if "weekEnding" in df:
        ending = df["weekEnding"].map(parse_week_ending_date)
        df["dateLabel"] = df["dateLabel"].fillna(ending.dt.strftime("%Y: %m-%d"))
        df["time"] = df["time"].fillna(ending.dt.strftime("1 week ending %m-%d-%Y"))
    if "item" not in df:
        df["item"] = source_sheet
    if "venue" not in df:
        df["venue"] = pd.NA
    else:
        df["venue"] = df["venue"].astype("string").str.strip()
    if "commonName" not in df:
        df["commonName"] = source_sheet
    if "isDemoWeek" not in df:
        df["isDemoWeek"] = False
    else:
        df["isDemoWeek"] = df["isDemoWeek"].fillna(False).astype(bool)

    df["item"] = df["item"].fillna(source_sheet)
    df["commonName"] = df["commonName"].fillna(source_sheet)
    # Strip leading item number (e.g. "1486657 OG RAINBOW CARROTS" → "OG RAINBOW CARROTS")
    df["commonName"] = df["commonName"].astype(str).str.replace(r"^\d+\s+", "", regex=True)

    if "weekStart" in df:
        direct_week_start = pd.to_datetime(df["weekStart"], errors="coerce", format="mixed")
    else:
        direct_week_start = pd.Series(pd.NaT, index=df.index)
    parsed_week_start = pd.to_datetime(
        [safe_parse_week(time_value, date_label) for time_value, date_label in zip(df["time"], df["dateLabel"])],
        errors="coerce",
    )
    df["weekStart"] = direct_week_start.fillna(pd.Series(parsed_week_start, index=df.index))
    if "weekEnding" in df:
        ending = df["weekEnding"].map(parse_week_ending_date)
        recovered_from_week_ending = direct_week_start.isna() & ending.notna() & df["venue"].notna()
        df["weekStart"] = df["weekStart"].fillna(ending - pd.Timedelta(days=6))
        if recovered_from_week_ending.any():
            warnings.append(f"{source_sheet}: Week Start was missing and was derived from Week Ending.")

    df = df[df["weekStart"].notna() & df["venue"].notna()].copy()
    df["year"] = df["weekStart"].dt.year.astype("Int64").astype(str).replace("<NA>", None)
    df["itemCode"] = df["item"].map(extract_item_code)
    df["sourceFile"] = source_name
    df["sourceSheet"] = source_sheet
    df["sourceOrder"] = source_order
    df["sourceModified"] = source_modified
    df.attrs["load_warnings"] = warnings
    return df


SUPPORTED_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}
REQUIRED_FIELDS = {"item", "venue", "time"}
BUSINESS_KEY = ["item", "venue", "time", "dateLabel", "commonName"]


def list_workbooks(folder, recursive=False):
    root = Path(folder).expanduser()
    if not root.exists() or not root.is_dir():
        return []
    pattern = "**/*" if recursive else "*"
    return sorted(
        path
        for path in root.glob(pattern)
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and not path.name.startswith("~$")
    )


def sheet_looks_compatible(path, sheet_name):
    sample = clean_columns(pd.read_excel(path, sheet_name=sheet_name, nrows=8))
    return len(REQUIRED_FIELDS & set(sample.columns)) >= 2 or "weekEnding" in sample.columns


def workbook_frames(path, preferred_sheet=None, source_order=0, source_name=None, source_modified=None):
    excel = pd.ExcelFile(path)
    sheet_names = excel.sheet_names
    if preferred_sheet and preferred_sheet in sheet_names:
        sheet_names = [preferred_sheet]

    frames = []
    errors = []
    warnings = []
    for sheet_index, sheet_name in enumerate(sheet_names):
        try:
            if preferred_sheet or sheet_looks_compatible(path, sheet_name):
                raw = pd.read_excel(path, sheet_name=sheet_name)
                frame = normalize_frame(
                    raw,
                    source_name or Path(path).name,
                    sheet_name,
                    source_order=source_order + sheet_index,
                    source_modified=source_modified,
                )
                warnings.extend(frame.attrs.get("load_warnings", []))
                if not frame.empty:
                    frame["productTab"] = sheet_name
                    frames.append(frame)
                elif sheet_name.strip().upper() != "SUMMARY":
                    warnings.append(f"{sheet_name}: no usable data rows loaded.")
        except Exception as exc:
            if preferred_sheet or sheet_name.strip().upper() != "SUMMARY":
                errors.append(f"{sheet_name}: {exc}")
    return frames, errors, warnings


def dedupe_rows(df):
    keys = [key for key in BUSINESS_KEY if key in df]
    if not keys or df.empty:
        return df
    sort_cols = [col for col in ["sourceModified", "sourceOrder", "sourceFile"] if col in df]
    if sort_cols:
        df = df.sort_values(sort_cols)
    return df.drop_duplicates(subset=keys, keep="last").reset_index(drop=True)


def load_workbooks(paths, preferred_sheet=None):
    frames = []
    errors = []
    warnings = []
    for index, path in enumerate(paths):
        path = Path(path).expanduser()
        try:
            workbook_frames_list, workbook_errors, workbook_warnings = workbook_frames(
                path,
                preferred_sheet,
                source_order=index * 1000,
                source_name=path.name,
                source_modified=path.stat().st_mtime,
            )
            frames.extend(workbook_frames_list)
            errors.extend(f"{path.name} / {error}" for error in workbook_errors)
            warnings.extend(workbook_warnings)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    combined = dedupe_rows(combined)
    combined.attrs["load_errors"] = errors
    combined.attrs["load_warnings"] = warnings
    return combined


def load_uploaded_workbooks(uploaded_files, preferred_sheet=None):
    frames = []
    errors = []
    warnings = []
    for index, uploaded in enumerate(uploaded_files):
        suffix = Path(uploaded.name).suffix or ".xlsx"
        with NamedTemporaryFile(suffix=suffix) as tmp:
            tmp.write(uploaded.getvalue())
            tmp.flush()
            try:
                workbook_frames_list, workbook_errors, workbook_warnings = workbook_frames(
                    tmp.name,
                    preferred_sheet,
                    source_order=index * 1000,
                    source_name=uploaded.name,
                    source_modified=index,
                )
                frames.extend(workbook_frames_list)
                errors.extend(f"{uploaded.name} / {error}" for error in workbook_errors)
                warnings.extend(workbook_warnings)
            except Exception as exc:
                errors.append(f"{uploaded.name}: {exc}")
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    combined = dedupe_rows(combined)
    combined.attrs["load_errors"] = errors
    combined.attrs["load_warnings"] = warnings
    return combined
