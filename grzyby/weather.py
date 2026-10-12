"""Krok 3: siatka punktów, dane Open-Meteo i wskaźnik pogodowy (0–1)."""

from __future__ import annotations

import collections
import datetime as dt
import time
from zoneinfo import ZoneInfo

import numpy as np
import requests
from pyproj import Transformer

from .common import Paths, curve, grid_signature, log, read_json, species_keys, write_json


# --- siatka ------------------------------------------------------------------

def build_grid(points_xy: np.ndarray, cfg: dict, paths: Paths) -> np.ndarray:
    """Węzły regularnej siatki (EPSG:2180) najbliższe punktom wydzieleń.

    Zwraca indeks węzła dla każdego punktu i zapisuje listę węzłów z lon/lat.
    """
    step = cfg["pogoda"]["siatka_km"] * 1000.0
    ij = np.round(points_xy / step).astype(np.int64)
    nodes, idx = np.unique(ij, axis=0, return_inverse=True)
    tr = Transformer.from_crs(cfg["dane"]["crs"], "EPSG:4326", always_xy=True)
    lon, lat = tr.transform(nodes[:, 0] * step, nodes[:, 1] * step)
    write_json(paths.grid, {
        "krok_m": step,
        "wezly": [[round(a, 4), round(b, 4)] for a, b in zip(lon, lat)],
    })
    log(f"siatka pogody: {len(nodes)} punktów co {cfg['pogoda']['siatka_km']} km")
    return idx.ravel()


# --- Open-Meteo --------------------------------------------------------------

class RateLimiter:
    """Prosty limiter „ważonych wywołań” na minutę (Open-Meteo liczy lokalizacje i długość okresu)."""

    def __init__(self, per_minute: float):
        self.per_minute = per_minute
        self.events: collections.deque[tuple[float, float]] = collections.deque()

    def wait(self, weight: float) -> None:
        while True:
            now = time.monotonic()
            while self.events and now - self.events[0][0] > 60:
                self.events.popleft()
            used = sum(w for _, w in self.events)
            if used + weight <= self.per_minute or not self.events:
                self.events.append((now, weight))
                return
            time.sleep(max(0.5, 60 - (now - self.events[0][0]) + 0.1))


def _covers_horizons(dates: list[str], pc: dict) -> bool:
    """Czy dane obejmują dziś i wszystkie horyzonty (po północy cache przestaje je obejmować)."""
    today = dt.datetime.now(ZoneInfo(pc["strefa_czasowa"])).date()
    return all((today + dt.timedelta(days=h)).isoformat() in dates for h in pc["horyzonty_dni"])


