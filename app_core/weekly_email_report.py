from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from pathlib import Path

import pandas as pd

from app_core.forecasting import FORECAST_METRIC_DEFINITIONS, build_inventory_forecast
from app_core.metrics import add_derived_metrics


REPORT_PRODUCT_LIMIT = 6
ACTION_ROW_LIMIT = 12


@dataclass
class WeeklyEmailReport:
    subject: str
    html: str
    report_week: pd.Timestamp | None
    action_rows: pd.DataFrame


def _currency(value):
    if pd.isna(value):
        return "-"
    return f"${value:,.0f}"


def _number(value):
    if pd.isna(value):
        return "-"
    return f"{value:,.0f}"


def _decimal(value, places=1):
    if pd.isna(value):
        return "-"
    return f"{value:,.{places}f}"


def _setting_bool(value):
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _percent(value):
    if pd.isna(value):
        return "-"
    return f"{value:+.0%}"


def _week_label(week_start):
    week_end = pd.to_datetime(week_start) + pd.Timedelta(days=6)
    return week_end.strftime("%-m/%-d")


def _product_title(value):
    return str(value or "").title()


def _forecast_columns(forecast):
    forecast = forecast.copy()
    if forecast.empty:
        return forecast
    defaults = {
        "inventoryNeed": 0,
        "status": "Watch",
        "statusRank": 9,
        "weeksOfSupply": pd.NA,
        "trendFactor": 1.0,
        "inventoryOnHand": 0,
    }
    for column, default in defaults.items():
        if column not in forecast:
            forecast[column] = default
    return forecast


def _ensure_dashboard_metrics(df):
    required = {
        "dollarSales",
        "unitSales",
        "warehousesSelling",
        "numberOfWarehouses",
        "inventoryOnHand",
        "dollarSalesYearAgo",
        "unitSalesYearAgo",
    }
    if required.issubset(df.columns):
        return add_derived_metrics(df)
    return df.copy()


def _latest_week_rows(df, report_week):
    if report_week is None or pd.isna(report_week):
        return df.iloc[0:0].copy()
    return df[df["weekStart"] == report_week].copy()


def weekly_kpi_rows(df, forecast, report_week):
    if df.empty or report_week is None or pd.isna(report_week):
        return []

    this_week = _latest_week_rows(df, report_week)
    prior_week = _latest_week_rows(df, report_week - pd.Timedelta(weeks=1))
    trailing = df[(df["weekStart"] <= report_week) & (df["weekStart"] > report_week - pd.Timedelta(weeks=4))]
    forecast = _forecast_columns(forecast)

    def wow(current, prior):
        if pd.isna(prior) or prior == 0:
            return pd.NA
        return (current - prior) / prior

    this_sales = this_week["dollarSales"].sum()
    prior_sales = prior_week["dollarSales"].sum()
    this_units = this_week["unitSales"].sum()
    prior_units = prior_week["unitSales"].sum()
    active_products = this_week.loc[this_week["unitSales"].fillna(0) > 0, "commonName"].nunique()
    prior_active_products = prior_week.loc[prior_week["unitSales"].fillna(0) > 0, "commonName"].nunique()
    avg_wos = forecast["weeksOfSupply"].replace([float("inf"), -float("inf")], pd.NA).dropna().mean()
    inventory_need = forecast.loc[forecast["status"].isin(["Critical", "Low"]), "inventoryNeed"].fillna(0).sum()
    forecast_units = forecast["projected4WeekDemand"].fillna(0).sum() if "projected4WeekDemand" in forecast else pd.NA

    return [
        ("Sales $", _currency(this_sales), _currency(prior_sales), _percent(wow(this_sales, prior_sales)), _currency(trailing["dollarSales"].sum())),
        ("Units Sold", _number(this_units), _number(prior_units), _percent(wow(this_units, prior_units)), _number(forecast_units)),
        ("Active Products", _number(active_products), _number(prior_active_products), _number(active_products - prior_active_products), _number(active_products)),
        ("Avg Weeks of Supply", _decimal(avg_wos), "-", "-", _decimal(avg_wos)),
        ("Inventory Need", _number(inventory_need), "-", "-", _number(inventory_need)),
    ]


