"""Attach to hidden Chrome over CDP and run window.fetch() in-page.

List targets on the debugging port, pick an irctc.co.in page, then
`Runtime.evaluate` with `awaitPromise` so the call is the page's own fetch
(cookies, origin, TLS). Charts Chrome is a normal (non-HeadlessChrome)
process on a private Xvfb display so no window is shown. This module never
books, pays, or hits availability write paths — callers must pass an
allowed charts/schedule path.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import httpx

from app.forbidden import assert_allowed_path
from app.integration.live_client import LiveAccessError
from app.logging_util import configure_logging

logger = configure_logging()

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts" / "start-charts-chrome.sh"
DEFAULT_CDP = os.environ.get("CHROME_CDP") or "http://127.0.0.1:9222"
ORIGIN = "https://www.irctc.co.in"
CHARTS_PARK_URL = f"{ORIGIN}/online-charts/"
_FETCH_LOCK = threading.Lock()


def default_cdp() -> str:
    return os.environ.get("CHROME_CDP") or DEFAULT_CDP


def connect_ws(url: str, timeout: float):
    from websockets.sync.client import connect

    return connect(url, open_timeout=timeout, close_timeout=2)


def window_up(cdp: str | None = None, timeout: float = 3.0) -> bool:
    endpoint = (cdp or default_cdp()).rstrip("/")
    try:
        response = httpx.get(f"{endpoint}/json/version", timeout=timeout)
    except httpx.HTTPError:
        return False
    return response.status_code == 200 and bool(response.text.strip())


def _cdp_port(endpoint: str) -> str:
    return endpoint.rsplit(":", 1)[-1]


def _xvfb_display() -> str:
    return os.environ.get("CHARTS_XVFB_DISPLAY") or ":99"


def _main_chrome_pid(port: str) -> str | None:
    try:
        done = subprocess.run(  # noqa: S603
            ["ps", "-eo", "pid=,args="],
            capture_output=True,
            text=True,
            timeout=3.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    marker = f"--remote-debugging-port={port}"
    for line in done.stdout.splitlines():
        if marker not in line or "--type=" in line:
            continue
        return line.split(None, 1)[0]
    return None


def _process_display(pid: str) -> str | None:
    env_path = Path(f"/proc/{pid}/environ")
    try:
        raw = env_path.read_bytes()
    except OSError:
        raw = b""
    for item in raw.split(b"\0"):
        if item.startswith(b"DISPLAY="):
            return item.decode("utf-8", "replace").split("=", 1)[1]
    try:
        done = subprocess.run(  # noqa: S603
            ["pgrep", "-P", str(pid)],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    for child in done.stdout.split():
        found = _process_display_direct(child)
        if found:
            return found
    return None


def _process_display_direct(pid: str) -> str | None:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return None
    for item in raw.split(b"\0"):
        if item.startswith(b"DISPLAY="):
            return item.decode("utf-8", "replace").split("=", 1)[1]
    return None


def chrome_is_hidden(cdp: str | None = None) -> bool:
    """True when CDP Chrome is a normal (not --headless) process on Xvfb."""
    port = _cdp_port((cdp or default_cdp()).rstrip("/"))
    pid = _main_chrome_pid(port)
    if not pid:
        return False
    try:
        args = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return False
    if "--headless" in args:
        return False
    display = _process_display(pid) or ""
    expected = _xvfb_display()
    return display == expected or display.startswith(f"{expected}.")


def chrome_is_headless(cdp: str | None = None) -> bool:
    """Kept for tests: True when the CDP process was started with --headless."""
    port = _cdp_port((cdp or default_cdp()).rstrip("/"))
    pid = _main_chrome_pid(port)
    if not pid:
        return False
    try:
        args = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return False
    return "--headless" in args


def ensure_window(*, cdp: str | None = None, timeout: float = 30.0) -> tuple[bool, str]:
    endpoint = (cdp or default_cdp()).rstrip("/")
    if window_up(endpoint, timeout=3.0) and chrome_is_hidden(endpoint):
        return True, f"hidden Chrome already answers on {endpoint}"
    if not LAUNCHER.exists():
        return False, f"no attachable Chrome on {endpoint} and missing {LAUNCHER}"
    try:
        done = subprocess.run(  # noqa: S603
            ["bash", str(LAUNCHER), "--cdp", endpoint, "--replace-headed"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"failed to start hidden charts Chrome: {exc}"
    if window_up(endpoint, timeout=3.0) and chrome_is_hidden(endpoint):
        return True, (done.stdout.strip() or "started hidden charts Chrome")
    detail = (done.stdout or done.stderr or "").strip() or f"launcher exited {done.returncode}"
    return False, f"no hidden Chrome on CDP: {detail}"


def list_targets(cdp: str) -> list[dict[str, Any]]:
    endpoint = cdp.rstrip("/")
    try:
        response = httpx.get(f"{endpoint}/json/list", timeout=5.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise LiveAccessError(f"Chrome CDP target list failed: {exc}") from exc
    if not isinstance(payload, list):
        raise LiveAccessError("Chrome CDP target list was not a JSON array.")
    return payload


def pick_irctc_page(pages: list[dict[str, Any]]) -> dict[str, Any] | None:
    page_targets = [target for target in pages if target.get("type") == "page"]
    on_site = [target for target in page_targets if str(target.get("url") or "").startswith(ORIGIN)]
    if not on_site:
        return None
    charts = next((target for target in on_site if "/online-charts" in str(target.get("url") or "")), None)
    return charts or on_site[0]


def pick_page_for_path(pages: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
    page_targets = [target for target in pages if target.get("type") == "page"]
    on_site = [target for target in page_targets if str(target.get("url") or "").startswith(ORIGIN)]
    if "/eticketing/" in path:
        nget = next((target for target in on_site if "/nget/" in str(target.get("url") or "")), None)
        if nget:
            return nget
    charts = next((target for target in on_site if "/online-charts" in str(target.get("url") or "")), None)
    return charts or (on_site[0] if on_site else None)


def _open_charts_tab(cdp: str) -> None:
    endpoint = cdp.rstrip("/")
    url = f"{endpoint}/json/new?{quote(CHARTS_PARK_URL, safe=':/')}"
    try:
        httpx.put(url, timeout=8.0)
    except httpx.HTTPError:
        try:
            httpx.get(url, timeout=8.0)
        except httpx.HTTPError as exc:
            raise LiveAccessError(f"Chrome CDP could not open an IRCTC charts tab: {exc}") from exc


def reload_charts_page(cdp: str, page: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reload the IRCTC charts tab so a dead in-page fetch context can recover."""
    target = page if page and page.get("webSocketDebuggerUrl") else pick_irctc_page(list_targets(cdp))
    if not target or not target.get("webSocketDebuggerUrl"):
        _open_charts_tab(cdp)
        time.sleep(1.0)
        chosen = pick_irctc_page(list_targets(cdp))
        if not chosen:
            raise LiveAccessError("Chrome CDP could not reload an IRCTC charts tab.")
        return chosen
    evaluate(
        str(target["webSocketDebuggerUrl"]),
        "location.reload(true); 'reloaded'",
        timeout=8.0,
        await_promise=False,
    )
    deadline = time.time() + 12.0
    while time.time() < deadline:
        chosen = pick_irctc_page(list_targets(cdp))
        if chosen and chosen.get("webSocketDebuggerUrl"):
            url = str(chosen.get("url") or "")
            if "/online-charts" in url:
                try:
                    ready = evaluate(
                        str(chosen["webSocketDebuggerUrl"]),
                        "document.readyState",
                        timeout=4.0,
                    )
                except LiveAccessError:
                    time.sleep(0.3)
                    continue
                if ready in {"interactive", "complete"}:
                    time.sleep(0.4)
                    return chosen
        time.sleep(0.3)
    chosen = pick_irctc_page(list_targets(cdp))
    if chosen and chosen.get("webSocketDebuggerUrl"):
        return chosen
    raise LiveAccessError("Chrome CDP charts tab did not come back after reload.")


