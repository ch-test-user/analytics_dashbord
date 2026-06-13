# Costco Consumption Dashboard

Python-managed local dashboard for the Costco weekly consumption workbook.

## Run

One-command setup and run:

```bash
cd "/Users/gaganmalhotra/Documents/Chef Haks Dashboard"
./setup_and_run.sh
```

This creates or repairs `.venv`, installs dependencies, verifies Streamlit, and starts the app at `http://localhost:8501`.

To use another port:

```bash
PORT=8502 ./setup_and_run.sh
```

Recommended Streamlit app:

```bash
python3 -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

Then open the local URL Streamlit prints, usually `http://localhost:8501`.

Codex bundled Python setup:

```bash
/Users/gaganmalhotra/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m pip install -r requirements.txt
/Users/gaganmalhotra/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m streamlit run streamlit_app.py
```

## Update Data

The dashboard now uses one data source only: the Google Sheet configured in `app.config.json`.

- `googleSheetUrl`: the Google Sheet or Google-hosted Excel workbook to load.
- `googleCredentialsPath`: the service-account JSON key used for read-only access.

Each worksheet/tab is treated as a product tab. Click **Refresh data cache** in the sidebar after the Google Sheet changes or after editing the config.

### Google Sheets Access

For private sheets:

1. Share the Google Sheet with the service-account email.
2. Keep the service-account JSON file at the configured path.
3. Start the app with `./setup_and_run.sh`.

The dashboard reads the sheet only. It does not write changes back to Google Sheets.

## Metric Layer

Business logic lives in `app_core/metrics.py`:

- metric labels
- derived metric formulas
- aggregation logic
- velocity and weeks-of-supply calculations
- number/currency/percent formatting

Data ingestion lives in `app_core/data.py`:

- Google workbook column normalization
- product-tab parsing
- week-ending/date parsing
- source tab tracking

The Streamlit UI imports those modules, so new metrics added to the metric layer can be exposed in charts without duplicating formulas in the UI.

## Add Default Charts

Edit `app_core/metrics.py` and update `DEFAULT_CHARTS`. Charts support:

- `type`: `bar` or `line`
- `dimension`: for example `weekStart`, `venue`, `commonName`, `year`
- `metric`: for example `unitSales`, `dollarSales`, `inventoryOnHand`, `coverageRate`
- `aggregation`: `sum`, `mean`, or `count`
- `limit`: optional maximum number of groups for bar charts

## Streamlit Cloud Deployment

Use `streamlit_app.py` as the app entrypoint and deploy from GitHub on Streamlit Community Cloud.

Before deploying, add this secret in Streamlit Cloud **Advanced settings**. Do not commit the real service-account JSON file to GitHub.

```toml
[google_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@...iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
universe_domain = "googleapis.com"
```

The Google Sheet must be shared with the service account email.
