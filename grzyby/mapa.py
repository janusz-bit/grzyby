"""Krok 5: jeden plik HTML z mapą (MapLibre GL z CDN, podkład OSM).

Geometria i atrybuty wydzieleń są kodowane raz (pełny pipeline) do pliku pośredniego:
współrzędne całkowite (1e-5°) z kodowaniem różnicowym, JSON skompresowany gzipem
i zapisany w base64. Przeglądarka rozpakowuje go natywnym DecompressionStream.
Odświeżenie pogody podmienia tylko mały blok JSON z wskaźnikiem pogodowym.
"""

from __future__ import annotations

import base64
import datetime as dt
import gzip
import html
import json
from importlib import resources

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .common import Paths, grid_signature, log, model_signature, read_json, species_keys, write_json

STOREY_LABELS = {"DRZEW": "", "IP": "I p.", "IIP": "II p.", "PRZES": "przestoje",
                 "PODRII": "podrost II p.", "PODR": "podrost"}


def _simplify(gdf: gpd.GeoDataFrame, tol: float) -> gpd.GeoSeries:
    """Upraszczanie pokrycia (wspólne granice zostają wspólne), z fallbackiem."""
    out = gdf.geometry.copy()
    if hasattr(shapely, "coverage_simplify"):
        for _, idx in gdf.groupby("nadl_code").groups.items():
            geoms = shapely.make_valid(gdf.geometry.loc[idx].values)
            try:
                out.loc[idx] = shapely.coverage_simplify(geoms, tol)
            except Exception as e:  # pokrycie z nakładkami – zwykłe upraszczanie
                log(f"coverage_simplify nieudane ({e}); zwykłe upraszczanie")
                out.loc[idx] = shapely.simplify(geoms, tol, preserve_topology=True)
    else:
        out = gdf.geometry.simplify(tol, preserve_topology=True)
    return out


def _encode_ring(coords: np.ndarray, scale: float) -> list[int] | None:
    q = np.round(coords * scale).astype(np.int64)
    keep = np.ones(len(q), dtype=bool)
    keep[1:] = np.any(q[1:] != q[:-1], axis=1)
    q = q[keep]
    if len(q) > 1 and (q[0] == q[-1]).all():
        q = q[:-1]  # pierścień domyka przeglądarka
    if len(q) < 3:
        return None
    d = np.vstack([q[:1], np.diff(q, axis=0)])
    return d.ravel().tolist()


def _encode_geom(geom, scale: float, min_area_deg2: float) -> list:
    polys = []
    for poly in getattr(geom, "geoms", [geom]):
        if poly.is_empty or poly.geom_type != "Polygon":
            continue
        ext = _encode_ring(np.asarray(poly.exterior.coords), scale)
        if ext is None:
            continue
        rings = [ext]
        for hole in poly.interiors:
            if shapely.Polygon(hole).area < min_area_deg2:
                continue
            r = _encode_ring(np.asarray(hole.coords), scale)
            if r is not None:
                rings.append(r)
        polys.append(rings)
    return polys


def _dictionaries(cfg: dict, paths: Paths) -> tuple[dict[str, str], dict[str, str]]:
    """Nazwy typów siedliskowych i kategorii ochronności ze słowników BDL."""
    from .bdl import Package
    zips = sorted(paths.raw.glob("BDL_*.zip"))
    pkg = Package(zips[0], cfg["dane"]["kodowanie_txt"])
    st = pkg.table("f_site_type_dic.txt")
    pc = pkg.table("f_prot_categ_dic.txt")
    return dict(zip(st["site_type_cd"], st["site_type_name"])), dict(zip(pc["prot_category_cd"], pc["prot_category_name"]))


def _idx(values: pd.Series) -> tuple[list[str], list[int]]:
    cats = pd.Categorical(values.fillna(""))
    return [str(c) for c in cats.categories], cats.codes.astype(int).tolist()


def _ints(s: pd.Series, mult: float = 1.0, missing: int = -1) -> list[int]:
    return np.where(s.isna(), missing, np.round(s.fillna(0) * mult)).astype(int).tolist()