def ensure_irctc_page(cdp: str, timeout: float = 20.0, path: str | None = None) -> dict[str, Any]:
    deadline = time.time() + timeout
    picker = (lambda pages: pick_page_for_path(pages, path or "")) if path else pick_irctc_page
    chosen = picker(list_targets(cdp))
    if chosen and chosen.get("webSocketDebuggerUrl"):
        return chosen
    _open_charts_tab(cdp)
    while time.time() < deadline:
        chosen = picker(list_targets(cdp))
        if chosen and chosen.get("webSocketDebuggerUrl"):
            return chosen
        time.sleep(0.3)
    raise LiveAccessError(
        "Chrome CDP is up but no tab is on irctc.co.in. Restart scripts/start-charts-chrome.sh so it parks on /online-charts/."
    )


def page_fetch_expression(method: str, url: str, body: dict[str, Any] | None, timeout_ms: int = 20000) -> str:
    call = json.dumps({"method": method, "url": url, "body": body, "timeoutMs": int(timeout_ms)})
    protected = "/eticketing/protected/" in url
    token_walk = ""
    extra_headers = ""
    if protected:
        token_walk = """
  const keys = ['httpClient', 'bmirak', 'token', 'csrfToken'];
  const seen = new Set();
  const queue = [];
  const root = document.querySelector('app-root');
  if (root && root.__ngContext__) {
    for (const entry of Array.isArray(root.__ngContext__) ? root.__ngContext__ : [root.__ngContext__]) queue.push(entry);
  }
  let client = null;
  let visits = 0;
  while (queue.length > 0 && visits < 4000) {
    const node = queue.shift();
    visits += 1;
    if (!node || typeof node !== 'object' || seen.has(node)) continue;
    seen.add(node);
    try {
      const own = Object.keys(node);
      if (!client && keys.every((key) => own.includes(key))) {
        const token = node.token && (node.token.access_token || node.token);
        client = {
          token: typeof token === 'string' ? token : null,
          csrfToken: node.csrfToken ? String(node.csrfToken) : null,
          uid: node.uid ? String(node.uid) : null,
        };
      }
      for (const key of own) {
        const value = node[key];
        if (value && typeof value === 'object' && !value.nodeType) queue.push(value);
      }
    } catch (error) { /* skip unreadables */ }
  }
"""
        extra_headers = """
    if (client && client.token) headers.Authorization = 'Bearer ' + client.token;
    if (client && client.csrfToken) headers['Spa-Csrf-Token'] = client.csrfToken;
    if (client && client.uid) headers.Greq = client.uid;
    headers.Bmirak = 'webbm';
"""
    return f"""(async () => {{
  const call = {call};
  {token_walk}
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), call.timeoutMs);
  try {{
    const headers = {{
      Accept: 'application/json, text/plain, */*',
      'Content-Type': 'application/json; charset=utf-8',
    }};
    {extra_headers}
    const init = {{
      method: call.method,
      headers,
      credentials: 'include',
      cache: 'no-store',
      signal: controller.signal,
    }};
    if (call.body !== null && call.method !== 'GET') {{
      init.body = JSON.stringify(call.body);
    }}
    const response = await fetch(call.url, init);
    const text = await response.text();
    let parsed = null;
    try {{ parsed = JSON.parse(text); }} catch (error) {{ parsed = null; }}
    return {{
      status: response.status,
      ok: response.ok,
      contentType: response.headers.get('content-type'),
      body: parsed,
      text: parsed === null ? text.slice(0, 300) : null,
    }};
  }} catch (error) {{
    return {{ error: String((error && error.message) || error) }};
  }} finally {{
    clearTimeout(timer);
  }}
}})()"""


