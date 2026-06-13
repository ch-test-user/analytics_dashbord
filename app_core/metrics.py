import pandas as pd


METRIC_LABELS = {
    "revenue": "Revenue",
    "dollarSales": "Dollar Sales",
    "dollarSalesYearAgo": "Dollar Sales YA",
    "unitSales": "Unit Sales",
    "unitSalesYearAgo": "Unit Sales YA",
    "warehousesSelling": "Warehouses Selling",
    "warehousesSellingYearAgo": "Warehouses Selling YA",
    "numberOfWarehouses": "Warehouses",
    "numberOfWarehousesYearAgo": "Warehouses YA",
    "inventoryOnHand": "Inventory",
    "coverageRate": "Coverage Rate",
    "avgPrice": "Average Price",
    "salesPerWarehouse": "Sales per Selling Warehouse",
    "unitsPerWarehouse": "Units per Selling Warehouse",
    "inventoryPerWarehouse": "Inventory per Warehouse",
    "dollarSalesYoYPct": "Dollar Sales YoY %",
    "unitSalesYoYPct": "Unit Sales YoY %",
    "velocity": "Unit Velocity",
    "unitVelocity": "Unit Velocity",
    "dollarVelocity": "$ per Store per Week",
    "dollarsPerStorePerWeek": "$ per Store per Week",
    "weeklyVelocity": "Weekly Unit Velocity",
    "weeklyDollarVelocity": "Weekly $ per Store",
    "weeklyDollarsPerStorePerWeek": "Weekly $ per Store",
    "weeksOfSupply": "Weeks of Supply",
    "salesShare": "Sales Share",
}


METRIC_DEFINITIONS = {
    "revenue": "Same as Dollar Sales. Sum for the selected filters.",
    "dollarSales": "Sum of Dollar Sales for the selected filters.",
    "dollarSalesYearAgo": "Sum of Dollar Sales Year Ago for the selected filters.",
    "unitSales": "Sum of Unit Sales for the selected filters.",
    "unitSalesYearAgo": "Sum of Unit Sales Year Ago for the selected filters.",
    "warehousesSelling": "Warehouses Selling, using the selected chart aggregation.",
    "warehousesSellingYearAgo": "Warehouses Selling Year Ago, using the selected chart aggregation.",
    "numberOfWarehouses": "Number of Warehouses, using the selected chart aggregation.",
    "numberOfWarehousesYearAgo": "Number of Warehouses Year Ago, using the selected chart aggregation.",
    "inventoryOnHand": "Sum of Inventory On Hand for the selected filters.",
    "coverageRate": "Warehouses Selling divided by Number of Warehouses. Usually interpreted as selling warehouse coverage.",
    "avgPrice": "Dollar Sales divided by Unit Sales.",
    "salesPerWarehouse": "Dollar Sales divided by Warehouses Selling.",
    "unitsPerWarehouse": "Unit Sales divided by Warehouses Selling.",
    "inventoryPerWarehouse": "Inventory On Hand divided by Number of Warehouses.",
    "dollarSalesYoYPct": "Dollar Sales minus Dollar Sales Year Ago, divided by Dollar Sales Year Ago.",
    "unitSalesYoYPct": "Unit Sales minus Unit Sales Year Ago, divided by Unit Sales Year Ago.",
    "velocity": "Alias for Unit Velocity. Unit Sales divided by active weeks, where active weeks are distinct weeks with unit sales greater than zero.",
    "unitVelocity": "Unit Sales divided by active weeks, where active weeks are distinct weeks with unit sales greater than zero.",
    "dollarVelocity": "Dollar Sales divided by selling store-weeks. This is dollars per store per active week.",
    "dollarsPerStorePerWeek": "Dollar Sales divided by selling store-weeks. This is dollars per store per active week.",
    "weeklyVelocity": "Unit Sales in a specific week. Demo weeks are highlighted when the source workbook marks that week in blue.",
    "weeklyDollarVelocity": "Dollar Sales divided by Warehouses Selling for that week. This is dollars per store for the week.",
    "weeklyDollarsPerStorePerWeek": "Dollar Sales divided by Warehouses Selling for that week. This is dollars per store for the week.",
    "weeksOfSupply": "Inventory On Hand divided by Unit Velocity.",
    "salesShare": "Group dollar sales divided by total dollar sales for the week.",
}


DIMENSION_LABELS = {
    "item": "Costco Item",
    "itemCode": "Item Code",
    "commonName": "Item",
    "venue": "Venue",
    "dateLabel": "Date Label",
    "weekStart": "Week",
    "year": "Year",
    "sourceFile": "Source File",
    "productTab": "Product Tab",
    "productGroup": "Product Group",
    "isDemoWeek": "Demo Week",
}


DEFAULT_CHARTS = []