def build_static(cfg: dict, paths: Paths, stands: gpd.GeoDataFrame, grid_idx: np.ndarray) -> None:
    mc = cfg["mapa"]
    keys = species_keys(cfg)
    log("mapa: upraszczanie geometrii")
    geom = _simplify(stands, mc["uproszczenie_m"])
    area_ok = geom.area >= mc["min_pole_m2"]
    df = stands.loc[area_ok].copy()
    df["geometry"] = geom.loc[area_ok]
    df["g"] = np.asarray(grid_idx)[area_ok.to_numpy()]
    df = df.set_geometry("geometry").to_crs(4326)
    log(f"mapa: kodowanie {len(df)} poligonów")
    scale = 10 ** mc["precyzja"]
    min_area_deg2 = mc["min_pole_m2"] / (111_000.0 * 70_000.0)
    geoms = [_encode_geom(g, scale, min_area_deg2) for g in df.geometry.values]
    keep = np.array([len(g) > 0 for g in geoms])
    df = df.loc[keep]
    geoms = [g for g, k in zip(geoms, keep) if k]

    site_names, prot_names = _dictionaries(cfg, paths)
    nadl, nadl_i = _idx(df["nadl"])
    area_codes, area_i = _idx(df["area_type_cd"])
    area_names = df.groupby("area_type_cd")["area_name"].first().reindex(area_codes).fillna("").tolist()
    site_codes, site_i = _idx(df["site_type_cd"])
    excl, excl_i = _idx(df["wykluczenie"])  # "" (dostępne) ma kod 0, bo sortuje się pierwsze
    assert excl[0] == "", excl
    prot, prot_i = _idx(df["prot"])
    warn, warn_i = _idx(df["ostrzezenie"])

    comp = []
    for s in df["composition"].fillna("[]"):
        flat = []
        for st, sp, part, age, h in json.loads(s):
            flat += [st, sp, part, age, h]
        comp.append(flat)
    # udziały gatunków ważone wagą piętra (te same, które liczy model) -> [kod, %, kod, %, ...]
    ws = []
    for s in df["udzialy"].fillna("[]"):
        u = json.loads(s)
        ws.append([v if i % 2 == 0 else round(v * 100) for i, v in enumerate(u)])

    feats = {
        "geom": geoms,
        "n": nadl_i, "adr": df["adres"].tolist(), "area": area_i, "site": site_i, "prot": prot_i,
        "ha": _ints(df["area_ha"], 100), "ex": excl_i, "g": df["g"].astype(int).tolist(),
        "age": _ints(df["lead_age"]), "hgt": _ints(df["top_height"], 10), "lead": df["lead_species"].fillna("").tolist(),
        "comp": comp, "ws": ws, "warn": warn_i,
    }
    for k in keys:  # składniki potencjału ×100 (opis w habitat.host_scores)
        for c in ("p", "hs", "uf", "af", "hz", "sf"):
            feats[f"{c}_{k}"] = _ints(df[f"{c}_{k}"], 100, 0)
        feats[f"dm_{k}"] = df[f"dm_{k}"].fillna(0).astype(int).tolist()

    payload = {
        "skala_wsp": scale,
        "nadl": nadl,
        "rodzaje": area_codes, "rodzaje_nazwy": area_names,
        "siedliska": site_codes, "siedliska_nazwy": [site_names.get(c, "") for c in site_codes],
        "wykluczenia": excl, "ostrzezenia": warn,
        "ochronnosc": [", ".join(prot_names.get(c, c) for c in p.split(",")) if p else "" for p in prot],
        "pietra": STOREY_LABELS,
        "f": feats,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    gz = gzip.compress(raw, compresslevel=9, mtime=0)
    b64 = base64.b64encode(gz).decode("ascii")
    bounds = [round(v, 4) for v in df.total_bounds]
    write_json(paths.static_payload, {
        "zbudowano": dt.datetime.now().isoformat(timespec="minutes"),
        "liczba": len(df), "granice": bounds,
        "siatka_podpis": grid_signature(read_json(paths.grid)["wezly"]),
        "model_podpis": model_signature(cfg),
        "b64": b64,
    })
    log(f"mapa: dane statyczne {len(raw) / 1e6:.1f} MB JSON -> {len(gz) / 1e6:.1f} MB gzip "
        f"-> {len(b64) / 1e6:.1f} MB base64 ({len(df)} wydzieleń)")


def check_static(cfg: dict, static: dict, grid: dict) -> None:
    """Dane statyczne muszą pasować do siatki pogody i do reguł modelu w bieżącym configu."""
    if static.get("siatka_podpis") != grid_signature(grid["wezly"]):
        raise SystemExit("dane statyczne mapy i siatka pogody pochodzą z różnych przebiegów – "
                         "uruchom pełny pipeline (nix run .#mapa)")
    if static.get("model_podpis") != model_signature(cfg):
        raise SystemExit("zmieniono reguły siedliskowe, wykluczenia, geometrię lub siatkę w config.yaml – "
                         "uruchom pełny pipeline (nix run .#mapa)")


def _species_meta(cfg: dict) -> list[dict]:
    return [{
        "k": k, "nazwa": sp["nazwa"], "lacina": sp["lacina"], "zywiciele": sp["zywiciele"],
        "nasycenie": sp["nasycenie"], "sezon": sp["sezon"],
    } for k, sp in cfg["gatunki"].items()]


def _script_json(obj) -> str:
    # bezpieczne osadzenie JSON w <script>
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
            .replace("</", "<\\/").replace("<!--", "<\\!--"))


