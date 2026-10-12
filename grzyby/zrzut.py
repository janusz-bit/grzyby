"""Krok 6: zrzut ekranu mapy przeglądarką headless (jeśli jest dostępna).

Chromium jest sterowany przez DevTools Protocol (minimalny klient WebSocket na bibliotece
standardowej), żeby poczekać na faktyczne rozpakowanie danych i wyrenderowanie mapy,
zebrać błędy JavaScript i sprawdzić popup wydzielenia.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .common import Paths, log, write_json

BROWSERS = ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"]


def find_browser() -> str | None:
    return next((b for b in map(shutil.which, BROWSERS) if b), None)


class WebSocket:
    def __init__(self, url: str, timeout: float = 300):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.sock.recv(4096)
        head, self.buf = resp.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head.decode(errors="replace"))

    def send(self, text: str) -> None:
        data = text.encode()
        n = len(data)
        hdr = bytearray([0x81])
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(bytes(hdr) + mask + masked)

    def _read(self, n: int) -> bytes:
        chunks = [self.buf]
        have = len(self.buf)
        while have < n:
            c = self.sock.recv(max(65536, n - have))
            if not c:
                raise ConnectionError("WebSocket zamknięty")
            chunks.append(c)
            have += len(c)
        data = b"".join(chunks)
        self.buf = data[n:]
        return data[:n]

    def recv(self) -> str:
        msg = b""
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b1 & 0x80 else None
            payload = self._read(n)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            op = b0 & 0x0F
            if op == 8:
                raise ConnectionError("WebSocket zamknięty przez przeglądarkę")
            if op in (9, 10):
                continue
            msg += payload
            if b0 & 0x80:
                return msg.decode()


class DevTools:
    def __init__(self, ws_url: str):
        self.ws = WebSocket(ws_url)
        self.next_id = 0
        self.events: list[dict] = []

    def call(self, method: str, **params):
        self.next_id += 1
        self.ws.send(json.dumps({"id": self.next_id, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.next_id:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})
            self.events.append(m)

    def eval(self, expr: str):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            raise RuntimeError(f"JS: {r['exceptionDetails'].get('exception', {}).get('description') or r['exceptionDetails']}")
        return r.get("result", {}).get("value")

    def wait_for(self, expr: str, timeout: float, step: float = 2.0) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.eval(expr):
                return True
            time.sleep(step)
        return False

    def screenshot(self, path: Path) -> None:
        data = self.call("Page.captureScreenshot", format="png")["data"]
        path.write_bytes(base64.b64decode(data))

    def errors(self) -> list[str]:
        out = []
        for e in self.events:
            p = e.get("params", {})
            if e.get("method") == "Runtime.exceptionThrown":
                d = p.get("exceptionDetails", {})
                out.append(d.get("exception", {}).get("description") or d.get("text", "wyjątek JS"))
            elif e.get("method") == "Runtime.consoleAPICalled" and p.get("type") == "error":
                out.append(" ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", [])))
            elif e.get("method") == "Log.entryAdded" and p.get("entry", {}).get("level") == "error":
                out.append(f"{p['entry'].get('text')} {p['entry'].get('url', '')}".strip())
        return out


# Sprawdzenia wykonywane w stronie po wyrenderowaniu
CHECK_JS = """(() => {
  const r = id => map.queryRenderedFeatures({layers: [id]}).length;
  return {pot: r('pot'), wyk: r('wyk'), wydzielen: F.geom.length, wezlow: POGODA.wezly.length,
          zoom: map.getZoom(), dzien: POGODA.horyzonty[state.dzien].data};
})()"""

POPUP_JS = """(async () => {
  map.jumpTo({center: %s, zoom: 13});
  await new Promise(r => map.once('idle', r));
  // szukamy piksela w środkowej części ekranu, pod którym leży wydzielenie o najwyższym potencjale
  const c = map.getCanvas().getBoundingClientRect();
  let best = null;
  for (let x = c.width * 0.55; x < c.width * 0.85; x += 25)  // z dala od panelu po lewej
    for (let y = c.height * 0.3; y < c.height * 0.7; y += 25) {
      const f = map.queryRenderedFeatures([x, y], {layers: ['pot']})[0];
      if (f && (!best || f.properties.p0 > best.p)) best = {x, y, p: f.properties.p0, i: f.properties.i};
    }
  return best ? {ok: true, x: best.x + c.left, y: best.y + c.top, i: best.i} : {ok: false};
})()"""


def run(cfg: dict, paths: Paths, timeout_s: float = 600, center=(23.62, 52.73)) -> Path | None:
    browser = find_browser()
    if not browser:
        log("brak przeglądarki headless – pomijam zrzut (uruchom: nix run .#zrzut)")
        return None
    html = (paths.out / cfg["mapa"]["plik"]).resolve()
    png = paths.out / "zrzut.png"
    png_popup = paths.out / "zrzut_popup.png"
    profile = tempfile.mkdtemp(prefix="grzyby-chromium-")
    proc = subprocess.Popen(
        [browser, "--headless=new", "--no-sandbox", "--hide-scrollbars", "--window-size=1400,900",
         "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
         "--no-first-run", "--disable-background-networking", "--remote-debugging-port=0",
         f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    report: dict = {"przegladarka": browser}
    try:
        port_file = Path(profile) / "DevToolsActivePort"
        for _ in range(120):
            if port_file.exists() and port_file.read_text().strip():
                break
            time.sleep(0.5)
        port = int(port_file.read_text().split()[0])
        targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list"))
        page = next(t for t in targets if t.get("type") == "page")
        dt = DevTools(page["webSocketDebuggerUrl"])
        for dom in ("Runtime", "Page", "Log"):
            dt.call(f"{dom}.enable")
        log(f"zrzut ekranu: {browser}")
        t0 = time.time()
        dt.call("Page.navigate", url=html.as_uri())
        ready = dt.wait_for("window.__mapaGotowa === true || !!window.__mapaBlad", timeout_s)
        report["czas_ladowania_s"] = round(time.time() - t0, 1)
        report["blad_strony"] = dt.eval("window.__mapaBlad || null")
        if ready and not report["blad_strony"]:
            report["kontrola"] = dt.eval(CHECK_JS)
            dt.screenshot(png)
            target = dt.eval(POPUP_JS % json.dumps(list(center)))
            if target and target.get("ok"):
                for typ in ("mouseMoved", "mousePressed", "mouseReleased"):
                    dt.call("Input.dispatchMouseEvent", type=typ, x=target["x"], y=target["y"],
                            button="left", clickCount=1)
                dt.wait_for("!!document.querySelector('.maplibregl-popup-content')", 30, step=1)
                time.sleep(2)
                report["popup"] = dt.eval("(() => { const p = document.querySelector('.maplibregl-popup-content');"
                                          " return p ? p.innerText : null; })()")
                dt.screenshot(png_popup)
        else:
            dt.screenshot(png)
        report["bledy_js"] = dt.errors()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)

    write_json(paths.out / "zrzut_raport.json", report)
    ok = bool(report.get("kontrola", {}).get("pot")) and not report["bledy_js"] and report.get("popup")
    log(f"zapisano {png}: załadowano w {report['czas_ladowania_s']} s, "
        f"wyrenderowane wydzielenia {report.get('kontrola', {}).get('pot')} (+{report.get('kontrola', {}).get('wyk')} wykluczonych), "
        f"popup {'tak' if report.get('popup') else 'NIE'}, błędy JS: {len(report['bledy_js'])}")
    for e in report["bledy_js"][:10]:
        log(f"  błąd JS: {e}")
    if not ok:
        log("uwaga: mapa mogła się nie wyrenderować poprawnie – obejrzyj zrzut i output/zrzut_raport.json")
    return png