AVERAGE_METRICS = {"coverageRate", "avgPrice", "dollarSalesYoYPct", "unitSalesYoYPct"}
CURRENCY_METRICS = {"dollarSales", "dollarSalesYearAgo", "revenue", "salesPerWarehouse", "dollarVelocity", "dollarsPerStorePerWeek", "weeklyDollarVelocity", "weeklyDollarsPerStorePerWeek"}
PERCENT_METRICS = {"coverageRate", "dollarSalesYoYPct", "unitSalesYoYPct", "salesShare"}


def metric_label(metric):
    return METRIC_LABELS.get(metric, metric)


def metric_definition(metric):
    return METRIC_DEFINITIONS.get(metric, "No metric definition has been configured.")


def metric_axis_title(metric, override=None):
    return override or metric_label(metric)


def add_derived_metrics(df):
    df = df.copy()
    df["revenue"] = df["dollarSales"]
    df["avgPrice"] = df["dollarSales"] / df["unitSales"].replace({0: pd.NA})
    df["coverageRate"] = df["warehousesSelling"] / df["numberOfWarehouses"].replace({0: pd.NA})
    df["inventoryPerWarehouse"] = df["inventoryOnHand"] / df["numberOfWarehouses"].replace({0: pd.NA})
    df["salesPerWarehouse"] = df["dollarSales"] / df["warehousesSelling"].replace({0: pd.NA})
    df["unitsPerWarehouse"] = df["unitSales"] / df["warehousesSelling"].replace({0: pd.NA})
    df["dollarSalesYoYPct"] = (df["dollarSales"] - df["dollarSalesYearAgo"]) / df["dollarSalesYearAgo"].replace({0: pd.NA})
    df["unitSalesYoYPct"] = (df["unitSales"] - df["unitSalesYearAgo"]) / df["unitSalesYearAgo"].replace({0: pd.NA})
    return df


def currency(value):
    return f"${value:,.0f}" if pd.notna(value) else "-"


def number(value):
    return f"{value:,.0f}" if pd.notna(value) else "-"


def percent(value):
    return f"{value:.1%}" if pd.notna(value) else "-"


def compact_number(value):
    if pd.isna(value):
        return "-"
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.0f}"


def compact_currency(value):
    if pd.isna(value):
        return "-"
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if absolute >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


def metric_value(value, metric):
    if metric in CURRENCY_METRICS:
        return currency(value)
    if metric in PERCENT_METRICS:
        return percent(value)
    if metric == "avgPrice":
        return f"${value:,.2f}" if pd.notna(value) else "-"
    return number(value)


def compact_metric_value(value, metric):
    if metric in CURRENCY_METRICS:
        return compact_currency(value)
    if metric in PERCENT_METRICS:
        return percent(value)
    if metric == "avgPrice":
        return f"${value:,.2f}" if pd.notna(value) else "-"
    return compact_number(value)


def metric_total(df, metric):
    if metric in AVERAGE_METRICS:
        return df[metric].mean()
    return df[metric].sum()


def aggregate(df, dimension, metric, aggregation, limit=None, ascending=False):
    grouped = df.groupby(dimension, dropna=False)[metric]
    if aggregation == "mean":
        output = grouped.mean()
    elif aggregation == "count":
        output = grouped.count()
    else:
        output = grouped.sum(min_count=1)

    output = output.reset_index(name=metric).dropna(subset=[dimension])
    if dimension == "weekStart":
        output = output.sort_values(dimension)
    else:
        output = output.sort_values(metric, ascending=ascending)
    if limit:
        output = output.head(limit)
    return output


def active_sales_weeks(df, by):
    group_cols = [by] if isinstance(by, str) else list(by)
    active = df.dropna(subset=group_cols + ["weekStart"]).copy()
    if active.empty:
        return pd.DataFrame(columns=group_cols + ["activeWeeks"])

    active["weekStart"] = pd.to_datetime(active["weekStart"], errors="coerce")
    selling = active[active["unitSales"].fillna(0) > 0].dropna(subset=["weekStart"])
    if selling.empty:
        return pd.DataFrame(columns=group_cols + ["activeWeeks"])

    weeks = (
        selling.groupby(group_cols, dropna=False)["weekStart"]
        .nunique()
        .reset_index(name="activeWeeks")
    )
    return weeks


def weekly_velocity(df, by):
    group_cols = [by] if isinstance(by, str) else list(by)
    active = df.dropna(subset=group_cols).copy()
    grouped = active.groupby(group_cols, dropna=False).agg(
        unitSales=("unitSales", "sum"),
        dollarSales=("dollarSales", "sum"),
        warehousesSelling=("warehousesSelling", "sum"),
        inventoryOnHand=("inventoryOnHand", "sum"),
        coverageRate=("coverageRate", "mean"),
    )
    grouped = grouped.reset_index().merge(active_sales_weeks(df, group_cols), on=group_cols, how="left")
    grouped["unitVelocity"] = grouped["unitSales"] / grouped["activeWeeks"].replace({0: pd.NA})
    grouped["velocity"] = grouped["unitVelocity"]
    grouped["dollarVelocity"] = grouped["dollarSales"] / grouped["warehousesSelling"].replace({0: pd.NA})
    grouped["dollarsPerStorePerWeek"] = grouped["dollarVelocity"]
    grouped["avgPrice"] = grouped["dollarSales"] / grouped["unitSales"].replace({0: pd.NA})
    return grouped