def _exclusion_reasons(cfg: dict) -> list[str]:
    ex = cfg["wykluczenia"]
    return [*ex["funkcje_lasu"].values(), *ex["kategorie_ochronnosci"].values(),
            *ex.get("rodzaje_powierzchni", {}).values(),
            f"uprawa leśna (do {ex['uprawa_max_wysokosc_m']} m) – stały zakaz wstępu", "powierzchnia nieleśna"]


def render(cfg: dict, paths: Paths) -> None:
    mc = cfg["mapa"]
    static = read_json(paths.static_payload)
    weather = read_json(paths.weather_index)
    grid = read_json(paths.grid)
    check_static(cfg, static, grid)
    if weather.get("siatka_podpis") != grid_signature(grid["wezly"]):
        raise SystemExit("wskaźnik pogody policzono dla innej siatki – uruchom nix run .#pogoda")
    gbif = read_json(paths.gbif_report) if paths.gbif_report.exists() else {"punkty": [], "gatunki": {}}
    meta = {
        "gatunki": _species_meta(cfg),
        "granice": static["granice"],
        "zbudowano": static["zbudowano"],
        "skala": mc["skala"],
        "styl_bazowy": mc["styl_bazowy"],
        "podklady": mc["podklady"],
        "pogoda_cfg": {
            "okno_opadu": cfg["pogoda"]["opady"]["okno_dni"],
            "okno_temp": cfg["pogoda"]["temperatura"]["okno_dni"],
            "okno_mrozu": cfg["pogoda"]["przymrozek"]["okno_dni"],
            "prog_mrozu": cfg["pogoda"]["przymrozek"]["prog_c"],
            "wysyp": cfg["pogoda"]["opady"]["wysyp_opoznienie_dni"],
            "wysyp_prog": cfg["pogoda"]["opady"]["wysyp_prog_mm"],
        },
        "prog_wysoki": cfg["gbif"]["prog_wysoki"],
        "drzewostan": cfg["drzewostan"],
        "wykluczenia_lista": _exclusion_reasons(cfg),
    }
    tpl = resources.files("grzyby").joinpath("szablon.html").read_text(encoding="utf-8")
    for ph in ("{{MAPLIBRE}}", "/*{{META}}*/null", "/*{{POGODA}}*/null", "/*{{GBIF}}*/null", "{{DANE_B64}}"):
        if ph not in tpl:
            raise RuntimeError(f"szablon.html: brak znacznika {ph}")
    v = mc["maplibre_wersja"]
    out = (tpl
           .replace("{{MAPLIBRE}}", html.escape(v))
           .replace("/*{{META}}*/null", _script_json(meta))
           .replace("/*{{POGODA}}*/null", _script_json({**weather, "wezly": grid["wezly"]}))
           .replace("/*{{GBIF}}*/null", _script_json({"punkty": gbif.get("punkty", []),
                                                      "podsumowanie": gbif.get("gatunki", {})}))
           .replace("{{DANE_B64}}", static["b64"]))
    dest = paths.out / mc["plik"]
    dest.write_text(out, encoding="utf-8")
    log(f"zapisano {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