def evaluate(
    web_socket_debugger_url: str,
    expression: str,
    timeout: float = 30.0,
    await_promise: bool = True,
) -> Any:
    payload = {
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": await_promise,
            "timeout": int((timeout + 5) * 1000),
        },
    }
    try:
        with connect_ws(web_socket_debugger_url, timeout) as socket:
            socket.send(json.dumps(payload))
            deadline = time.time() + timeout + 5
            while True:
                remaining = max(0.1, deadline - time.time())
                raw = socket.recv(timeout=remaining)
                message = json.loads(raw)
                if message.get("id") != 1:
                    continue
                if message.get("result", {}).get("exceptionDetails"):
                    details = message["result"]["exceptionDetails"]
                    text = (
                        (details.get("exception") or {}).get("description")
                        or details.get("text")
                        or "the page threw"
                    )
                    raise LiveAccessError(f"Chrome CDP page threw: {text}")
                return (message.get("result") or {}).get("result", {}).get("value")
    except LiveAccessError:
        raise
    except Exception as exc:
        raise LiveAccessError(f"Chrome CDP evaluate failed: {exc}") from exc


def _transient_fetch_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        token in lowered
        for token in (
            "failed to fetch",
            "networkerror",
            "the user aborted a request",
            "aborted",
            "timed out",
            "timeout",
        )
    )