def weekly_operating_trends(df):
    grouped = (
        df.dropna(subset=["weekStart"])
        .groupby("weekStart", dropna=False)
        .agg(
            dollarSales=("dollarSales", "sum"),
            unitSales=("unitSales", "sum"),
            activeItems=("commonName", "nunique"),
            warehousesSelling=("warehousesSelling", "sum"),
            numberOfWarehouses=("numberOfWarehouses", "sum"),
        )
        .reset_index()
        .sort_values("weekStart")
    )
    grouped["unitVelocity"] = grouped["unitSales"] / grouped["activeItems"].replace({0: pd.NA})
    grouped["velocity"] = grouped["unitVelocity"]
    grouped["salesPerWarehouse"] = grouped["dollarSales"] / grouped["warehousesSelling"].replace({0: pd.NA})
    grouped["dollarVelocity"] = grouped["salesPerWarehouse"]
    grouped["dollarsPerStorePerWeek"] = grouped["dollarVelocity"]
    grouped["coverageRate"] = grouped["warehousesSelling"] / grouped["numberOfWarehouses"].replace({0: pd.NA})
    return grouped


def weekly_sales_mix(df, dimension, top_n=8):
    base = df.dropna(subset=["weekStart", dimension]).copy()
    grouped = (
        base.groupby(["weekStart", dimension], dropna=False)
        .agg(dollarSales=("dollarSales", "sum"))
        .reset_index()
    )
    leaders = (
        grouped.groupby(dimension, dropna=False)["dollarSales"]
        .sum()
        .sort_values(ascending=False)
        .head(top_n)
        .index
    )
    grouped[dimension] = grouped[dimension].where(grouped[dimension].isin(leaders), "Other")
    mixed = (
        grouped.groupby(["weekStart", dimension], dropna=False)
        .agg(dollarSales=("dollarSales", "sum"))
        .reset_index()
    )
    weekly_total = mixed.groupby("weekStart")["dollarSales"].transform("sum")
    mixed["salesShare"] = mixed["dollarSales"] / weekly_total.replace({0: pd.NA})
    return mixed.sort_values(["weekStart", "dollarSales"], ascending=[True, False])


def product_velocity_for_region(df, venue, limit=15):
    region = df[df["venue"] == venue].copy()
    if region.empty:
        return pd.DataFrame(columns=["commonName", "unitSales", "dollarSales", "warehousesSelling", "activeWeeks", "unitVelocity", "dollarVelocity", "dollarsPerStorePerWeek", "avgPrice"])

    velocity = weekly_velocity(region, "commonName").sort_values("dollarVelocity", ascending=False)
    if limit:
        velocity = velocity.head(limit)
    return velocity


def weekly_product_velocity(df, product, venue=None):
    columns = [
        "weekStart",
        "weekEnd",
        "unitSales",
        "dollarSales",
        "isDemoWeek",
        "month",
        "monthLabel",
        "weekLabel",
        "weekRangeLabel",
        "weeklyVelocity",
        "weeklyDollarVelocity",
        "weeklyDollarsPerStorePerWeek",
    ]
    product_rows = df[df["commonName"] == product].copy()
    if venue and venue != "All regions":
        product_rows = product_rows[product_rows["venue"] == venue]
    if product_rows.empty:
        return pd.DataFrame(columns=columns)

    grouped = (
        product_rows.dropna(subset=["weekStart"])
        .groupby("weekStart", dropna=False)
        .agg(
            unitSales=("unitSales", "sum"),
            dollarSales=("dollarSales", "sum"),
            warehousesSelling=("warehousesSelling", "sum"),
            isDemoWeek=("isDemoWeek", "max"),
        )
        .reset_index()
        .sort_values("weekStart")
    )
    grouped["weekEnd"] = grouped["weekStart"] + pd.Timedelta(days=6)
    grouped["weeklyVelocity"] = grouped["unitSales"]
    grouped["weeklyDollarVelocity"] = grouped["dollarSales"] / grouped["warehousesSelling"].replace({0: pd.NA})
    grouped["weeklyDollarsPerStorePerWeek"] = grouped["weeklyDollarVelocity"]
    grouped["month"] = grouped["weekStart"].dt.strftime("%Y-%m")
    grouped["monthLabel"] = grouped["weekStart"].dt.strftime("%b %Y")
    grouped["weekLabel"] = grouped["weekStart"].dt.strftime("%b %-d, %Y")
    grouped["weekRangeLabel"] = (
        grouped["weekStart"].dt.strftime("%b %-d")
        + "-"
        + grouped["weekEnd"].dt.strftime("%-d, %Y")
    )
    return grouped[columns]


def weeks_of_supply(df):
    velocity = weekly_velocity(df, "commonName")
    velocity["weeksOfSupply"] = velocity["inventoryOnHand"] / velocity["unitVelocity"].replace({0: pd.NA})
    return velocity
