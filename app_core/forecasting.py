import pandas as pd


FORECAST_METRIC_DEFINITIONS = {
    "Current Inventory": {
        "meaning": "How many units are currently on hand for that product and region in the latest available week.",
        "formula": "Sum of Inventory On Hand for the product + region in the latest available week.",
    },
    "Inventory Week": {
        "meaning": "The week used for that row's current inventory. This can differ by product if some items are not active in the most recent report week.",
        "formula": "Latest available Week Start for that product + region.",
    },
    "4-Week Avg Velocity": {
        "meaning": "The average weekly unit sales pace over the most recent four weeks of data.",
        "formula": "(Week 1 Unit Sales + Week 2 Unit Sales + Week 3 Unit Sales + Week 4 Unit Sales) / 4",
    },
    "Weighted Velocity": {
        "meaning": "A recent-sales pace that gives more importance to newer weeks, so the forecast reacts faster to demand changes.",
        "formula": "(Oldest Week x 10% + Next Week x 20% + Next Week x 30% + Latest Week x 40%) using non-demo weeks when possible.",
    },
    "Trend Factor": {
        "meaning": "Shows whether demand is moving up or down recently. 1.00 means flat, above 1.00 means rising, below 1.00 means slowing.",
        "formula": "Recent 2-week average unit sales / prior 2-week average unit sales, capped between 0.75 and 1.35.",
    },
    "Adjusted Forecast Velocity": {
        "meaning": "The expected weekly unit demand after applying recent trend and demo-week handling.",
        "formula": "Weighted Velocity x Trend Factor",
    },
    "Projected 3-Week Demand": {
        "meaning": "How many units we expect to sell over the next three weeks.",
        "formula": "Adjusted Forecast Velocity x 3",
    },
    "Projected 4-Week Demand": {
        "meaning": "How many units we expect to sell over the next four weeks.",
        "formula": "Adjusted Forecast Velocity x 4",
    },
    "Weeks of Supply": {
        "meaning": "How many weeks current inventory can cover at the forecasted weekly demand pace.",
        "formula": "Current Inventory / Adjusted Forecast Velocity",
    },
    "Inventory Need": {
        "meaning": "How many additional units are needed to cover the next four weeks of expected demand.",
        "formula": "Projected 4-Week Demand - Current Inventory. If negative, show 0.",
    },
    "Expected Stockout Week": {
        "meaning": "The estimated week inventory may run out if no additional inventory comes in.",
        "formula": "Latest Inventory Week + rounded Weeks of Supply in weeks.",
    },
    "Status": {
        "meaning": "A simple priority label showing whether the item needs attention.",
        "formula": "Critical: under 1.5 weeks supply or zero inventory. Low: under 3 weeks. Watch: under 4 weeks. Healthy: within range. Overstock: above 7.2 weeks.",
    },
    "Reason Code": {
        "meaning": "A short explanation for why the row received its status.",
        "formula": "Built from row conditions such as zero inventory, under 3 weeks of supply, rising velocity, or demo week excluded.",
    },
}


TARGET_WEEKS = 4
LOW_SUPPLY_WEEKS = 3
ACTIVE_LOOKBACK_WEEKS = 4


def _latest_inventory(group):
    return pd.Series(
        {
            "inventoryOnHand": group["inventoryOnHand"].sum(min_count=1),
        }
    )


def _velocity_summary(group):
    group = group.sort_values("weekStart")
    latest_four = group.tail(4).copy()
    non_demo = latest_four[~latest_four["isDemoWeek"].fillna(False)]
    baseline_rows = non_demo if len(non_demo) >= 2 else latest_four

    four_week_avg = latest_four["unitSales"].mean()
    weights = pd.Series([0.10, 0.20, 0.30, 0.40], index=range(4)).tail(len(baseline_rows)).to_numpy()
    if len(baseline_rows):
        weighted_velocity = (baseline_rows["unitSales"].to_numpy() * weights[-len(baseline_rows):]).sum() / weights[-len(baseline_rows):].sum()
    else:
        weighted_velocity = pd.NA

    recent_two = baseline_rows.tail(2)["unitSales"].mean()
    prior_two = baseline_rows.iloc[:-2].tail(2)["unitSales"].mean()
    if pd.isna(recent_two) or pd.isna(prior_two) or prior_two == 0:
        trend_factor = 1.0
    else:
        trend_factor = min(max(recent_two / prior_two, 0.75), 1.35)

    demo_weeks_excluded = int(latest_four["isDemoWeek"].fillna(False).sum()) if len(non_demo) >= 2 else 0
    return pd.Series(
        {
            "fourWeekAvgVelocity": four_week_avg,
            "weightedVelocity": weighted_velocity,
            "trendFactor": trend_factor,
            "demoWeeksExcluded": demo_weeks_excluded,
            "weeksOfData": group["weekStart"].nunique(),
        }
    )


