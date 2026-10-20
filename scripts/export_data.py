import json
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_core.google_sheets import load_frozen_google_sheet, load_google_sheet


CONFIG_PATH = ROOT / "app.config.json"
ROLLUP_VENUES = {"Total US by Region"}


def load_config():
    config = json.loads(CONFIG_PATH.read_text())
    dataset = os.environ.get("COSTCO_DATASET", config.get("defaultDataset", "deli"))
    datasets = config.get("datasets")
    if datasets:
        if dataset not in datasets:
            raise ValueError(f"Unknown dataset: {dataset}")
        config = {**config, **datasets[dataset], "dataset": dataset}
    else:
        config["dataset"] = dataset
    if os.environ.get("COSTCO_SOURCE_WORKBOOK"):
        config["sourceWorkbook"] = os.environ["COSTCO_SOURCE_WORKBOOK"]
    if os.environ.get("COSTCO_SOURCE_SHEET"):
        config["sourceSheet"] = os.environ["COSTCO_SOURCE_SHEET"]
    return config


def load_local_workbook(config):
    workbook = Path(config["sourceWorkbook"]).expanduser()
    if not workbook.exists():
        raise FileNotFoundError(f"Workbook not found: {workbook}")
    df = pd.read_excel(workbook, sheet_name=config.get("sourceSheet", 0))
    df.columns = [str(col).strip() for col in df.columns]
    return df.dropna(how="all"), workbook


def load_dataset(config):
    source_kind = config.get("sourceKind", "workbook")
    if source_kind == "frozen-google-sheet":
        return load_frozen_google_sheet(config["googleSheetUrl"], config["googleCredentialsPath"]), config["googleSheetUrl"]
    if source_kind == "google-sheet":
        try:
            return load_google_sheet(config["googleSheetUrl"], config.get("googleCredentialsPath")), config["googleSheetUrl"]
        except Exception:
            if not config.get("sourceWorkbook"):
                raise
    return load_local_workbook(config)


def clean_value(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value


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


def item_code(item):
    match = re.search(r"ITEM\s+(\d+)", str(item or ""))
    return match.group(1) if match else None


def main():
    config = load_config()
    df, source = load_dataset(config)

    rename = {
        "Item": "item",
        "Venue": "venue",
        "Time": "time",
        "Dollar Sales": "dollarSales",
        "Dollar Sales Year Ago": "dollarSalesYearAgo",
        "Unit Sales": "unitSales",
        "Unit Sales Year Ago": "unitSalesYearAgo",
        "Warehouses Selling": "warehousesSelling",
        "Warehouses Selling Year Ago": "warehousesSellingYearAgo",
        "Number of Warehouses": "numberOfWarehouses",
        "Number of Warehouses Year Ago": "numberOfWarehousesYearAgo",
        "Inventory On Hand": "inventoryOnHand",
        "Common Names": "commonName",
        "Dates": "dateLabel",
    }
    df = df.rename(columns=rename)
    if "venue" in df.columns:
        df = df[~df["venue"].isin(ROLLUP_VENUES)].copy()

    for column in [
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
        "avgSalesPerWarehouse",
    ]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    if "weekStart" not in df:
        df["weekStart"] = [
            parse_week_start(time_value, date_label)
            for time_value, date_label in zip(df.get("time", []), df.get("dateLabel", []))
        ]
    else:
        df["weekStart"] = pd.to_datetime(df["weekStart"], errors="coerce").dt.date.astype("string")
    if "year" not in df:
        df["year"] = df["weekStart"].astype("string").str.slice(0, 4)
    if "itemCode" not in df:
        df["itemCode"] = df["item"].apply(item_code)

    records = []
    for row in df.to_dict(orient="records"):
        records.append({key: clean_value(value) for key, value in row.items()})

    numeric_fields = [
        "dollarSales",
        "dollarSalesYearAgo",
        "unitSales",
        "unitSalesYearAgo",
        "warehousesSelling",
        "warehousesSellingYearAgo",
        "numberOfWarehouses",
        "numberOfWarehousesYearAgo",
        "inventoryOnHand",
    ]
    dimensions = ["item", "itemCode", "commonName", "venue", "time", "dateLabel", "weekStart", "year"]
    metadata = {
        "sourceWorkbook": str(source),
        "sourceSheet": config.get("sourceSheet") or config.get("label", config["dataset"]),
        "dataset": config["dataset"],
        "datasetLabel": config.get("label", config["dataset"].title()),
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "rowCount": len(records),
        "fields": {
            "dimensions": [field for field in dimensions if field in df.columns],
            "metrics": [field for field in numeric_fields if field in df.columns and df[field].notna().any()],
        },
        "venues": sorted([str(value) for value in df["venue"].dropna().unique()]) if "venue" in df else [],
        "items": sorted([str(value) for value in df["commonName"].dropna().unique()]) if "commonName" in df else [],
        "weekRange": {
            "min": clean_value(df["weekStart"].dropna().min()) if df["weekStart"].notna().any() else None,
            "max": clean_value(df["weekStart"].dropna().max()) if df["weekStart"].notna().any() else None,
        },
    }

    payload = {"metadata": metadata, "records": records}
    output = ROOT / config.get("outputData", f"public/data/{config['dataset']}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf8")
    print(f"Wrote {len(records):,} records to {output}")


if __name__ == "__main__":
    main()