def fetch(cfg: dict, paths: Paths, force: bool = False) -> dict:
    pc = cfg["pogoda"]
    grid = read_json(paths.grid)
    nodes = grid["wezly"]
    if paths.weather_raw.exists() and not force:
        cached = read_json(paths.weather_raw)
        age_h = (time.time() - cached["pobrano_ts"]) / 3600
        if (age_h < pc["cache_godzin"] and _covers_horizons(cached["daty"], pc) and cached["wezly"] == nodes
                and cached["parametry"] == _params_sig(pc)):
            log(f"pogoda z cache ({age_h:.1f} h temu); użyj --force, aby pobrać ponownie")
            return cached

    started_ts = time.time()
    started = dt.datetime.now(ZoneInfo(pc["strefa_czasowa"])).isoformat(timespec="minutes")

    n_days = pc["dni_wstecz"] + pc["dni_prognozy"] + 1
    n_vars = len(pc["zmienne_dzienne"]) + (1 if pc.get("wilgotnosc_gleby") else 0)
    per_loc = max(1.0, n_vars / 10) * max(1.0, n_days / 14)
    limiter = RateLimiter(pc["limit_wywolan_na_minute"])
    chunk = pc["punktow_na_zapytanie"]
    results: list[dict] = []
    for start in range(0, len(nodes), chunk):
        part = nodes[start:start + chunk]
        params = {
            "latitude": ",".join(f"{p[1]:.4f}" for p in part),
            "longitude": ",".join(f"{p[0]:.4f}" for p in part),
            "daily": ",".join(pc["zmienne_dzienne"]),
            "past_days": pc["dni_wstecz"],
            "forecast_days": pc["dni_prognozy"] + 1,
            "timezone": pc["strefa_czasowa"],
        }
        if pc.get("wilgotnosc_gleby"):
            params["hourly"] = pc["wilgotnosc_gleby"]
        for attempt in range(6):
            limiter.wait(per_loc * len(part))
            r = requests.get(pc["url"], params=params, timeout=120)
            if r.status_code == 429 or r.status_code >= 500:
                log(f"Open-Meteo {r.status_code}: czekam 60 s (próba {attempt + 1})")
                time.sleep(60)
                continue
            r.raise_for_status()
            break
        else:
            raise RuntimeError("Open-Meteo: przekroczono liczbę prób")
        data = r.json()
        results.extend(data if isinstance(data, list) else [data])
        log(f"Open-Meteo: {min(start + chunk, len(nodes))}/{len(nodes)} punktów")

    # pobieranie przez północ: późniejsze paczki mają zakres dat przesunięty o dzień
    if any(res["daily"]["time"] != results[0]["daily"]["time"] for res in results):
        raise RuntimeError("Open-Meteo: paczki mają różne zakresy dat (pobieranie przez północ?) – uruchom ponownie")
    daily_vars = pc["zmienne_dzienne"]
    out = {
        "pobrano_ts": started_ts,
        "pobrano": started,
        "parametry": _params_sig(pc),
        "wezly": nodes,
        "daty": results[0]["daily"]["time"],
        "dzienne": {v: [res["daily"][v] for res in results] for v in daily_vars},
    }
    sm_var = pc.get("wilgotnosc_gleby")
    if sm_var:
        out["gleba"] = [_daily_mean(res["hourly"]["time"], res["hourly"][sm_var], out["daty"]) for res in results]
    write_json(paths.weather_raw, out)
    return out


def _params_sig(pc: dict) -> list:
    return [pc["dni_wstecz"], pc["dni_prognozy"], pc["zmienne_dzienne"], pc.get("wilgotnosc_gleby")]


def _daily_mean(times: list[str], values: list, dates: list[str]) -> list:
    acc: dict[str, list[float]] = collections.defaultdict(list)
    for t, v in zip(times, values):
        if v is not None:
            acc[t[:10]].append(v)
    return [float(np.mean(acc[d])) if acc.get(d) else None for d in dates]


# --- wskaźnik ----------------------------------------------------------------

def _arr(rows) -> np.ndarray:
    return np.array([[np.nan if v is None else v for v in r] for r in rows], dtype=float)