def _status_and_reason(row):
    status = "Healthy"
    reasons = []
    velocity = row["adjustedForecastVelocity"]
    weeks = row["weeksOfSupply"]

    if pd.isna(velocity) or velocity <= 0:
        return "Watch", "No recent sales velocity"
    if row["inventoryOnHand"] <= 0:
        status = "Critical"
        reasons.append("zero current inventory")
    if pd.notna(weeks) and weeks < 1.5:
        status = "Critical"
        reasons.append("under 1.5 weeks of supply")
    elif pd.notna(weeks) and weeks < LOW_SUPPLY_WEEKS:
        status = "Low"
        reasons.append("below 3 weeks of supply")
    elif pd.notna(weeks) and weeks < TARGET_WEEKS:
        status = "Watch"
        reasons.append("below 4 weeks of supply")
    elif pd.notna(weeks) and weeks > TARGET_WEEKS * 1.8:
        status = "Overstock"
        reasons.append("above 4-week target supply")

    if row["trendFactor"] >= 1.2:
        reasons.append("rising velocity")
    if row["demoWeeksExcluded"]:
        reasons.append("demo week excluded from baseline")
    return status, ", ".join(reasons) or "Within target range"


def build_inventory_forecast(df_full, filtered=None):
    source = df_full.copy()
    if source.empty or "weekStart" not in source:
        return pd.DataFrame(), None

    report_week = source["weekStart"].dropna().max()
    if pd.isna(report_week):
        return pd.DataFrame(), None

    if filtered is not None and not filtered.empty:
        products = filtered["commonName"].dropna().unique() if "commonName" in filtered else []
        venues = filtered["venue"].dropna().unique() if "venue" in filtered else []
        if len(products):
            source = source[source["commonName"].isin(products)]
        if len(venues):
            source = source[source["venue"].isin(venues)]

    if source.empty:
        return pd.DataFrame(), report_week

    active_cutoff = report_week - pd.Timedelta(weeks=ACTIVE_LOOKBACK_WEEKS)
    active_source = source[
        (source["weekStart"] > active_cutoff)
        & (source["unitSales"].fillna(0) > 0)
    ].dropna(subset=["commonName", "venue"])
    if active_source.empty:
        return pd.DataFrame(), report_week

    active_pairs = active_source[["commonName", "venue"]].drop_duplicates()
    source = source.merge(active_pairs, on=["commonName", "venue"], how="inner")

    latest_source = source.dropna(subset=["commonName", "venue", "weekStart"]).copy()
    latest_week_by_group = latest_source.groupby(["commonName", "venue"], dropna=False)["weekStart"].transform("max")
    latest_rows = latest_source[latest_source["weekStart"] == latest_week_by_group].copy()
    latest = (
        latest_rows.groupby(["commonName", "venue"], dropna=False)
        .agg(
            inventoryOnHand=("inventoryOnHand", "sum"),
            inventoryWeek=("weekStart", "max"),
        )
        .reset_index()
    )

    history = (
        source.dropna(subset=["commonName", "venue", "weekStart"])
        .groupby(["commonName", "venue", "weekStart"], dropna=False)
        .agg(unitSales=("unitSales", "sum"), isDemoWeek=("isDemoWeek", "max"))
        .reset_index()
    )
    velocity = history.groupby(["commonName", "venue"], dropna=False).apply(_velocity_summary).reset_index()
    forecast = latest.merge(velocity, on=["commonName", "venue"], how="left")

    forecast["inventoryOnHand"] = forecast["inventoryOnHand"].fillna(0)
    forecast["trendFactor"] = forecast["trendFactor"].fillna(1.0)
    forecast["adjustedForecastVelocity"] = forecast["weightedVelocity"] * forecast["trendFactor"]
    forecast["projected3WeekDemand"] = forecast["adjustedForecastVelocity"] * 3
    forecast["projected4WeekDemand"] = forecast["adjustedForecastVelocity"] * TARGET_WEEKS
    forecast["inventoryNeed"] = (forecast["projected4WeekDemand"] - forecast["inventoryOnHand"]).clip(lower=0)
    forecast["weeksOfSupply"] = forecast["inventoryOnHand"] / forecast["adjustedForecastVelocity"].replace({0: pd.NA})
    forecast["expectedStockoutWeek"] = forecast["inventoryWeek"] + pd.to_timedelta(forecast["weeksOfSupply"].round().fillna(0).astype(int) * 7, unit="D")

    status_reason = forecast.apply(_status_and_reason, axis=1, result_type="expand")
    forecast["status"] = status_reason[0]
    forecast["reasonCode"] = status_reason[1]
    status_rank = {"Critical": 0, "Low": 1, "Watch": 2, "Healthy": 3, "Overstock": 4}
    forecast["statusRank"] = forecast["status"].map(status_rank).fillna(9)
    return forecast.sort_values(["statusRank", "weeksOfSupply", "inventoryNeed"], ascending=[True, True, False]), report_week