def _weekly_velocity_data(df, product, max_weeks=8):
    rows = df[df["commonName"] == product].dropna(subset=["weekStart", "venue"]).copy()
    if rows.empty:
        return pd.DataFrame(), [], set()
    weekly = (
        rows.groupby(["venue", "weekStart"], dropna=False)
        .agg(
            dollarSales=("dollarSales", "sum"),
            warehousesSelling=("warehousesSelling", "sum"),
            isDemoWeek=("isDemoWeek", "max"),
        )
        .reset_index()
        .sort_values("weekStart")
    )
    weekly["weeklyDollarsPerStore"] = weekly["dollarSales"] / weekly["warehousesSelling"].replace({0: pd.NA})
    weeks = weekly["weekStart"].dropna().sort_values().drop_duplicates().tail(max_weeks).tolist()
    weekly = weekly[weekly["weekStart"].isin(weeks)].copy()
    demo_weeks = set(weekly.loc[weekly["isDemoWeek"].fillna(False), "weekStart"].tolist())
    return weekly, weeks, demo_weeks


def weekly_velocity_table_html(df, product, max_regions=8, max_weeks=8):
    weekly, weeks, demo_weeks = _weekly_velocity_data(df, product, max_weeks=max_weeks)
    if weekly.empty or not weeks:
        return ""

    latest_week = weeks[-1]
    latest_values = weekly[weekly["weekStart"] == latest_week].sort_values("weeklyDollarsPerStore", ascending=False)
    regions = latest_values["venue"].dropna().head(max_regions).tolist()
    if not regions:
        regions = weekly["venue"].dropna().drop_duplicates().head(max_regions).tolist()

    pivot = weekly.pivot_table(index="venue", columns="weekStart", values="weeklyDollarsPerStore", aggfunc="sum")
    pivot = pivot.reindex(index=regions, columns=weeks)
    wow = pivot.pct_change(axis=1)

    header = ["<th>Region</th>"]
    for week in weeks:
        demo_class = " demo-week" if week in demo_weeks else ""
        marker = "*" if week in demo_weeks else ""
        header.append(f'<th class="{demo_class.strip()}">{escape(_week_label(week))}{marker}</th>')

    body = []
    for region in regions:
        values = [f'<td class="region-name">{escape(str(region))}</td>']
        deltas = ['<td class="wow-label">WoW</td>']
        for week in weeks:
            latest_class = " latest" if week == latest_week else ""
            delta = wow.loc[region, week]
            delta_class = "positive" if pd.notna(delta) and delta > 0 else "negative" if pd.notna(delta) and delta < 0 else "muted"
            values.append(f'<td class="{latest_class.strip()}">{escape(_currency(pivot.loc[region, week]))}</td>')
            deltas.append(f'<td class="{delta_class} {latest_class}">{escape(_percent(delta))}</td>')
        body.append(f'<tr class="value-row">{"".join(values)}</tr>')
        body.append(f'<tr class="wow-row">{"".join(deltas)}</tr>')

    note = ""
    if demo_weeks:
        labels = ", ".join(_week_label(week) for week in sorted(demo_weeks))
        note = f'<p class="note">*Demo week - {escape(labels)} sales lift may reflect in-club demo activity.</p>'

    return (
        f'<h3>{escape(_product_title(product))} - Weekly Velocity Trend</h3>'
        '<p class="subtle">Average $ Sales per Warehouse Selling</p>'
        '<table class="velocity-table">'
        f'<thead><tr>{"".join(header)}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody>'
        '</table>'
        f'{note}'
    )


def choose_report_products(df, forecast, limit=REPORT_PRODUCT_LIMIT):
    forecast = _forecast_columns(forecast)
    products = []
    if not forecast.empty:
        action = forecast[forecast["status"].isin(["Critical", "Low", "Watch"])].copy()
        if not action.empty:
            products = action.sort_values(["statusRank", "inventoryNeed"], ascending=[True, False])["commonName"].dropna().drop_duplicates().tolist()
    if len(products) < limit and not df.empty:
        latest_week = df["weekStart"].dropna().max()
        recent = df[df["weekStart"] == latest_week] if pd.notna(latest_week) else df
        top = (
            recent.groupby("commonName", dropna=False)["dollarSales"]
            .sum()
            .sort_values(ascending=False)
            .index.dropna()
            .tolist()
        )
        products.extend([product for product in top if product not in products])
    return products[:limit]