def compute_index(raw: dict, cfg: dict, paths: Paths) -> dict:
    pc = cfg["pogoda"]
    tz = ZoneInfo(pc["strefa_czasowa"])
    dates = [dt.date.fromisoformat(d) for d in raw["daty"]]
    today = dt.datetime.now(tz).date()
    if today not in dates:
        raise RuntimeError(f"brak dnia {today} w danych Open-Meteo ({dates[0]}–{dates[-1]})")
    t0 = dates.index(today)

    P = _arr(raw["dzienne"]["precipitation_sum"])
    P = np.nan_to_num(P, nan=0.0)
    Tmin = _arr(raw["dzienne"]["temperature_2m_min"])
    Tmean = _arr(raw["dzienne"]["temperature_2m_mean"])
    SM = _arr(raw["gleba"]) if raw.get("gleba") else None

    o, g, t, f = pc["opady"], pc["gleba"], pc["temperatura"], pc["przymrozek"]
    horizons = []
    for h in pc["horyzonty_dni"]:
        D = t0 + h
        if D >= len(dates):
            raise RuntimeError(f"prognoza za krótka dla horyzontu +{h} dni")
        p_win = P[:, max(0, D - o["okno_dni"] + 1): D + 1].sum(axis=1)
        rain = curve(p_win, o["krzywa_mm"])
        # premia za obfity deszcz 7–14 dni wcześniej (początek wysypu): każde k-dniowe okno
        # zdarzenia musi leżeć w całości w przedziale [D - lag_hi, D - lag_lo]
        k = o["wysyp_okno_zdarzenia_dni"]
        lag_lo, lag_hi = o["wysyp_opoznienie_dni"]
        if k > lag_hi - lag_lo + 1:
            raise ValueError("pogoda.opady: wysyp_okno_zdarzenia_dni dłuższe niż przedział wysyp_opoznienie_dni")
        ev_mm = np.zeros(len(P))
        for end in range(D - lag_hi + k - 1, D - lag_lo + 1):
            if end - k + 1 >= 0:
                ev_mm = np.maximum(ev_mm, P[:, end - k + 1: end + 1].sum(axis=1))
        event = ev_mm >= o["wysyp_prog_mm"]
        rain = np.minimum(1.0, rain + np.where(event, o["wysyp_premia"], 0.0))
        if SM is not None and g["waga"] > 0:
            sm = SM[:, D]
            soil = curve(np.nan_to_num(sm, nan=-1), g["krzywa_m3m3"])
            moist = np.where(np.isnan(sm), rain, (1 - g["waga"]) * rain + g["waga"] * soil)
        else:
            sm = np.full(len(P), np.nan)
            moist = rain
        t_win = np.nanmean(Tmean[:, max(0, D - t["okno_dni"] + 1): D + 1], axis=1)
        temp = curve(t_win, t["krzywa_c"])
        tmin_win = np.nanmin(Tmin[:, max(0, D - f["okno_dni"] + 1): D + 1], axis=1)
        frost = np.where(tmin_win < f["prog_c"], f["mnoznik"], 1.0)
        base = moist * temp * frost
        month = dates[D].month
        horizons.append({
            "h": h,
            "data": dates[D].isoformat(),
            "prognoza": h > 0,
            "sezon": {k_: cfg["gatunki"][k_]["sezon"].get(month, 0.0) for k_ in species_keys(cfg)},
            "w": _r(base, 3),
            "skladniki": {
                "opad_mm": _r(p_win, 1), "wysyp_mm": _r(ev_mm, 1), "gleba": _r(sm, 3),
                "t_sr": _r(t_win, 1), "t_min": _r(tmin_win, 1),
                "f_opad": _r(rain, 2), "f_wilg": _r(moist, 2), "f_temp": _r(temp, 2), "f_mroz": _r(frost, 2),
            },
        })
        log(f"pogoda {dates[D]} (+{h} d): średni wskaźnik bazowy {np.nanmean(base):.2f}, "
            f"opad {pc['opady']['okno_dni']} d śr. {np.nanmean(p_win):.0f} mm, T{t['okno_dni']} śr. {np.nanmean(t_win):.1f}°C")
    out = {
        "pobrano": raw["pobrano"],
        "dzis": today.isoformat(),
        "strefa": pc["strefa_czasowa"],
        "siatka_podpis": grid_signature(raw["wezly"]),
        "zrodlo": "Open-Meteo (open-meteo.com), CC BY 4.0",
        "horyzonty": horizons,
    }
    write_json(paths.weather_index, out)
    return out


def _r(a: np.ndarray, nd: int) -> list:
    return [None if np.isnan(v) else round(float(v), nd) for v in np.asarray(a, dtype=float)]


def run(cfg: dict, paths: Paths, force: bool = False) -> dict:
    raw = fetch(cfg, paths, force=force)
    return compute_index(raw, cfg, paths)
