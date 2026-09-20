"""Capture reproducible SupplyPilot screenshots through the Edge DevTools protocol."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import websocket


CAPTURES: dict[str, dict[str, str]] = {
    # Product-story screenshots used by README and case documents.
    "control-tower-overview.png": {"page": "管理驾驶舱"},
    "demand-forecast-confidence.png": {"page": "需求预测"},
    "inventory-risk-heatmap.png": {"page": "管理驾驶舱", "_scroll_to": "Inventory Risk Heatmap"},
    "sku-360-detail.png": {"page": "管理驾驶舱", "detail": "MAT-B"},
    "inventory-projection.png": {"page": "库存控制台", "material": "MAT-B"},
    "procurement-action-center.png": {"page": "采购工作台"},
    "action-impact-validation.png": {
        "page": "库存控制台",
        "material": "MAT-A",
        "_scroll_to": "动作前后验证",
    },
    "ai-copilot-structured-response.png": {"page": "AI Copilot"},
    # Backward-compatible names referenced by older releases.
    "management-dashboard.png": {"page": "管理驾驶舱"},
    "forecast.png": {"page": "需求预测"},
    "atp-allocation.png": {"page": "共用料ATP与客户分配"},
    "transfer-optimization.png": {"page": "多工厂调拨优化"},
    "procurement-optimization.png": {"page": "采购成本与批量优化"},
    "scenario-optimization.png": {"page": "多情景库存成本优化"},
}


class DevTools:
    def __init__(self, websocket_url: str) -> None:
        self.connection = websocket.create_connection(
            websocket_url,
            timeout=10,
            origin="http://127.0.0.1",
        )
        self.command_id = 0

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        self.command_id += 1
        request: dict[str, Any] = {
            "id": self.command_id,
            "method": method,
            "params": params or {},
        }
        if session_id:
            request["sessionId"] = session_id
        self.connection.send(json.dumps(request))
        while True:
            response = json.loads(self.connection.recv())
            if response.get("id") != self.command_id:
                continue
            if "error" in response:
                raise RuntimeError(f"DevTools {method} failed: {response['error']}")
            return response.get("result", {})

    def close(self) -> None:
        self.connection.close()


def find_edge() -> Path:
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Microsoft Edge was not found in the standard locations.")


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def url_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "SupplyPilot-Screenshot-Capture"})
    with urlopen(request, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_url(url: str, timeout_seconds: float = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError, ConnectionError):
            time.sleep(0.4)
    raise TimeoutError(f"Timed out waiting for {url}")


def wait_for_devtools(port: int, timeout_seconds: float = 20) -> str:
    endpoint = f"http://127.0.0.1:{port}/json/version"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            return str(url_json(endpoint)["webSocketDebuggerUrl"])
        except (URLError, TimeoutError, ConnectionError, KeyError):
            time.sleep(0.25)
    raise TimeoutError("Microsoft Edge DevTools endpoint did not become ready.")


def wait_for_streamlit_page(
    devtools: DevTools,
    session_id: str,
    timeout_seconds: float = 35,
) -> None:
    expression = """
        (() => {
          const app = document.querySelector('[data-testid="stAppViewContainer"]');
          return Boolean(
            app && app.innerText.includes('SupplyPilot') && app.innerText.length > 250
          );
        })()
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = devtools.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True},
            session_id=session_id,
        )
        if result.get("result", {}).get("value") is True:
            # Vega views mount asynchronously; wait for both charts in the
            # two-column control-tower layout before capturing the viewport.
            time.sleep(3.0)
            return
        time.sleep(0.35)
    raise TimeoutError("Streamlit page did not finish rendering before capture.")