def weekly_insight_bullets(df, forecast, products):
    insights = []
    forecast = _forecast_columns(forecast)
    report_week = df["weekStart"].dropna().max() if not df.empty else None
    if report_week is not None and pd.notna(report_week):
        insights.append(f"Report is anchored to week ending {(report_week + pd.Timedelta(days=6)).date()}.")

    action = forecast[forecast["status"].isin(["Critical", "Low"])] if not forecast.empty else pd.DataFrame()
    if not action.empty:
        need = action["inventoryNeed"].fillna(0).sum()
        insights.append(f"{len(action):,} product-region rows are Critical or Low, with {_number(need)} units needed to cover expected 4-week demand.")
        urgent = action.sort_values(["statusRank", "weeksOfSupply"]).iloc[0]
        insights.append(f"Most urgent row is {_product_title(urgent['commonName'])} in {urgent['venue']} at {_decimal(urgent['weeksOfSupply'])} weeks of supply.")

    for product in products[:4]:
        weekly, weeks, _ = _weekly_velocity_data(df, product, max_weeks=5)
        if weekly.empty or len(weeks) < 2:
            continue
        latest = weekly[weekly["weekStart"] == weeks[-1]].copy()
        prior = weekly[weekly["weekStart"] == weeks[-2]][["venue", "weeklyDollarsPerStore"]].rename(columns={"weeklyDollarsPerStore": "priorValue"})
        comparison = latest.merge(prior, on="venue", how="left")
        comparison["wowPct"] = (comparison["weeklyDollarsPerStore"] - comparison["priorValue"]) / comparison["priorValue"].replace({0: pd.NA})
        movers = comparison.dropna(subset=["wowPct"])
        if not movers.empty:
            mover = movers.reindex(movers["wowPct"].abs().sort_values(ascending=False).index).iloc[0]
            insights.append(f"{_product_title(product)} in {mover['venue']} moved {_percent(mover['wowPct'])} WoW to {_currency(mover['weeklyDollarsPerStore'])} per warehouse selling.")

    rising = forecast[(forecast["trendFactor"] >= 1.2) & forecast["status"].isin(["Critical", "Low", "Watch"])] if not forecast.empty else pd.DataFrame()
    if not rising.empty:
        insights.append(f"{len(rising):,} flagged rows also have rising recent velocity, so demand is running above baseline.")
    return insights[:7]


def _action_table(forecast):
    forecast = _forecast_columns(forecast)
    rows = forecast[forecast["status"].isin(["Critical", "Low"])].copy()
    if rows.empty:
        return '<p class="empty">No Critical or Low inventory rows this week.</p>', rows

    rows = rows.sort_values(["statusRank", "weeksOfSupply", "inventoryNeed"], ascending=[True, True, False]).head(ACTION_ROW_LIMIT)
    cells = []
    for row in rows.itertuples():
        stockout = getattr(row, "expectedStockoutWeek", pd.NaT)
        stockout_text = pd.to_datetime(stockout).date().isoformat() if pd.notna(stockout) else "-"
        status_class = "critical" if row.status == "Critical" else "low"
        cells.append(
            "<tr>"
            f'<td><span class="pill {status_class}">{escape(str(row.status))}</span></td>'
            f"<td>{escape(_product_title(row.commonName))}</td>"
            f"<td>{escape(str(row.venue))}</td>"
            f"<td>{_number(row.inventoryOnHand)}</td>"
            f"<td>{_decimal(row.weeksOfSupply)}</td>"
            f"<td>{_number(getattr(row, 'projected4WeekDemand', pd.NA))}</td>"
            f"<td>{_number(row.inventoryNeed)}</td>"
            f"<td>{escape(stockout_text)}</td>"
            "</tr>"
        )
    table = (
        '<table class="data-table">'
        '<thead><tr><th>Priority</th><th>Product</th><th>Region</th><th>Current Inventory</th><th>Weeks of Supply</th><th>4-Week Demand</th><th>Inventory Need</th><th>Expected Stockout</th></tr></thead>'
        f'<tbody>{"".join(cells)}</tbody>'
        '</table>'
    )
    return table, rows


