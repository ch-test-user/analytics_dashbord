import json
import mimetypes
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "4173"))


def json_response(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def run_refresh(extra_config=None):
    env = os.environ.copy()
    extra_config = extra_config or {}
    if extra_config.get("sourceWorkbook"):
        env["COSTCO_SOURCE_WORKBOOK"] = extra_config["sourceWorkbook"]
    if extra_config.get("sourceSheet"):
        env["COSTCO_SOURCE_SHEET"] = extra_config["sourceSheet"]
    if extra_config.get("dataset"):
        env["COSTCO_DATASET"] = extra_config["dataset"]

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "export_data.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Refresh failed")
    return {"stdout": result.stdout.strip(), "stderr": result.stderr.strip()}


def dashboard_config():
    return json.loads((ROOT / "app.config.json").read_text())


def dataset_id(value=None):
    config = dashboard_config()
    selected = value or config.get("defaultDataset", "deli")
    if selected not in config.get("datasets", {selected: {}}):
        raise ValueError(f"Unknown dataset: {selected}")
    return selected


def data_path_for(dataset):
    config = dashboard_config()
    source = config.get("datasets", {}).get(dataset, {})
    return ROOT / source.get("outputData", f"public/data/{dataset}.json")


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            json_response(self, 200, dashboard_config())
            return

        if parsed.path == "/api/data":
            try:
                dataset = dataset_id(parse_qs(parsed.query).get("dataset", [None])[0])
            except ValueError as exc:
                json_response(self, 400, {"ok": False, "error": str(exc)})
                return
            data_path = data_path_for(dataset)
            if not data_path.exists():
                run_refresh({"dataset": dataset})
            data = json.loads(data_path.read_text())
            json_response(self, 200, data)
            return

        self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/refresh":
            json_response(self, 404, {"ok": False, "error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            request = json.loads(body or "{}")
            request["dataset"] = dataset_id(request.get("dataset"))
            result = run_refresh(request)
            json_response(self, 200, {"ok": True, **result})
        except Exception as exc:
            json_response(self, 500, {"ok": False, "error": str(exc)})

    def serve_static(self, request_path):
        if request_path == "/":
            request_path = "/public/index.html"

        relative = unquote(request_path).lstrip("/")
        full_path = (ROOT / relative).resolve()
        if ROOT not in full_path.parents and full_path != ROOT:
            self.send_error(403)
            return

        if not full_path.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(full_path.name)[0] or "application/octet-stream"
        body = full_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    run_refresh({"dataset": dataset_id()})
    server = ThreadingHTTPServer(("127.0.0.1", PORT), DashboardHandler)
    print(f"Costco dashboard running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