def _one_page_fetch(
    method: str,
    path: str,
    body: dict[str, Any] | None,
    *,
    endpoint: str,
    timeout: float,
    origin: str,
    page: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    page = page or ensure_irctc_page(endpoint, timeout=min(20.0, max(8.0, timeout)), path=path)
    ws_url = page.get("webSocketDebuggerUrl")
    if not ws_url:
        raise LiveAccessError("Chrome CDP page has no webSocketDebuggerUrl.")
    url = f"{origin.rstrip('/')}{path}"
    timeout_ms = int(max(2.0, timeout) * 1000)
    value = evaluate(str(ws_url), page_fetch_expression(method, url, body, timeout_ms=timeout_ms), timeout=timeout + 8)
    if not isinstance(value, dict):
        raise LiveAccessError("Chrome CDP page fetch returned no object.")
    return page, value


def fetch_json(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    cdp: str | None = None,
    timeout: float = 20.0,
    origin: str = ORIGIN,
) -> dict[str, Any]:
    assert_allowed_path(path)
    endpoint = (cdp or default_cdp()).rstrip("/")
    with _FETCH_LOCK:
        if not window_up(endpoint) or not chrome_is_hidden(endpoint):
            ok, message = ensure_window(cdp=endpoint)
            if not ok:
                raise LiveAccessError(f"Hidden Chrome CDP is not available: {message}")
        page, value = _one_page_fetch(method, path, body, endpoint=endpoint, timeout=timeout, origin=origin)
        if value.get("error") and _transient_fetch_error(str(value.get("error"))):
            logger.info("cdp retry after in-page fetch error: %s", value.get("error"))
            try:
                page = reload_charts_page(endpoint, page)
            except LiveAccessError as exc:
                logger.info("cdp reload after failed fetch: %s", exc)
            page, value = _one_page_fetch(
                method,
                path,
                body,
                endpoint=endpoint,
                timeout=timeout,
                origin=origin,
                page=page,
            )
        if value.get("error"):
            raise LiveAccessError(f"In-page fetch failed for {path}: {value['error']}")
        status = value.get("status")
        if isinstance(status, int) and status in {401, 403}:
            raise LiveAccessError(f"Access denied for {path} (HTTP {status}) via Chrome CDP.")
        if isinstance(status, int) and status >= 400:
            raise LiveAccessError(f"Upstream error for {path}: HTTP {status} via Chrome CDP.")
        payload = value.get("body")
        if not isinstance(payload, dict):
            raise LiveAccessError(f"Malformed JSON from {path} via Chrome CDP.")
        logger.info("cdp %s %s status=%s", method, path, status)
        return payload