def _kpi_table(rows):
    body = "".join(
        "<tr>"
        f"<td>{escape(label)}</td><td>{this_week}</td><td>{last_week}</td><td>{wow}</td><td>{forecast}</td>"
        "</tr>"
        for label, this_week, last_week, wow, forecast in rows
    )
    return (
        '<table class="data-table kpi-table">'
        '<thead><tr><th>Metric</th><th>This Week</th><th>Last Week</th><th>WoW Change</th><th>4-Week Outlook</th></tr></thead>'
        f'<tbody>{body}</tbody>'
        '</table>'
    )


def _metric_guide_html():
    wanted = ["Weeks of Supply", "Inventory Need", "Weighted Velocity", "Trend Factor", "Adjusted Forecast Velocity", "Status"]
    rows = []
    for metric in wanted:
        details = FORECAST_METRIC_DEFINITIONS.get(metric, {})
        rows.append(
            "<tr>"
            f"<td>{escape(metric)}</td>"
            f"<td>{escape(details.get('meaning', ''))}</td>"
            f"<td class=\"formula\">{escape(details.get('formula', ''))}</td>"
            "</tr>"
        )
    return (
        '<table class="data-table guide-table">'
        '<thead><tr><th>Metric</th><th>Plain meaning</th><th>Formula</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
    )


def email_styles():
    return """
    <style>
      body{margin:0;padding:0;background:#ffffff;color:#1f2933;font-family:Arial,Helvetica,sans-serif;}
      .wrap{max-width:980px;margin:0 auto;padding:24px 28px;}
      h1{font-size:21px;margin:0 0 4px;color:#152536;}
      h2{font-size:15px;margin:24px 0 8px;text-transform:uppercase;letter-spacing:.02em;color:#152536;}
      h3{font-size:14px;margin:22px 0 2px;color:#111827;}
      p{font-size:13px;line-height:1.4;margin:6px 0;}
      .subtle{font-size:12px;color:#5d6978;margin-top:0;}
      .summary{font-size:13px;color:#344054;margin:8px 0 18px;}
      ul{margin:8px 0 12px 20px;padding:0;font-size:13px;line-height:1.45;}
      .data-table,.velocity-table{border-collapse:collapse;width:100%;font-size:12px;margin:6px 0 14px;}
      .data-table th{background:#2f4358;color:#fff;text-align:left;border:1px solid #2f4358;padding:7px 8px;}
      .data-table td{border:1px solid #d7dce1;padding:7px 8px;vertical-align:top;}
      .data-table td:not(:first-child),.data-table th:not(:first-child){text-align:right;}
      .kpi-table td:first-child,.kpi-table th:first-child,.guide-table td:first-child,.guide-table th:first-child{text-align:left;}
      .guide-table td:nth-child(2),.guide-table th:nth-child(2),.guide-table td:nth-child(3),.guide-table th:nth-child(3){text-align:left;}
      .formula{font-family:"Times New Roman",serif;font-style:italic;background:#fff8df;}
      .pill{display:inline-block;border-radius:999px;padding:2px 8px;font-weight:bold;font-size:11px;}
      .critical{background:#f4cccc;color:#8a1f1f;}
      .low{background:#fce5cd;color:#7a3e00;}
      .velocity-table{width:auto;max-width:100%;}
      .velocity-table th{background:#2f4358;color:#fff;border:1px solid #2f4358;padding:6px 8px;text-align:right;}
      .velocity-table th:first-child,.velocity-table td:first-child{text-align:left;min-width:82px;}
      .velocity-table th.demo-week{background:#f39c12;}
      .velocity-table td{border:1px solid #d7dce1;padding:6px 8px;text-align:right;white-space:nowrap;}
      .value-row td{background:#f2f3f5;}
      .wow-row td{background:#fbfbfc;color:#667085;}
      .region-name{font-weight:bold;color:#263238;}
      .wow-label{font-weight:bold;color:#77808a;}
      .latest{background:#e8eff3!important;font-weight:bold;}
      .positive{color:#027a3d!important;font-weight:bold;}
      .negative{color:#c62828!important;font-weight:bold;}
      .muted{color:#8b949e!important;}
      .note,.empty{font-size:12px;color:#5d6978;}
    </style>
    """