def capture_page(
    devtools: DevTools,
    url: str,
    destination: Path,
    width: int,
    height: int,
    scroll_to: str | None = None,
) -> None:
    target_id = devtools.call("Target.createTarget", {"url": "about:blank"})["targetId"]
    session_id = devtools.call(
        "Target.attachToTarget",
        {"targetId": target_id, "flatten": True},
    )["sessionId"]
    try:
        devtools.call("Page.enable", session_id=session_id)
        devtools.call("Runtime.enable", session_id=session_id)
        devtools.call(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,
                "mobile": False,
            },
            session_id=session_id,
        )
        devtools.call("Page.navigate", {"url": url}, session_id=session_id)
        wait_for_streamlit_page(devtools, session_id)
        if scroll_to:
            expression = f"""
                (() => {{
                  const target = [...document.querySelectorAll('h1,h2,h3')]
                    .find((element) => element.textContent.trim() === {json.dumps(scroll_to)});
                  if (!target) return false;
                  target.scrollIntoView({{block: 'start'}});
                  window.scrollBy(0, -24);
                  return true;
                }})()
            """
            result = devtools.call(
                "Runtime.evaluate",
                {"expression": expression, "returnByValue": True},
                session_id=session_id,
            )
            if result.get("result", {}).get("value") is not True:
                raise RuntimeError(f"Could not find screenshot section: {scroll_to}")
            time.sleep(1.0)
        screenshot = devtools.call(
            "Page.captureScreenshot",
            {
                "format": "png",
                "fromSurface": True,
                "captureBeyondViewport": False,
            },
            session_id=session_id,
        )
        destination.write_bytes(base64.b64decode(screenshot["data"]))
    finally:
        devtools.call("Target.closeTarget", {"targetId": target_id})


def stop_process_tree(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        process.terminate()
        process.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--only", action="append", choices=sorted(CAPTURES))
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    output_directory = args.output_dir.resolve() if args.output_dir else project_root / "assets" / "screenshots"
    output_directory.mkdir(parents=True, exist_ok=True)
    streamlit_url = f"http://127.0.0.1:{args.port}"

    streamlit_process: subprocess.Popen[Any] | None = None
    edge_process: subprocess.Popen[Any] | None = None
    devtools: DevTools | None = None
    profile_root = Path(tempfile.mkdtemp(prefix="supplypilot-edge-profile-"))

    try:
        try:
            wait_for_url(f"{streamlit_url}/_stcore/health", timeout_seconds=1)
        except TimeoutError:
            streamlit_process = subprocess.Popen(
                [
                    os.environ.get("PYTHON", "python"),
                    "-m",
                    "streamlit",
                    "run",
                    "app.py",
                    "--server.headless",
                    "true",
                    "--server.port",
                    str(args.port),
                    "--browser.gatherUsageStats",
                    "false",
                ],
                cwd=project_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            wait_for_url(f"{streamlit_url}/_stcore/health")

        debug_port = available_port()
        edge_process = subprocess.Popen(
            [
                str(find_edge()),
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-gpu-sandbox",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-crash-reporter",
                "--hide-scrollbars",
                "--no-first-run",
                "--remote-allow-origins=*",
                f"--remote-debugging-port={debug_port}",
                f"--user-data-dir={profile_root}",
                f"--window-size={args.width},{args.height}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        devtools = DevTools(wait_for_devtools(debug_port))

        selected_captures = (
            {filename: CAPTURES[filename] for filename in args.only}
            if args.only
            else CAPTURES
        )
        for filename, query in selected_captures.items():
            params = {key: value for key, value in query.items() if not key.startswith("_")}
            params["capture"] = Path(filename).stem
            url = f"{streamlit_url}/?{urlencode(params)}"
            destination = output_directory / filename
            capture_page(
                devtools,
                url,
                destination,
                args.width,
                args.height,
                scroll_to=query.get("_scroll_to"),
            )
            relative = destination.relative_to(project_root)
            print(f"Captured {relative} ({destination.stat().st_size:,} bytes)")
    finally:
        if devtools is not None:
            devtools.close()
        stop_process_tree(edge_process)
        stop_process_tree(streamlit_process)
        temp_root = Path(tempfile.gettempdir()).resolve()
        resolved_profile = profile_root.resolve()
        if temp_root in resolved_profile.parents and resolved_profile.exists():
            shutil.rmtree(resolved_profile, ignore_errors=True)


if __name__ == "__main__":
    main()
