"""Krok 2 i 4: wydzielenia z BDL, potencjał siedliskowy (0–1) i wykluczenia."""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS

from .bdl import Package, clean_address, open_packages, to_num
from .common import Paths, curve, log, same_projection, species_keys

# Kody wykluczeń (kolejność = priorytet przy kilku powodach naraz)
EXCL_NONE = ""


def _shares(ss: pd.DataFrame, cfg: dict) -> pd.Series:
    """Udział gatunku w piętrze (0–1) z kodu part_cd_act."""
    d = cfg["drzewostan"]
    part = ss["part_cd_act"]
    share = to_num(part) / 10.0
    share = share.mask(part == "MJS", d["udzial_mjs"]).mask(part == "PJD", d["udzial_pjd"])
    # Brak udziału: jedyny gatunek w piętrze = 100%, inaczej jak „pojedynczo”.
    n_in_storey = ss.groupby(["arodes_int_num", "storey_cd"])["species_cd"].transform("size")
    share = share.fillna(pd.Series(np.where(n_in_storey == 1, 1.0, d["udzial_pjd"]), index=ss.index))
    return share


def _host_weight(codes: pd.Series, hosts: dict[str, float]) -> pd.Series:
    exact = codes.map(hosts)
    genus = codes.str.split(".").str[0].map(hosts)
    return exact.fillna(genus).fillna(0.0)


def species_rows(pkg: Package, cfg: dict) -> pd.DataFrame:
    ss = pkg.table("f_storey_species.txt")
    weights = cfg["drzewostan"]["wagi_pieter"]
    ss = ss[ss["storey_cd"].isin(weights.keys())].copy()
    ss["storey_w"] = ss["storey_cd"].map(weights).astype(float)
    ss["share"] = _shares(ss, cfg)
    ss["age"] = to_num(ss["species_age"])
    ss["height_m"] = to_num(ss["height"])
    ss["rank"] = to_num(ss["sp_rank_order_act"])
    return ss