def build_weekly_email_report(df, selected_products=None):
    df = _ensure_dashboard_metrics(df.copy())
    forecast, report_week = build_inventory_forecast(df, df)
    forecast = _forecast_columns(forecast)
    products = selected_products or choose_report_products(df, forecast)
    kpis = weekly_kpi_rows(df, forecast, report_week)
    insights = weekly_insight_bullets(df, forecast, products)
    action_html, action_rows = _action_table(forecast)
    trend_sections = "".join(weekly_velocity_table_html(df, product) for product in products)

    week_end = report_week + pd.Timedelta(days=6) if report_week is not None and pd.notna(report_week) else None
    week_text = week_end.date().isoformat() if week_end is not None else "latest week"
    subject = f"Chef Hak's Weekly Sales & Inventory Report - Week Ending {week_text}"
    coverage = f"{df['commonName'].nunique():,} products across {df['venue'].nunique():,} regions" if not df.empty else "No data loaded"
    summary = insights[0] if insights else "Weekly sales, inventory risk, and velocity trends are attached below."

    html = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"{email_styles()}</head><body><div class=\"wrap\">"
        f"<h1>{escape(subject)}</h1>"
        f"<p class=\"subtle\">Coverage: {escape(coverage)} | Generated from latest dashboard data</p>"
        f"<p class=\"summary\"><strong>Executive summary:</strong> {escape(summary)}</p>"
        "<h2>Weekly KPI Snapshot</h2>"
        f"{_kpi_table(kpis)}"
        "<h2>Action Required: Critical / Low Inventory</h2>"
        f"{action_html}"
        "<h2>Weekly Insights</h2>"
        f"<ul>{''.join(f'<li>{escape(item)}</li>' for item in insights)}</ul>"
        "<h2>Weekly Velocity Trends</h2>"
        f"{trend_sections or '<p class=\"empty\">No velocity trend tables are available for this report.</p>'}"
        "<h2>Metric Guide</h2>"
        f"{_metric_guide_html()}"
        "</div></body></html>"
    )
    return WeeklyEmailReport(subject=subject, html=html, report_week=report_week, action_rows=action_rows)


def send_email_report(
    report,
    recipients,
    sender=None,
    smtp_host=None,
    smtp_port=None,
    username=None,
    password=None,
    use_tls=None,
    require_auth=None,
):
    recipients = [email.strip() for email in recipients if email and email.strip()]
    if not recipients:
        raise ValueError("At least one recipient email is required.")

    sender = sender or os.getenv("REPORT_EMAIL_SENDER") or username
    smtp_host = smtp_host or os.getenv("REPORT_SMTP_HOST")
    smtp_port = int(smtp_port or os.getenv("REPORT_SMTP_PORT", "587"))
    username = username or os.getenv("REPORT_SMTP_USERNAME")
    password = password or os.getenv("REPORT_SMTP_PASSWORD")
    use_tls = _setting_bool(use_tls if use_tls is not None else os.getenv("REPORT_SMTP_USE_TLS", "true"))
    require_auth = _setting_bool(require_auth if require_auth is not None else os.getenv("REPORT_SMTP_REQUIRE_AUTH", "true"))

    missing = [name for name, value in {
        "REPORT_EMAIL_SENDER": sender,
        "REPORT_SMTP_HOST": smtp_host,
    }.items() if not value]
    if require_auth:
        missing.extend(
            name for name, value in {
                "REPORT_SMTP_USERNAME": username,
                "REPORT_SMTP_PASSWORD": password,
            }.items() if not value
        )
    if missing:
        raise RuntimeError(f"Missing email settings: {', '.join(missing)}")

    message = EmailMessage()
    message["Subject"] = report.subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content("This email contains an HTML weekly Chef Hak's sales and inventory report.")
    message.add_alternative(report.html, subtype="html")

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        if use_tls:
            server.starttls()
        if require_auth:
            server.login(username, password)
        server.send_message(message)


def save_report_html(report, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.html, encoding="utf-8")
    return path
