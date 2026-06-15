from html import escape
import calendar
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from app_core.data import load_uploaded_workbooks, load_workbooks, list_workbooks
from app_core.google_sheets import load_google_sheet
from app_core.metrics import (
    DEFAULT_CHARTS,
    DIMENSION_LABELS,
    METRIC_LABELS,
    CURRENCY_METRICS,
    PERCENT_METRICS,
    add_derived_metrics,
    aggregate,
    currency,
    compact_currency,
    compact_number,
    metric_axis_title,
    metric_definition,
    metric_value,
    number,
    percent,
    product_velocity_for_region,
    weekly_product_velocity,
    weekly_velocity,
    weekly_operating_trends,
    weeks_of_supply,
)


st.set_page_config(
    page_title="Costco Consumption Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    .block-container { padding-top: 1.6rem; }
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(5, minmax(150px, 1fr));
        gap: 0.75rem;
        margin: 0.75rem 0 1rem;
    }
    .kpi-card {
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 0.5rem;
        padding: 0.8rem 0.9rem;
        background: var(--background-color, transparent);
        min-height: 92px;
    }
    .kpi-label {
        color: var(--text-color, inherit);
        opacity: 0.68;
        font-size: 0.78rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        margin-bottom: 0.35rem;
    }
    .kpi-value {
        color: var(--text-color, inherit);
        font-size: 1.65rem;
        font-weight: 700;
        line-height: 1.1;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .kpi-detail {
        color: var(--text-color, inherit);
        opacity: 0.68;
        font-size: 0.78rem;
        margin-top: 0.35rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    div[data-baseweb="tab-list"][role="tablist"] {
        position: sticky !important;
        top: 0 !important;
        z-index: 9999 !important;
        background: var(--background-color, transparent) !important;
        border-bottom: 1px solid rgba(128, 128, 128, 0.25) !important;
        padding-top: 0.35rem !important;
    }
    @media (max-width: 1100px) {
        .kpi-grid { grid-template-columns: repeat(2, minmax(150px, 1fr)); }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def cached_path_load(paths, preferred_sheet, signatures):
    return add_derived_metrics(load_workbooks(paths, preferred_sheet or None))


@st.cache_data(show_spinner=False)
def cached_upload_load(files_payload, preferred_sheet):
    class UploadedPayload:
        def __init__(self, name, content):
            self.name = name
            self._content = content

        def getvalue(self):
            return self._content

    uploads = [UploadedPayload(name, content) for name, content in files_payload]
    return add_derived_metrics(load_uploaded_workbooks(uploads, preferred_sheet or None))


@st.cache_data(show_spinner=False)
def cached_google_sheet_load(spreadsheet_url_or_id, credentials_path):
    return add_derived_metrics(load_google_sheet(spreadsheet_url_or_id, credentials_path or None))


def file_signatures(paths):
    return tuple((str(path), Path(path).stat().st_mtime, Path(path).stat().st_size) for path in paths)


def load_config():
    config_path = Path(__file__).resolve().parent / "app.config.json"
    return json.loads(config_path.read_text())


def resolve_project_path(path_value):
    if not path_value:
        return ""
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return str(path)
    return str((Path(__file__).resolve().parent / path).resolve())


def google_credentials_config(config):
    # Streamlit Cloud + Streamlit in Snowflake (via ALTER STREAMLIT SET SECRETS)
    try:
        if "google_service_account" in st.secrets:
            secret = st.secrets["google_service_account"]
            # Snowflake secrets come as a plain string, Streamlit Cloud as a dict
            if isinstance(secret, str):
                return json.loads(secret), "Snowflake Secret"
            return dict(secret), "Streamlit Secrets"
    except Exception:
        pass

    credentials_path = resolve_project_path(config.get("googleCredentialsPath", ""))
    return credentials_path, credentials_path


def load_dashboard_data(config):
    with st.sidebar:
        st.header("Data Source")
        st.caption("Google Sheets")

        if st.button("Refresh data cache", use_container_width=True):
            cached_google_sheet_load.clear()
            st.rerun()

        spreadsheet_url = st.text_input("Google Sheet URL or ID", value=config.get("googleSheetUrl", ""))
        credentials_config, _ = google_credentials_config(config)
        if not spreadsheet_url:
            st.warning("Enter a Google Sheet URL or spreadsheet ID.")
            st.stop()
        if credentials_config and not isinstance(credentials_config, dict) and not Path(credentials_config).expanduser().exists():
            st.warning("Service account key path does not exist.")

        try:
            df = cached_google_sheet_load(spreadsheet_url, credentials_config)
        except Exception as exc:
            st.error(f"Could not load Google Sheet: {exc}")
            st.stop()
        source_tabs = sorted(df["sourceSheet"].dropna().unique().tolist()) if not df.empty and "sourceSheet" in df else []
        return df, "Google Sheets", source_tabs


def metric_card(label, compact_value, detail=None):
    label_text = str(label)
    value_text = str(compact_value)
    detail_text = str(detail) if detail else ""
    tooltip_text = f"{label_text}: {value_text}"
    if detail_text:
        tooltip_text = f"{tooltip_text} - {detail_text}"

    detail_html = (
        f"<div class='kpi-detail' title='{escape(detail_text, quote=True)}'>{escape(detail_text)}</div>"
        if detail_text
        else ""
    )
    return (
        f"<div class='kpi-card' title='{escape(tooltip_text, quote=True)}'>"
        f"<div class='kpi-label' title='{escape(label_text, quote=True)}'>{escape(label_text)}</div>"
        f"<div class='kpi-value' title='{escape(value_text, quote=True)}'>{escape(value_text)}</div>"
        f"{detail_html}"
        "</div>"
    )


def metric_grid(cards):
    st.markdown(
        "<div class='kpi-grid'>"
        + "".join(metric_card(label, value, detail) for label, value, detail in cards)
        + "</div>",
        unsafe_allow_html=True,
    )


def sorted_bar_chart(data, category, value, value_label=None, height=340):
    if data.empty:
        st.info("No data for the selected filters.")
        return
    if value in data and data[value].dropna().empty:
        st.info(f"{METRIC_LABELS.get(value, value)} is not available for the selected source/filters.")
        return

    label = value_label or METRIC_LABELS.get(value, value)
    plot_data = data.copy()
    plot_data["_metric_definition"] = metric_definition(value)
    chart = (
        alt.Chart(plot_data)
        .mark_bar()
        .encode(
            y=alt.Y(f"{category}:N", sort="-x", title=None),
            x=alt.X(f"{value}:Q", title=metric_axis_title(value, label)),
            tooltip=[
                alt.Tooltip(f"{category}:N", title=DIMENSION_LABELS.get(category, category)),
                alt.Tooltip(f"{value}:Q", title=label, format=",.2f"),
                alt.Tooltip("_metric_definition:N", title="Metric definition"),
            ],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


def line_chart(data, x, y, value_label=None, height=300):
    if data.empty:
        st.info("No data for the selected filters.")
        return
    if y in data and data[y].dropna().empty:
        st.info(f"{METRIC_LABELS.get(y, y)} is not available for the selected source/filters.")
        return

    label = value_label or METRIC_LABELS.get(y, y)
    plot_data = data.copy()
    plot_data["_metric_definition"] = metric_definition(y)
    chart = (
        alt.Chart(plot_data)
        .mark_line(point=True)
        .encode(
            x=alt.X(f"{x}:T" if x == "weekStart" else f"{x}:N", title=DIMENSION_LABELS.get(x, x)),
            y=alt.Y(f"{y}:Q", title=metric_axis_title(y, label)),
            tooltip=[
                alt.Tooltip(f"{x}:T" if x == "weekStart" else f"{x}:N", title=DIMENSION_LABELS.get(x, x)),
                alt.Tooltip(f"{y}:Q", title=label, format=",.2f"),
                alt.Tooltip("_metric_definition:N", title="Metric definition"),
            ],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


def demo_week_velocity_chart(data, height=340):
    if data.empty:
        st.info("No weekly velocity data for the selected product and filters.")
        return

    plot_data = data.copy()
    plot_data["demoStatus"] = plot_data["isDemoWeek"].map({True: "Demo week", False: "Regular week"})
    plot_data["_metric_definition"] = metric_definition("weeklyVelocity")

    base = alt.Chart(plot_data).encode(
        x=alt.X(
            "weekRangeLabel:N",
            sort=list(plot_data["weekRangeLabel"]),
            title="Week range",
            axis=alt.Axis(labelAngle=-35),
        ),
        y=alt.Y("weeklyDollarsPerStorePerWeek:Q", title=metric_axis_title("weeklyDollarsPerStorePerWeek", "Weekly $ per Store")),
        tooltip=[
            alt.Tooltip("weekRangeLabel:N", title="Week Range"),
            alt.Tooltip("weekStart:T", title="Week Start"),
            alt.Tooltip("weekEnd:T", title="Week End"),
            alt.Tooltip("weeklyDollarsPerStorePerWeek:Q", title="Weekly $ per Store", format="$,.2f"),
            alt.Tooltip("weeklyVelocity:Q", title="Weekly Unit Velocity", format=",.0f"),
            alt.Tooltip("dollarSales:Q", title="Dollar Sales", format=",.2f"),
            alt.Tooltip("demoStatus:N", title="Demo Status"),
            alt.Tooltip("_metric_definition:N", title="Metric definition"),
        ],
    )
    line = base.mark_line(point=False, color="#2F5D7C", strokeWidth=3)
    points = base.mark_point(filled=True, size=95).encode(
        color=alt.Color(
            "demoStatus:N",
            title=None,
            scale=alt.Scale(domain=["Demo week", "Regular week"], range=["#2B8CBE", "#6E7781"]),
        )
    )
    st.altair_chart((line + points).properties(height=height), use_container_width=True)


def weekly_performance_status(product_name, value):
    group = product_group(product_name)
    return velocity_threshold_status(group, value)


def weekly_performance_data(data, product_name, region_label):
    performance = data.copy().sort_values("weekStart")
    if performance.empty:
        return performance
    performance["wowPct"] = performance["weeklyDollarsPerStorePerWeek"].pct_change()
    performance["performance"] = performance["weeklyDollarsPerStorePerWeek"].apply(lambda value: weekly_performance_status(product_name, value))
    performance["pointStatus"] = performance.apply(lambda row: "Demo week" if row.get("isDemoWeek") else row["performance"], axis=1)
    performance["regionLabel"] = region_label
    return performance


def compact_product_title(product_name, region_label):
    name = str(product_name)
    prefixes = ["1735647 ORG ", "1486656 ", "1486657 ", "1647892 ", "1684743 ", "1747121 ", "1840329 ", "1942703 ", "1958551 ", "1964966 ", "1964972 ", "1965017 ", "1968332 ", "1975119 ", "1978085 ", "2009544 ", "2027129 ", "2058788 "]
    for prefix in prefixes:
        name = name.replace(prefix, "")
    title = name.title()
    if region_label != "All selected regions":
        title = f"{region_label} {title}"
    return title


def weekly_performance_chart(data, product_name, height=520):
    if data.empty:
        st.info("No weekly velocity data for the selected product and filters.")
        return

    plot_data = data.copy().sort_values("weekStart")
    plot_data["metricDefinition"] = metric_definition("weeklyDollarsPerStorePerWeek")
    plot_data["wowLabel"] = plot_data["wowPct"].apply(lambda value: "-" if pd.isna(value) else f"{value:+.0%}")
    plot_data["valueLabel"] = plot_data["weeklyDollarsPerStorePerWeek"].apply(lambda value: f"${value:,.0f}" if pd.notna(value) else "-")
    plot_data["labelYOffset"] = -16
    plot_data["weekAxisLabel"] = plot_data["weekEnd"].dt.strftime("%-m/%-d")

    avg_value = plot_data["weeklyDollarsPerStorePerWeek"].mean()
    peak = plot_data.sort_values("weeklyDollarsPerStorePerWeek", ascending=False).iloc[0]
    low = plot_data.sort_values("weeklyDollarsPerStorePerWeek", ascending=True).iloc[0]
    first_end = plot_data["weekEnd"].min()
    last_end = plot_data["weekEnd"].max()
    week_label_order = plot_data.sort_values("weekEnd")["weekAxisLabel"].tolist()
    label_angle = -45 if len(week_label_order) > 12 else 0
    region_label = plot_data["regionLabel"].iloc[0] if "regionLabel" in plot_data else "All selected regions"
    title = compact_product_title(product_name, region_label)

    st.markdown(f"### {title}")
    st.caption(f"Avg. $ Sales per Warehouse Selling | Week Ending {first_end.strftime('%-m/%-d/%Y')} - {last_end.strftime('%-m/%-d/%Y')}")

    card_cols = st.columns(3)
    card_cols[0].metric("Peak Week", f"${peak['weeklyDollarsPerStorePerWeek']:,.2f}", peak["weekEnd"].strftime("%b %-d, %Y"))
    card_cols[1].metric("Lowest Week", f"${low['weeklyDollarsPerStorePerWeek']:,.2f}", low["weekEnd"].strftime("%b %-d, %Y"))
    card_cols[2].metric(f"{len(plot_data)}-Week Average", f"${avg_value:,.2f}", f"{first_end.strftime('%b %-d')} - {last_end.strftime('%b %-d')}")

    y_min = max(0, plot_data["weeklyDollarsPerStorePerWeek"].min() * 0.72)
    y_max = plot_data["weeklyDollarsPerStorePerWeek"].max() * 1.18

    base = alt.Chart(plot_data).encode(
        x=alt.X(
            "weekAxisLabel:N",
            title="Week Ending",
            sort=week_label_order,
            axis=alt.Axis(
                labelAngle=label_angle,
                labelFontSize=12,
                labelLimit=90,
                labelOverlap=False,
                titleFontSize=12,
                titlePadding=14,
            ),
        ),
        y=alt.Y(
            "weeklyDollarsPerStorePerWeek:Q",
            title=None,
            scale=alt.Scale(domain=[y_min, y_max]),
            axis=alt.Axis(format="$,.0f", grid=True, labelFontSize=12),
        ),
        tooltip=[
            alt.Tooltip("weekRangeLabel:N", title="Week"),
            alt.Tooltip("regionLabel:N", title="Region"),
            alt.Tooltip("weeklyDollarsPerStorePerWeek:Q", title="Avg $ / Whse", format="$,.2f"),
            alt.Tooltip("wowLabel:N", title="WoW Change"),
            alt.Tooltip("performance:N", title="Performance"),
            alt.Tooltip("weeklyVelocity:Q", title="Unit Sales", format=",.0f"),
            alt.Tooltip("dollarSales:Q", title="Dollar Sales", format="$,.0f"),
            alt.Tooltip("metricDefinition:N", title="Metric definition"),
        ],
    )
    hover = alt.selection_point(
        fields=["weekAxisLabel"],
        nearest=True,
        on="pointerover",
        empty=False,
        clear="pointerout",
    )
    hover_targets = base.mark_point(opacity=0, size=260).add_params(hover)
    crosshair_base = alt.Chart(plot_data).transform_filter(hover)
    x_crosshair = crosshair_base.mark_rule(
        color="#9CA3AF",
        strokeDash=[2, 4],
        strokeWidth=0.75,
    ).encode(
        x=alt.X("weekAxisLabel:N", sort=week_label_order),
    )
    y_crosshair = crosshair_base.mark_rule(
        color="#9CA3AF",
        strokeDash=[2, 4],
        strokeWidth=0.75,
    ).encode(
        y="weeklyDollarsPerStorePerWeek:Q",
    )
    hover_point = base.mark_point(filled=True, size=180, color="#1289E8", stroke="#FFFFFF", strokeWidth=3).transform_filter(hover)

    area = base.mark_area(color="#1E88E5", opacity=0.10, interpolate="linear").encode(order=alt.Order("weekEnd:T"))
    line = base.mark_line(color="#1289E8", strokeWidth=4, point=False, interpolate="linear").encode(order=alt.Order("weekEnd:T"))
    points = base.mark_point(filled=True, size=120, color="#1289E8", stroke="#FFFFFF", strokeWidth=2)
    demo_points = base.transform_filter("datum.isDemoWeek == true").mark_point(filled=True, size=190, color="#1E88E5", stroke="#0B4F8A", strokeWidth=2)
    label_halo = base.mark_text(
        fontSize=11,
        fontWeight="bold",
        color="#FFFFFF",
        stroke="#FFFFFF",
        strokeWidth=4,
    ).encode(
        text="valueLabel:N",
        yOffset="labelYOffset:Q",
    )
    labels = base.mark_text(fontSize=11, fontWeight="bold", color="#1289E8").encode(
        text="valueLabel:N",
        yOffset="labelYOffset:Q",
    )
    avg_layers = None
    if len(plot_data) > 1:
        avg_rule = alt.Chart(pd.DataFrame({"avg": [avg_value], "label": [f"{len(plot_data)}-week avg (${avg_value:,.2f})"]})).mark_rule(
            color="#8C8C8C",
            strokeDash=[6, 4],
            strokeWidth=2,
        ).encode(y="avg:Q", tooltip=[alt.Tooltip("label:N", title="Average")])
        avg_label_data = pd.DataFrame(
            {
                "avg": [avg_value],
                "label": [f"{len(plot_data)}-week avg (${avg_value:,.2f})"],
                "weekAxisLabel": [week_label_order[-1]],
            }
        )
        avg_label = alt.Chart(avg_label_data).mark_text(
            align="right",
            dx=-8,
            dy=-8,
            color="#4D4D4D",
            fontSize=12,
        ).encode(
            x=alt.X("weekAxisLabel:N", sort=week_label_order),
            y="avg:Q",
            text="label:N",
        )
        avg_layers = avg_rule + avg_label

    chart_layers = area + x_crosshair + y_crosshair + line + points + demo_points + hover_point + label_halo + labels + hover_targets
    if avg_layers is not None:
        chart_layers = area + avg_layers + x_crosshair + y_crosshair + line + points + demo_points + hover_point + label_halo + labels + hover_targets

    if len(plot_data) == 1:
        st.info("Only 1 week of data in the selected range — expand the date range to see trends.")
    else:
        st.altair_chart(chart_layers.properties(height=height), use_container_width=True)


def style_weekly_performance_table(table):
    return table.style.format(
        {
            "Avg $ / Whse": "${:,.0f}",
            "WoW Change": "{:+.0%}",
            "Unit Sales": "{:,.0f}",
            "Dollar Sales": "${:,.0f}",
        },
        na_rep="-",
    )


def stacked_area_chart(data, x, y, color, metric_label=None, height=340):
    if data.empty:
        st.info("No data for the selected filters.")
        return

    label = metric_label or METRIC_LABELS.get(y, y)
    plot_data = data.copy()
    plot_data["_metric_definition"] = metric_definition(y)
    chart = (
        alt.Chart(plot_data)
        .mark_area()
        .encode(
            x=alt.X(f"{x}:T", title=DIMENSION_LABELS.get(x, x)),
            y=alt.Y(f"{y}:Q", stack="normalize", title=metric_axis_title(y, label), axis=alt.Axis(format="%")),
            color=alt.Color(f"{color}:N", title=DIMENSION_LABELS.get(color, color)),
            tooltip=[
                alt.Tooltip(f"{x}:T", title=DIMENSION_LABELS.get(x, x)),
                alt.Tooltip(f"{color}:N", title=DIMENSION_LABELS.get(color, color)),
                alt.Tooltip("dollarSales:Q", title="Dollar Sales", format=",.2f"),
                alt.Tooltip(f"{y}:Q", title=label, format=".1%"),
                alt.Tooltip("_metric_definition:N", title="Metric definition"),
            ],
        )
        .properties(height=height)
    )
    st.altair_chart(chart, use_container_width=True)


def render_insights(items):
    clean_items = [item for item in items if item]
    if not clean_items:
        return
    with st.container(border=True):
        st.markdown("**Insights**")
        for item in clean_items:
            st.markdown(f"- {item}")


def overview_insights(filtered):
    insights = []
    if filtered.empty:
        return insights
    product_velocity = weekly_velocity(filtered, "commonName").dropna(subset=["dollarsPerStorePerWeek"])
    top_revenue = aggregate(filtered, "commonName", "dollarSales", "sum", 1)
    if not product_velocity.empty:
        best = product_velocity.sort_values("dollarsPerStorePerWeek", ascending=False).iloc[0]
        insights.append(f"Best product by $ / Store / Week is {best['commonName']} at {currency(best['dollarsPerStorePerWeek'])}.")
    if not top_revenue.empty:
        row = top_revenue.iloc[0]
        insights.append(f"Largest revenue contributor is {row['commonName']} with {currency(row['dollarSales'])} in selected sales.")
    if "venue" in filtered:
        insights.append(f"The current view includes {filtered['commonName'].nunique():,} active products across {filtered['venue'].nunique():,} regions.")
    return insights


def weekly_insights(performance_data):
    insights = []
    if performance_data.empty:
        return insights
    latest = performance_data.sort_values("weekStart").iloc[-1]
    latest_text = f"Latest week ended {latest['weekEnd'].date()} at {currency(latest['weeklyDollarsPerStorePerWeek'])} per warehouse selling."
    if pd.notna(latest.get("wowPct")):
        latest_text += f" WoW changed {latest['wowPct']:+.0%}."
    insights.append(latest_text)
    best = performance_data.sort_values("weeklyDollarsPerStorePerWeek", ascending=False).iloc[0]
    insights.append(f"Best week in this view was week ended {best['weekEnd'].date()} at {currency(best['weeklyDollarsPerStorePerWeek'])}.")
    demo_weeks = performance_data[performance_data["isDemoWeek"].fillna(False)]
    if not demo_weeks.empty:
        demo = demo_weeks.sort_values("weeklyDollarsPerStorePerWeek", ascending=False).iloc[0]
        insights.append(f"Demo week appears in this range; strongest demo week was {demo['weekEnd'].date()} at {currency(demo['weeklyDollarsPerStorePerWeek'])}.")
    red_count = int((performance_data["performance"] == "Red").sum())
    if red_count:
        insights.append(f"{red_count} week(s) are below the red threshold in the selected period.")
    return insights


def region_insights(filtered):
    insights = []
    if filtered.empty:
        return insights
    region_velocity = weekly_velocity(filtered, "venue").dropna(subset=["dollarsPerStorePerWeek"])
    if not region_velocity.empty:
        best = region_velocity.sort_values("dollarsPerStorePerWeek", ascending=False).iloc[0]
        insights.append(f"Top region by $ / Store / Week is {best['venue']} at {currency(best['dollarsPerStorePerWeek'])}.")
        unit_best = region_velocity.dropna(subset=["unitVelocity"]).sort_values("unitVelocity", ascending=False).iloc[0]
        insights.append(f"Top region by unit velocity is {unit_best['venue']} at {number(unit_best['unitVelocity'])} units per active week.")
    return insights


def product_region_insights(matrix_table, year_summary, group_summary):
    insights = []
    if not matrix_table.empty:
        stacked = matrix_table.stack().dropna()
        if not stacked.empty:
            best_idx = stacked.idxmax()
            worst_idx = stacked.idxmin()
            insights.append(f"Best product-region cell is {best_idx[1]} in {best_idx[2]} at {currency(stacked.max())}.")
            insights.append(f"Weakest product-region cell is {worst_idx[1]} in {worst_idx[2]} at {currency(stacked.min())}.")
    if not year_summary.empty:
        year_values = year_summary.stack().dropna()
        if not year_values.empty:
            best_idx = year_values.idxmax()
            insights.append(f"Best product-year result is {best_idx[1]} in {best_idx[2]} at {currency(year_values.max())}.")
    if not group_summary.empty:
        best_group = group_summary.sort_values("dollarsPerStorePerWeek", ascending=False).iloc[0]
        insights.append(f"Strongest group is {best_group['productGroup']} at {currency(best_group['dollarsPerStorePerWeek'])} per store per week.")
    return insights


def inventory_insights(wos, latest_week):
    insights = []
    if latest_week is not None:
        insights.append(f"Inventory is using latest available week: {latest_week.date()}.")
    if wos.empty:
        return insights
    lowest = wos.sort_values("weeksOfSupply").iloc[0]
    insights.append(f"Lowest supply item is {lowest['commonName']} at {lowest['weeksOfSupply']:.1f} weeks of supply.")
    low_count = int((wos["weeksOfSupply"] < 2).sum())
    if low_count:
        insights.append(f"{low_count} item(s) are under 2 weeks of supply and need attention.")
    zero_inventory = int((wos["inventoryOnHand"].fillna(0) == 0).sum())
    if zero_inventory:
        insights.append(f"{zero_inventory} item(s) show zero inventory in this view.")
    return insights


def custom_export_insights(filtered):
    insights = []
    insights.append(f"Filtered export contains {len(filtered):,} rows.")
    if not filtered.empty and "weekStart" in filtered:
        weeks = filtered["weekStart"].dropna()
        if not weeks.empty:
            insights.append(f"Export date range is {weeks.min().date()} to {weeks.max().date()}.")
    if "commonName" in filtered:
        insights.append(f"Export includes {filtered['commonName'].nunique():,} products.")
    if "venue" in filtered:
        insights.append(f"Export includes {filtered['venue'].nunique():,} regions.")
    return insights


def available_years(data):
    return sorted(data["weekStart"].dropna().dt.year.astype(int).unique().tolist(), reverse=True)


def available_months(data, year):
    months = data.loc[data["weekStart"].dt.year == year, "weekStart"].dropna().dt.month.astype(int).unique().tolist()
    return sorted(months, reverse=True)


def month_name(month_number):
    return calendar.month_name[int(month_number)]


def month_bounds(year, month):
    start = pd.Timestamp(year=int(year), month=int(month), day=1)
    end = start + pd.offsets.MonthEnd(0)
    return start, end


def filter_month_range(data, start_year, start_month, end_year, end_month):
    start, _ = month_bounds(start_year, start_month)
    _, end = month_bounds(end_year, end_month)
    if start > end:
        return data.iloc[0:0], start, end
    return data[(data["weekStart"] >= start) & (data["weekStart"] <= end)], start, end


def apply_filters(df):
    filtered = df.copy()
    with st.sidebar:
        st.header("Filters")

        items = sorted(filtered["commonName"].dropna().unique())
        selected_items = st.multiselect("Items", items, default=[])
        if selected_items:
            filtered = filtered[filtered["commonName"].isin(selected_items)]

        week_starts = filtered["weekStart"].dropna().drop_duplicates().sort_values()
        weeks = pd.DataFrame({
            "weekStart": week_starts.values,
            "weekEnd": week_starts.values + pd.Timedelta(days=6),
        })
        if not weeks.empty:
            week_labels = {
                row.weekStart: f"{row.weekStart.strftime('%b %d')} – {row.weekEnd.strftime('%b %d, %Y')}"
                for row in weeks.itertuples()
            }
            week_starts = list(week_labels.keys())
            latest_month_start = weeks["weekStart"].max().to_pydatetime().replace(day=1)
            default_from = next((w for w in week_starts if w.to_pydatetime() >= latest_month_start), week_starts[0])
            default_to = week_starts[-1]
            from_week = st.selectbox("Start week", week_starts, index=week_starts.index(default_from), format_func=lambda w: week_labels[w], key="global_from_week")
            to_week = st.selectbox("End week", week_starts, index=week_starts.index(default_to), format_func=lambda w: week_labels[w], key="global_to_week")
            if from_week > to_week:
                st.error("'From' week must be before 'To' week.")
            else:
                filtered = filtered[(filtered["weekStart"] >= from_week) & (filtered["weekStart"] <= to_week)]
                st.caption(f"{week_labels[from_week].split('–')[0].strip()} to {week_labels[to_week].split('–')[1].strip()}")

        venues = sorted(filtered["venue"].dropna().unique())
        selected_venues = st.multiselect("Venues", venues, default=[])
        if selected_venues:
            filtered = filtered[filtered["venue"].isin(selected_venues)]

    return filtered


def render_overview(filtered):
    valid_dates = filtered["weekStart"].dropna()
    date_text = "No dates selected"
    if not valid_dates.empty:
        date_text = f"{valid_dates.min().date()} to {valid_dates.max().date()}"

    active_sales = filtered[filtered["dollarSales"].fillna(0) > 0]
    velocity_by_product = weekly_velocity(filtered, "commonName")
    avg_unit_velocity = velocity_by_product["unitVelocity"].mean()
    dollars_per_store_per_week = filtered["dollarSales"].sum() / filtered["warehousesSelling"].sum() if filtered["warehousesSelling"].sum() else pd.NA

    st.caption(f"Selected date range: {date_text} • {len(filtered):,} filtered rows")
    st.markdown("**Primary metric: $ per Store per Week**")
    metric_grid(
        [
            ("$ / Store / Week", compact_currency(dollars_per_store_per_week), metric_definition("dollarsPerStorePerWeek")),
            ("Revenue", compact_currency(filtered["dollarSales"].sum()), metric_definition("dollarSales")),
            ("Units", compact_number(filtered["unitSales"].sum()), metric_definition("unitSales")),
            ("Active Items", number(active_sales["commonName"].nunique()), f"{active_sales['venue'].nunique():,} active regions"),
            ("Avg Unit Velocity", compact_number(avg_unit_velocity), metric_definition("unitVelocity")),
        ]
    )
    st.caption("Profit is not shown yet because the workbook does not include COGS, unit cost, or margin data.")


def render_product_performance(filtered):
    top_products = aggregate(filtered, "commonName", "dollarSales", "sum", 15)
    product_velocity = weekly_velocity(filtered, "commonName").sort_values("dollarsPerStorePerWeek", ascending=False).head(15)
    product_unit_velocity = weekly_velocity(filtered, "commonName").sort_values("unitVelocity", ascending=False).head(15)

    st.subheader("Product Performance")
    with st.container(border=True):
        st.markdown("**Top Products by $ per Store per Week**")
        sorted_bar_chart(product_velocity, "commonName", "dollarsPerStorePerWeek", "$ per store per week", height=460)

    product_left, product_right = st.columns(2)
    with product_left:
        with st.container(border=True):
            st.markdown("**Top Products by Dollar Sales**")
            sorted_bar_chart(top_products, "commonName", "dollarSales", height=360)
    with product_right:
        with st.container(border=True):
            st.markdown("**Top Products by Unit Velocity**")
            sorted_bar_chart(product_unit_velocity, "commonName", "unitVelocity", "Units per active week", height=360)

    render_insights(overview_insights(filtered))


def render_weekly_trends(filtered):
    product_velocity = weekly_velocity(filtered, "commonName").sort_values("dollarsPerStorePerWeek", ascending=False).head(15)

    st.subheader("Weekly Trends")
    with st.container(border=True):
        st.markdown("**Weekly Sales Performance**")
        st.caption(
            "Week-by-week average dollar sales per warehouse selling. Demo weeks are highlighted in blue when the source workbook marks them."
        )
        available_products = sorted(filtered["commonName"].dropna().unique())
        if available_products:
            latest_week = filtered["weekStart"].dropna().max()
            latest_product_velocity = pd.DataFrame()
            if pd.notna(latest_week):
                latest_rows = filtered[filtered["weekStart"] == latest_week]
                latest_product_velocity = weekly_velocity(latest_rows, "commonName").sort_values("dollarsPerStorePerWeek", ascending=False)
            if not latest_product_velocity.empty:
                default_product = latest_product_velocity.iloc[0]["commonName"]
            else:
                default_product = product_velocity.iloc[0]["commonName"] if not product_velocity.empty else available_products[0]
            default_index = available_products.index(default_product) if default_product in available_products else 0

            control_left, control_right = st.columns([1.4, 1])
            selected_product = control_left.selectbox("Product", available_products, index=default_index, key="weekly_velocity_product")
            product_rows = filtered[filtered["commonName"] == selected_product]
            region_options = ["All regions"] + sorted(product_rows["venue"].dropna().unique().tolist())
            selected_region = control_right.selectbox("Region", region_options, key="weekly_velocity_region")

            weekly_source = filtered if selected_region == "All regions" else filtered[filtered["venue"] == selected_region]
            weekly_data = weekly_product_velocity(weekly_source, selected_product)
            if not weekly_data.empty:
                weekly_data = weekly_data.sort_values("weekStart")
                chart_data = weekly_data.copy()
                period_text = f"{chart_data['weekStart'].min().date().strftime('%b %d, %Y')} to {chart_data['weekEnd'].max().date().strftime('%b %d, %Y')}: {len(chart_data)} week(s) with data"
                st.caption(period_text)
                if chart_data.empty:
                    st.info("No weekly data exists for this product, region, and selected period.")
                    return
                region_label = selected_region if selected_region != "All regions" else "All selected regions"
                performance_data = weekly_performance_data(chart_data, selected_product, region_label)
                chart_height = min(max(220, len(performance_data) * 18), 380)
                weekly_performance_chart(performance_data, selected_product, height=chart_height)

                st.markdown("**Weekly Performance Table**")
                table = performance_data.copy()
                table["Week Ending"] = table["weekEnd"].dt.strftime("%m/%d/%Y")
                table["Region"] = region_label
                display = table[["Week Ending", "Region", "weeklyDollarsPerStorePerWeek", "wowPct", "performance", "weeklyVelocity", "dollarSales"]].rename(
                    columns={
                        "weeklyDollarsPerStorePerWeek": "Avg $ / Whse",
                        "wowPct": "WoW Change",
                        "performance": "Performance",
                        "weeklyVelocity": "Unit Sales",
                        "dollarSales": "Dollar Sales",
                    }
                )
                table_height = min(38 + 35 * len(display), 400)
                st.dataframe(style_weekly_performance_table(display), use_container_width=True, height=table_height)
                render_insights(weekly_insights(performance_data))
            else:
                st.info("No weekly velocity data for the selected product, region, and filters.")
        else:
            st.info("No product data for the selected filters.")


def render_region_analysis(filtered):
    region_velocity = weekly_velocity(filtered, "venue").sort_values("dollarsPerStorePerWeek", ascending=False).head(10)
    region_unit_velocity = weekly_velocity(filtered, "venue").sort_values("unitVelocity", ascending=False).head(10)

    st.subheader("Region Analysis")
    region_left, region_right = st.columns(2)
    with region_left:
        with st.container(border=True):
            st.markdown("**Top Regions by $ per Store per Week**")
            sorted_bar_chart(region_velocity, "venue", "dollarsPerStorePerWeek", "$ per store per week", height=320)
    with region_right:
        with st.container(border=True):
            st.markdown("**Top Regions by Unit Velocity**")
            sorted_bar_chart(region_unit_velocity, "venue", "unitVelocity", "Units per active week", height=320)

    with st.container(border=True):
        st.markdown("**Product $ per Store per Week by Region**")
        available_regions = sorted(filtered["venue"].dropna().unique())
        if available_regions:
            selected_region = st.selectbox("Region", available_regions, key="product_velocity_region")
            region_product_velocity = product_velocity_for_region(filtered, selected_region, limit=15)
            sorted_bar_chart(region_product_velocity, "commonName", "dollarsPerStorePerWeek", "$ per store per week", height=420)
        else:
            st.info("No region data for the selected filters.")

    render_insights(region_insights(filtered))


def chart_manager():
    if "charts" not in st.session_state:
        st.session_state.charts = DEFAULT_CHARTS.copy()
    repeated_default_titles = {
        "Unit Sales Trend",
        "$ per Store per Week by Product",
        "$ per Store per Week by Region",
        "Inventory by Item",
    }
    st.session_state.charts = [chart for chart in st.session_state.charts if chart.get("title") not in repeated_default_titles]

    with st.expander("Chart manager", expanded=False):
        cols = st.columns([1.4, 1, 1, 1, 0.8, 0.7])
        title = cols[0].text_input("Title", value="New Chart")
        chart_type = cols[1].selectbox("Type", ["Bar", "Line"])
        dimension = cols[2].selectbox("Group by", list(DIMENSION_LABELS), format_func=lambda value: DIMENSION_LABELS[value])
        metric = cols[3].selectbox("Metric", list(METRIC_LABELS), format_func=lambda value: METRIC_LABELS[value])
        aggregation = cols[4].selectbox("Agg", ["sum", "mean", "count"])
        limit = cols[5].number_input("Limit", min_value=0, max_value=50, value=12, step=1)
        if st.button("Add chart", use_container_width=True):
            st.session_state.charts.append(
                {
                    "title": title,
                    "type": chart_type,
                    "dimension": dimension,
                    "metric": metric,
                    "aggregation": aggregation,
                    "limit": int(limit) or None,
                }
            )
            st.rerun()


def render_chart(df, chart, index):
    metric = chart["metric"]
    dimension = chart["dimension"]
    if metric in {"unitVelocity", "dollarVelocity", "dollarsPerStorePerWeek", "velocity"}:
        data = weekly_operating_trends(df) if dimension == "weekStart" else weekly_velocity(df, dimension)
        if chart.get("limit") and dimension != "weekStart":
            sort_metric = "unitVelocity" if metric == "velocity" else metric
            data = data.sort_values(sort_metric, ascending=False).head(chart.get("limit"))
    else:
        data = aggregate(df, dimension, metric, chart["aggregation"], chart.get("limit"))
    with st.container(border=True):
        cols = st.columns([1, 0.08])
        cols[0].subheader(chart["title"])
        if cols[1].button("×", key=f"remove-{index}", help="Remove chart", use_container_width=True):
            st.session_state.charts.pop(index)
            st.rerun()
        st.caption(f"{DIMENSION_LABELS[chart['dimension']]} by {METRIC_LABELS[chart['metric']]} ({chart['aggregation']})")
        if chart["type"] == "Line":
            line_chart(data, chart["dimension"], chart["metric"])
        else:
            sorted_bar_chart(data, chart["dimension"], chart["metric"])


def style_inventory_watchlist(inventory_table):
    def style_row(row):
        if pd.notna(row.get("Weeks of Supply")) and row.get("Weeks of Supply") < 2:
            return ["background-color: #F4CCCC; color: #8A1F1F; font-weight: 600" for _ in row]
        return ["" for _ in row]

    return inventory_table.style.format(
        {
            "Inventory": "{:,.0f}",
            "Unit Velocity": "{:,.0f}",
            "Weeks of Supply": "{:,.1f}",
            "Coverage": "{:.1%}",
        },
        na_rep="-",
    ).apply(style_row, axis=1)


PRODUCT_GROUP_KEYWORDS = {
    "Protein and Bowls": [
        "organic chicken meatballs",
        "org chicken meatballs",
        "simply roasted chicken",
        "roasted chicken breast",
        "tuscan style roasted chicken",
        "chipotle chicken bowl",
        "cilantro lime chicken bowl",
        "turkey bolognese power bowl",
        "japanese bbq chicken",
        "chicken veggies w parm",
        "sweet and sour chicken",
        "sweet smoky gf sirloin",
    ],
    "Veggie Sides": [
        "red white and blue veggies",
        "rainbow carrots",
        "roasted root",
        "root veg",
        "brussel",
        "veggies and quinoa",
        "veg quinoa",
        "roasted veg quino",
        "haks roasted veg quino",
        "herb roasted tuscan veggies",
        "roasted tuscan veg",
        "farmers market",
        "farmer market",
        "harvest veggies",
        "roasted harvest",
        "broccoli brussels",
        "rainbow carrot",
    ],
    "Soups and Broths": [
        "protein bone broth",
        "immunity bone broth",
        "beef and veggie soup",
        "beefveggie soup",
        "tomato basil soup",
        "creamed spinach",
        "turkey gravy",
    ],
}


def normalized_text(value):
    return " ".join(str(value or "").lower().replace("&", " and ").split())


def product_group(product_name):
    text = normalized_text(product_name)
    for group, keywords in PRODUCT_GROUP_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return group
    return "Unmapped"


def velocity_threshold_status(group, value):
    if pd.isna(value):
        return "Missing"
    if group == "Protein and Bowls":
        if value >= 1200:
            return "Green"
        if value >= 1000:
            return "Yellow"
        return "Red"
    if group in {"Veggie Sides", "Soups and Broths"}:
        if value >= 1000:
            return "Green"
        if value >= 800:
            return "Yellow"
        return "Red"
    return "Missing"


def velocity_cell_style(value, group):
    status = velocity_threshold_status(group, value)
    if status == "Green":
        return "background-color: #D9EAD3; color: #1F5E2E; font-weight: 600"
    if status == "Yellow":
        return "background-color: #FFF2CC; color: #7A5A00; font-weight: 600"
    if status == "Red":
        return "background-color: #F4CCCC; color: #8A1F1F; font-weight: 600"
    return "background-color: #F3F4F6; color: #6B7280"


def mapped_product_rows(filtered):
    mapped = filtered.copy()
    mapped["productGroup"] = mapped["commonName"].map(product_group)
    return mapped[mapped["productGroup"] != "Unmapped"]


def grouped_metric_summary(filtered):
    mapped = mapped_product_rows(filtered)
    if mapped.empty:
        return pd.DataFrame(columns=["productGroup", "dollarsPerStorePerWeek", "unitVelocity", "dollarSales", "unitSales"])
    return weekly_velocity(mapped, "productGroup").sort_values("dollarsPerStorePerWeek", ascending=False)


def grouped_product_region_matrix(filtered, matrix_metric):
    mapped = mapped_product_rows(filtered)
    if mapped.empty:
        return pd.DataFrame()

    if matrix_metric in {"unitVelocity", "dollarVelocity", "dollarsPerStorePerWeek"}:
        matrix = weekly_velocity(mapped, ["productGroup", "commonName", "venue"])
        values = matrix_metric
        aggfunc = "mean"
    else:
        matrix = mapped
        values = matrix_metric
        aggfunc = "mean" if matrix_metric == "coverageRate" else "sum"

    matrix_table = matrix.pivot_table(
        index=["productGroup", "commonName"],
        columns="venue",
        values=values,
        aggfunc=aggfunc,
    ).sort_index()
    return matrix_table


def product_year_summary_matrix(filtered):
    mapped = mapped_product_rows(filtered).dropna(subset=["weekStart"])
    if mapped.empty:
        return pd.DataFrame()

    mapped = mapped.copy()
    mapped["year"] = pd.to_datetime(mapped["weekStart"], errors="coerce").dt.year
    mapped = mapped.dropna(subset=["year"])
    if mapped.empty:
        return pd.DataFrame()

    yearly = weekly_velocity(mapped, ["productGroup", "commonName", "year"])
    matrix_table = yearly.pivot_table(
        index=["productGroup", "commonName"],
        columns="year",
        values="dollarsPerStorePerWeek",
        aggfunc="mean",
    ).sort_index()
    matrix_table.columns = [str(int(column)) for column in matrix_table.columns]
    return matrix_table


def style_grouped_velocity_matrix(matrix_table, matrix_metric):
    if matrix_metric == "dollarsPerStorePerWeek":
        def style_row(row):
            group = row.name[0] if isinstance(row.name, tuple) else ""
            return [velocity_cell_style(value, group) for value in row]
        return matrix_table.style.format("${:,.0f}", na_rep="-").apply(style_row, axis=1)

    if matrix_metric in CURRENCY_METRICS:
        return matrix_table.style.format("${:,.0f}", na_rep="-")
    if matrix_metric in PERCENT_METRICS:
        return matrix_table.style.format("{:.1%}", na_rep="-")
    return matrix_table.style.format("{:,.0f}", na_rep="-")


def render_product_region_analysis(filtered):
    st.subheader("Product x Region Analysis")
    st.caption("Compare product performance across Costco regions, then roll products up into the main business groups.")

    matrix_filtered = filtered.copy()

    with st.container(border=True):
        st.markdown("**Product x Region Matrix**")
        valid_weeks = matrix_filtered["weekStart"].dropna().sort_values()
        if not valid_weeks.empty:
            start, end = valid_weeks.min(), valid_weeks.max()
            period_text = f"{start.date()} to {end.date()}"
        else:
            st.info("No week dates are available for Product x Region filtering.")
            period_text = "No dates selected"

        matrix_metric = st.selectbox(
            "Matrix metric",
            ["dollarsPerStorePerWeek", "unitVelocity", "dollarSales", "unitSales", "inventoryOnHand", "coverageRate"],
            format_func=lambda value: METRIC_LABELS[value],
            key="grouped_matrix_metric",
        )
        st.caption(f"Product x Region period: {period_text}.")
        if matrix_metric == "dollarsPerStorePerWeek":
            st.caption(
                "$ per Store per Week by product group and region. Protein and Bowls: green >= $1,200, yellow >= $1,000, red below $1,000. "
                "Veggie Sides and Soups/Broths: green >= $1,000, yellow >= $800, red below $800."
            )
        else:
            st.caption(metric_definition(matrix_metric))
        matrix_table = grouped_product_region_matrix(matrix_filtered, matrix_metric)
        if matrix_table.empty:
            st.info("No mapped products found for the selected filters.")
        else:
            matrix_height = min(38 + 35 * len(matrix_table), 600)
            st.dataframe(style_grouped_velocity_matrix(matrix_table, matrix_metric), use_container_width=True, height=matrix_height)

    with st.container(border=True):
        st.markdown("**Product Year Summary**")
        st.caption(
            "Overall $ per Store per Week by product and year across all selected regions. "
            "The same group thresholds are applied: Protein and Bowls green >= $1,200, yellow >= $1,000; "
            "Veggie Sides and Soups/Broths green >= $1,000, yellow >= $800."
        )
        year_summary = product_year_summary_matrix(matrix_filtered)
        if year_summary.empty:
            st.info("No mapped yearly product data found for the selected filters.")
        else:
            year_options = ["All years"] + list(year_summary.columns)
            selected_summary_year = st.selectbox(
                "Summary year",
                year_options,
                key="product_year_summary_year",
                help="Choose one year to focus the Product Year Summary, or keep all years visible.",
            )
            display_year_summary = year_summary if selected_summary_year == "All years" else year_summary[[selected_summary_year]]
            st.dataframe(style_grouped_velocity_matrix(display_year_summary, "dollarsPerStorePerWeek"), use_container_width=True, height=420)

    with st.container(border=True):
        st.markdown("**Group Summary**")
        st.caption("Grouped rollup by Protein and Bowls, Veggie Sides, and Soups/Broths using $ per Store per Week.")
        group_summary = grouped_metric_summary(matrix_filtered)
        if group_summary.empty:
            st.info("No mapped products found for the selected filters.")
        else:
            sorted_bar_chart(group_summary, "productGroup", "dollarsPerStorePerWeek", "$ per store per week", height=260)

    render_insights(product_region_insights(matrix_table, year_summary, group_summary))


def inventory_watchlist(filtered, mode):
    if mode == "Latest available week":
        latest_week = filtered["weekStart"].dropna().max()
        if pd.isna(latest_week):
            return pd.DataFrame(), None
        latest_rows = filtered[filtered["weekStart"] == latest_week]
        latest_inventory = (
            latest_rows.groupby("commonName", dropna=False)
            .agg(
                inventoryOnHand=("inventoryOnHand", "sum"),
                coverageRate=("coverageRate", "mean"),
            )
            .reset_index()
        )
        velocity = weekly_velocity(filtered, "commonName")[["commonName", "unitVelocity"]]
        watchlist = latest_inventory.merge(velocity, on="commonName", how="left")
        watchlist["weeksOfSupply"] = watchlist["inventoryOnHand"] / watchlist["unitVelocity"].replace({0: pd.NA})
        return watchlist.dropna(subset=["weeksOfSupply"]).sort_values("weeksOfSupply").head(15), latest_week

    watchlist = weeks_of_supply(filtered).dropna(subset=["weeksOfSupply"]).sort_values("weeksOfSupply").head(15)
    return watchlist, None


def render_inventory_health(filtered):
    st.subheader("Inventory and Supply Health")
    with st.container(border=True):
        st.subheader("Inventory Watchlist")
        inventory_mode = st.selectbox(
            "Inventory period",
            ["Latest available week", "Selected date period"],
            key="inventory_period_mode",
            help="Latest available week uses the newest inventory rows after sidebar filters. Selected date period summarizes inventory over the full filtered period.",
        )
        wos, latest_week = inventory_watchlist(filtered, inventory_mode)
        if latest_week is not None:
            st.caption(f"Using latest inventory week: {latest_week.date()}. Weeks of Supply uses latest inventory divided by unit velocity over the selected sidebar period.")
        else:
            st.caption("Using the selected sidebar date period. Rows under 2 weeks are highlighted.")
        inventory_table = wos[["commonName", "inventoryOnHand", "unitVelocity", "weeksOfSupply", "coverageRate"]].rename(
            columns={
                "commonName": "Item",
                "inventoryOnHand": "Inventory",
                "unitVelocity": "Unit Velocity",
                "weeksOfSupply": "Weeks of Supply",
                "coverageRate": "Coverage",
            }
        ) if not wos.empty else pd.DataFrame(columns=["Item", "Inventory", "Unit Velocity", "Weeks of Supply", "Coverage"])
        st.dataframe(style_inventory_watchlist(inventory_table), use_container_width=True, height=280)
        st.caption("Zeros usually mean the source data has zero inventory/sales for that product after filters, or the denominator is unavailable for that selected period.")

    render_insights(inventory_insights(wos, latest_week))


def render_custom_analysis(filtered):
    st.subheader("Custom Analysis")
    st.caption("Sidebar filters apply to the whole dashboard. Use this section for additional custom charts, matrix views, and row-level export.")

    chart_manager()

    left, right = st.columns(2)
    for index, chart in enumerate(st.session_state.charts):
        with left if index % 2 == 0 else right:
            render_chart(filtered, chart, index)


    st.subheader("Filtered rows")
    visible_cols = [
        "weekStart",
        "venue",
        "commonName",
        "unitSales",
        "dollarSales",
        "inventoryOnHand",
        "warehousesSelling",
        "numberOfWarehouses",
        "coverageRate",
        "avgPrice",
        "productTab",
        "isDemoWeek",
    ]
    st.dataframe(filtered[[col for col in visible_cols if col in filtered]], use_container_width=True, height=420)
    st.download_button(
        "Download filtered CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        "costco_filtered_rows.csv",
        "text/csv",
    )
    render_insights(custom_export_insights(filtered))


def main():
    config = load_config()
    df, source_label, source_files = load_dashboard_data(config)

    if df.empty:
        st.error("No usable rows were loaded from the selected data source.")
        st.stop()

    filtered = apply_filters(df)

    st.title("Chef Haks Dashboard")
    st.caption(f"{len(df):,} rows loaded from {source_label}")
    if df.attrs.get("load_errors"):
        with st.expander("Skipped tabs", expanded=False):
            st.write(df.attrs["load_errors"])
    if df.attrs.get("load_warnings"):
        with st.expander("Data load warnings", expanded=True):
            st.warning("Some rows or tabs needed cleanup during import. Review these before relying on the dashboard.")
            st.write(df.attrs["load_warnings"])
    overview_tab, weekly_tab, region_tab, product_region_tab, inventory_tab, custom_tab = st.tabs(
        ["Overview", "Weekly Trends", "Region Analysis", "Product x Region", "Inventory", "Custom / Export"]
    )

    with overview_tab:
        render_overview(filtered)
        render_product_performance(filtered)

    with weekly_tab:
        render_weekly_trends(filtered)

    with region_tab:
        render_region_analysis(filtered)

    with product_region_tab:
        render_product_region_analysis(filtered)

    with inventory_tab:
        render_inventory_health(filtered)

    with custom_tab:
        render_custom_analysis(filtered)


if __name__ == "__main__":
    main()