def host_scores(ss: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Dla każdego wydzielenia i gatunku grzyba: udział żywicieli, czynnik wieku, wynik żywiciela."""
    out = {}
    base = ss["share"] * ss["storey_w"]
    for key, sp in cfg["gatunki"].items():
        hw = _host_weight(ss["species_cd"], sp["zywiciele"])
        af = pd.Series(curve(ss["age"].fillna(-1), sp["wiek"]), index=ss.index)
        af = af.where(ss["age"].notna(), 0.5)
        hs = (base * hw).groupby(ss["arodes_int_num"]).sum()
        contrib = (base * hw * af).groupby(ss["arodes_int_num"]).sum()
        out[f"hs_{key}"] = hs.clip(upper=1.0)                          # ważony udział żywicieli
        out[f"af_{key}"] = (contrib / hs.where(hs > 0)).fillna(0.0)     # efektywny czynnik wieku
        out[f"hz_{key}"] = (contrib / sp["nasycenie"]).clip(upper=1.0)  # żywiciel × wiek, z nasyceniem
    return pd.DataFrame(out)


def stand_summary(ss: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Wiek/wysokość piętra górnego i zwarty zapis składu gatunkowego."""
    top = ss[ss["storey_cd"].isin(["DRZEW", "IP"])]
    g = top.groupby("arodes_int_num")
    summary = pd.DataFrame({
        "top_height": g["height_m"].max(),
        "top_age": g["age"].max(),
    })
    lead = top.sort_values(["arodes_int_num", "storey_cd", "rank"]).groupby("arodes_int_num").first()
    summary["lead_species"] = lead["species_cd"]
    summary["lead_age"] = lead["age"]

    order = {k: i for i, k in enumerate(cfg["drzewostan"]["wagi_pieter"])}
    s2 = ss.assign(_o=ss["storey_cd"].map(order)).sort_values(["arodes_int_num", "_o", "rank"])
    recs = list(zip(s2["storey_cd"], s2["species_cd"], s2["part_cd_act"],
                    s2["age"].fillna(-1).astype(int), s2["height_m"].fillna(-1).astype(int)))
    comp = pd.Series(recs, index=s2["arodes_int_num"].values).groupby(level=0).agg(list)
    summary["composition"] = comp.map(lambda r: json.dumps(r, ensure_ascii=False))
    return summary


def load_package(pkg: Package, cfg: dict) -> gpd.GeoDataFrame:
    name = pkg.name()
    log(f"{pkg.code} {name}: wczytywanie")
    geo = pkg.layer("G_SUBAREA")[["a_i_num", "adr_for", "geometry"]]
    geo["a_i_num"] = geo["a_i_num"].astype("int64").astype(str)
    if geo["a_i_num"].duplicated().any():  # wydzielenia wieloczęściowe zapisane jako kilka rekordów
        geo = geo.dissolve(by="a_i_num", as_index=False, aggfunc="first")
    sub = pkg.table("f_subarea.txt")
    area_dic = pkg.table("f_area_type_dic.txt").drop_duplicates("area_type_cd", keep="last")
    cats = pkg.table("f_arod_category.txt")
    ss = species_rows(pkg, cfg)

    df = geo.merge(sub, left_on="a_i_num", right_on="arodes_int_num", how="left")
    df["type_fl"] = df["area_type_cd"].map(area_dic.set_index("area_type_cd")["type_fl"])
    df["area_name"] = df["area_type_cd"].map(area_dic.set_index("area_type_cd")["area_type_name"])
    df["area_ha"] = to_num(df["sub_area"])
    prot = cats.sort_values("prot_rank_order").groupby("arodes_int_num")["prot_category_cd"].agg(",".join)
    df["prot"] = df["a_i_num"].map(prot).fillna("")

    df = df.join(stand_summary(ss, cfg), on="a_i_num")
    hs = host_scores(ss, cfg)
    df = df.join(hs, on="a_i_num")
    df[hs.columns] = df[hs.columns].fillna(0.0)

    df["nadl"] = name
    df["nadl_code"] = pkg.code
    df["adres"] = df["adr_for"].map(clean_address)
    keep = ["nadl_code", "nadl", "a_i_num", "adres", "area_type_cd", "area_name", "type_fl",
            "site_type_cd", "forest_func_cd", "prot", "area_ha", "top_height", "top_age",
            "lead_species", "lead_age", "composition", *hs.columns, "geometry"]
    log(f"{pkg.code} {name}: {len(df)} wydzieleń z geometrią, {len(ss)} wierszy składu")
    return gpd.GeoDataFrame(df[keep], geometry="geometry", crs=geo.crs)


def apply_site_and_potential(df: pd.DataFrame, cfg: dict) -> None:
    default = cfg["domyslny_czynnik_siedliska"]
    for key, sp in cfg["gatunki"].items():
        site = df["site_type_cd"].map(sp["siedliska"]).fillna(default)
        df[f"sf_{key}"] = site
        df[f"p_{key}"] = (df[f"hz_{key}"] * site).clip(0, 1)


def apply_exclusions(df: pd.DataFrame, cfg: dict) -> None:
    ex = cfg["wykluczenia"]
    reason = pd.Series(EXCL_NONE, index=df.index, dtype=object)

    def mark(mask, text):
        nonlocal reason
        reason = reason.mask((reason == EXCL_NONE) & mask, text)

    for code, text in ex["funkcje_lasu"].items():
        mark(df["forest_func_cd"] == code, text)
    prot_lists = df["prot"].str.split(",")
    for code, text in ex["kategorie_ochronnosci"].items():
        mark(prot_lists.map(lambda xs: code in xs), text)
    has_stand = df["top_age"].notna()
    young = np.where(df["top_height"].notna(),
                     df["top_height"] <= ex["uprawa_max_wysokosc_m"],
                     df["top_age"] < ex["uprawa_max_wiek_lat"])
    mark(has_stand & young & (df["type_fl"] != ex["nielesne_flaga"]),
         f"uprawa leśna (do {ex['uprawa_max_wysokosc_m']} m) – stały zakaz wstępu")
    mark(df["type_fl"] == ex["nielesne_flaga"], "powierzchnia nieleśna")
    df["wykluczenie"] = reason


def build(cfg: dict, paths: Paths) -> gpd.GeoDataFrame:
    parts = [load_package(p, cfg) for p in open_packages(cfg, paths)]
    gdf = pd.concat(parts, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=parts[0].crs)
    # .prj w BDL to ESRI-owy opis CS92 (pyproj rozpoznaje go jako EPSG:2180 tylko przy niższej
    # pewności) – po sprawdzeniu parametrów ustawiamy kanoniczny kod EPSG.
    target = CRS.from_user_input(cfg["dane"]["crs"])
    if gdf.crs is None or not same_projection(gdf.crs, target):
        raise RuntimeError(f"nieoczekiwany układ współrzędnych warstwy: {gdf.crs}")
    gdf = gdf.set_crs(target, allow_override=True)
    apply_site_and_potential(gdf, cfg)
    apply_exclusions(gdf, cfg)
    keys = species_keys(cfg)
    gdf["p_max"] = gdf[[f"p_{k}" for k in keys]].max(axis=1)
    stats = gdf["wykluczenie"].replace("", "dostępne").value_counts()
    log("wykluczenia: " + ", ".join(f"{k}: {v}" for k, v in stats.items()))
    gdf.to_file(paths.stands, driver="GPKG", engine="pyogrio")
    log(f"zapisano {paths.stands} ({len(gdf)} wydzieleń)")
    return gdf
