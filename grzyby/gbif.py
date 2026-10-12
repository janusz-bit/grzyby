"""Krok 6: obserwacje z GBIF jako sanity check potencjału siedliskowego (nie trening)."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import box

from .common import Paths, log, read_json, write_json

FIELDS = ["key", "scientificName", "decimalLatitude", "decimalLongitude", "eventDate", "year",
          "coordinateUncertaintyInMeters", "basisOfRecord", "datasetName", "occurrenceStatus"]


def match_taxon(base: str, name: str) -> int:
    r = requests.get(f"{base}/species/match", params={"name": name, "kingdom": "Fungi"}, timeout=60)
    r.raise_for_status()
    d = r.json()
    if d.get("matchType") not in ("EXACT", "FUZZY") or "usageKey" not in d:
        raise RuntimeError(f"GBIF: nie znaleziono taksonu {name!r}: {d}")
    return int(d.get("acceptedUsageKey") or d["usageKey"])


def fetch(cfg: dict, paths: Paths, stands: gpd.GeoDataFrame) -> list[dict]:
    gc = cfg["gbif"]
    minx, miny, maxx, maxy = stands.total_bounds
    b = gc["bufor_km"] * 1000
    area = gpd.GeoSeries([box(minx - b, miny - b, maxx + b, maxy + b)], crs=stands.crs).to_crs(4326)
    x0, y0, x1, y1 = area.total_bounds
    wkt = f"POLYGON(({x0:.3f} {y0:.3f},{x1:.3f} {y0:.3f},{x1:.3f} {y1:.3f},{x0:.3f} {y1:.3f},{x0:.3f} {y0:.3f}))"
    rows: list[dict] = []
    for key, sp in cfg["gatunki"].items():
        for name in sp["gbif"]:
            taxon = match_taxon(gc["url"], name)
            offset, got = 0, 0
            while offset < gc["max_na_takson"]:
                r = requests.get(f"{gc['url']}/occurrence/search", timeout=120, params={
                    "taxonKey": taxon, "geometry": wkt, "hasCoordinate": "true",
                    "hasGeospatialIssue": "false", "occurrenceStatus": "PRESENT",
                    "limit": 300, "offset": offset})
                r.raise_for_status()
                d = r.json()
                for o in d["results"]:
                    rec = {f: o.get(f) for f in FIELDS}
                    rec["gatunek"] = key
                    rec["takson"] = name
                    rows.append(rec)
                got += len(d["results"])
                offset += 300
                if d.get("endOfRecords", True):
                    break
            log(f"GBIF {name}: {got} obserwacji")
    write_json(paths.gbif, {"obszar_wkt": wkt, "obserwacje": rows})
    return rows


def evaluate(cfg: dict, paths: Paths, stands: gpd.GeoDataFrame, rows: list[dict] | None = None) -> dict:
    gc = cfg["gbif"]
    if rows is None:
        rows = read_json(paths.gbif)["obserwacje"]
    df = pd.DataFrame(rows)
    if df.empty:
        report = {"uwaga": "brak obserwacji GBIF", "gatunki": {}}
        write_json(paths.gbif_report, report)
        return report
    unc = pd.to_numeric(df["coordinateUncertaintyInMeters"], errors="coerce")
    df["precyzyjna"] = unc.isna() | (unc <= gc["max_niepewnosc_m"])
    pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["decimalLongitude"], df["decimalLatitude"]),
                           crs=4326).to_crs(stands.crs)
    keys = list(cfg["gatunki"])
    nonforest = cfg["wykluczenia"]["nielesne_flaga"]
    forest = stands[stands["type_fl"] != nonforest]
    cols = [f"p_{k}" for k in keys] + ["wykluczenie"]
    # 1) punkt wewnątrz wydzielenia leśnego
    j = gpd.sjoin(pts, forest[cols + ["geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated(keep="first")].drop(columns="index_right")
    j["dopasowanie"] = np.where(j["p_" + keys[0]].notna(), "wewnatrz", "")
    # 2) pozostałe: najbliższe wydzielenie leśne w promieniu `dopasowanie_m` (niepewność położenia)
    miss = j["dopasowanie"] == ""
    if miss.any() and gc["dopasowanie_m"] > 0:
        near = gpd.sjoin_nearest(pts.loc[miss], forest[cols + ["geometry"]], how="inner",
                                 max_distance=gc["dopasowanie_m"], distance_col="odl_m")
        near = near[~near.index.duplicated(keep="first")]
        j.loc[near.index, cols] = near[cols]
        j.loc[near.index, "dopasowanie"] = "blisko"
    thr = gc["prog_wysoki"]

    area = forest.geometry.area
    report = {"prog_wysoki": thr, "max_niepewnosc_m": gc["max_niepewnosc_m"],
              "dopasowanie_m": gc["dopasowanie_m"], "gatunki": {}}
    for k in keys:
        s = j[(j["gatunek"] == k) & j["precyzyjna"]]
        strict = s[s["dopasowanie"] == "wewnatrz"]
        matched = s[s["dopasowanie"] != ""]
        base_share = float(area[forest[f"p_{k}"] >= thr].sum() / area.sum())

        def share_high(d):
            return None if d.empty else round(float((d[f"p_{k}"] >= thr).mean()), 3)

        obs_share = share_high(matched)
        report["gatunki"][k] = {
            "nazwa": cfg["gatunki"][k]["nazwa"],
            "obserwacji_w_obszarze": int((j["gatunek"] == k).sum()),
            "obserwacji_precyzyjnych": int(len(s)),
            "w_wydzieleniach_lesnych": int(len(strict)),
            "w_wydzieleniach_lub_blisko": int(len(matched)),
            "odsetek_wysoki_wewnatrz": share_high(strict),
            "odsetek_wysoki_z_buforem": obs_share,
            "odsetek_powierzchni_wysoki": round(base_share, 3),
            "lift": None if obs_share is None or base_share == 0 else round(obs_share / base_share, 2),
            "mala_proba": len(matched) < 10,
            "sredni_potencjal_obserwacji": None if matched.empty else round(float(matched[f"p_{k}"].mean()), 3),
            "sredni_potencjal_lasu": round(float(np.average(forest[f"p_{k}"], weights=area)), 3),
        }
        r = report["gatunki"][k]
        log(f"GBIF {k}: {r['w_wydzieleniach_lesnych']} obs. w wydzieleniach (+{len(matched) - len(strict)} "
            f"≤{gc['dopasowanie_m']} m); w wysokim potencjale {r['odsetek_wysoki_z_buforem']} "
            f"vs {r['odsetek_powierzchni_wysoki']} powierzchni lasu")

    # punkty do warstwy na mapie
    pts4326 = j.to_crs(4326)
    report["punkty"] = [
        {"g": r.gatunek, "t": r.takson, "lon": round(r.geometry.x, 5), "lat": round(r.geometry.y, 5),
         "d": (r.eventDate or "")[:10], "u": None if pd.isna(r.coordinateUncertaintyInMeters) else int(r.coordinateUncertaintyInMeters),
         "k": int(r.key), "m": r.dopasowanie,
         "p": None if pd.isna(getattr(r, f"p_{r.gatunek}")) else round(float(getattr(r, f"p_{r.gatunek}")), 2)}
        for r in pts4326.itertuples()
    ]
    write_json(paths.gbif_report, report)
    return report
