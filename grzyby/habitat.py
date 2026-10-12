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
    # PRZES nie ma kodów udziału – udział z miąższości gatunku
    p = d["udzial_przestoje"]
    vol_share = (ss["volume"] / p["miazszosc_pelna_m3ha"]).clip(upper=1.0).fillna(p["brak_miazszosci"])
    share = share.mask((ss["storey_cd"] == "PRZES") & share.isna(), vol_share)
    return share.fillna(d["udzial_pjd"])  # inne piętra bez kodu (w BDL 2026 nie występują)


def _host_weight(codes: pd.Series, hosts: dict[str, float]) -> pd.Series:
    exact = codes.map(hosts)
    genus = codes.str.split(".").str[0].map(hosts)
    return exact.fillna(genus).fillna(0.0)


def species_rows(pkg: Package, cfg: dict) -> pd.DataFrame:
    ss = pkg.table("f_storey_species.txt")
    weights = cfg["drzewostan"]["wagi_pieter"]
    ss = ss[ss["storey_cd"].isin(weights.keys())].copy()
    ss["storey_w"] = ss["storey_cd"].map(weights).astype(float)
    ss["volume"] = to_num(ss["volume"])
    ss["share"] = _shares(ss, cfg)
    ss["age"] = to_num(ss["species_age"])
    ss["height_m"] = to_num(ss["height"])
    ss["rank"] = to_num(ss["sp_rank_order_act"])
    return ss


def host_scores(ss: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Dla każdego wydzielenia i gatunku grzyba (sufiksy kolumn = klucz gatunku):

    hs – ważony udział żywicieli: Σ udział × waga piętra × waga żywiciela (może przekroczyć 1
         przy kilku piętrach),
    uf – czynnik udziału: min(1, hs / nasycenie), nie mniej niż min_obecnosc × waga żywiciela,
         gdy żywiciel jest w piętrach domieszki,
    af – czynnik wieku: krzywa wieku żywicieli uśredniona wagą ich udziału,
    hz – czynnik żywiciela = uf × af (czysty drzewostan żywiciela = sama krzywa wieku).
    """
    d = cfg["drzewostan"]
    ids = ss["arodes_int_num"]
    base = ss["share"] * ss["storey_w"]
    in_mix = ss["storey_cd"].isin(d["pietra_domieszki"])
    out = {}
    for key, sp in cfg["gatunki"].items():
        hw = _host_weight(ss["species_cd"], sp["zywiciele"])
        age_f = pd.Series(curve(ss["age"].fillna(-1), sp["wiek"]), index=ss.index)
        age_f = age_f.where(ss["age"].notna(), d["czynnik_wieku_brak"])
        w = base * hw
        hs = w.groupby(ids).sum()
        af = ((w * age_f).groupby(ids).sum() / hs.where(hs > 0)).fillna(0.0)
        uf = (hs / sp["nasycenie"]).clip(upper=1.0)
        if sp.get("min_obecnosc"):
            best = hw[in_mix].groupby(ids[in_mix]).max().reindex(hs.index).fillna(0.0)
            uf = np.maximum(uf, sp["min_obecnosc"] * best)
        out[f"hs_{key}"] = hs
        out[f"uf_{key}"] = uf
        out[f"af_{key}"] = af
        out[f"hz_{key}"] = uf * af
        # 1 = czynnik udziału podniesiony regułą domieszki (do opisu w popupie)
        out[f"dm_{key}"] = (uf > (hs / sp["nasycenie"]).clip(upper=1.0) + 1e-9).astype(int)
    return pd.DataFrame(out)


def stand_summary(ss: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Wiek/wysokość piętra górnego, zwarty zapis składu i ważone udziały gatunków."""
    ex = cfg["wykluczenia"]
    top = ss[ss["storey_cd"].isin(cfg["drzewostan"]["pietra_gorne"])]
    g = top.groupby("arodes_int_num")
    # wysokość drzewostanu = średnia wysokość gatunków piętra górnego ważona udziałami
    # (maksimum dawałoby 10% domieszki szybko rosnącej brzozy nad młodą uprawą). BDL nie podaje
    # wysokości głównie 2–5-letnich drzewek – dla gatunków młodszych niż uprawa_max_wiek_lat
    # przyjmujemy wtedy uprawa_wysokosc_brak_m.
    h = top["height_m"].mask(top["height_m"].isna() & (top["age"] < ex["uprawa_max_wiek_lat"]),
                             ex["uprawa_wysokosc_brak_m"])
    has_h = h.notna()
    ids_h = top.loc[has_h, "arodes_int_num"]
    top_height = ((top.loc[has_h, "share"] * h[has_h]).groupby(ids_h).sum()
                  / top.loc[has_h, "share"].groupby(ids_h).sum()).round(1)
    # indeks = wszystkie wydzielenia ze składem (także zręby/sukcesje bez piętra DRZEW/IP)
    summary = pd.DataFrame(index=pd.Index(ss["arodes_int_num"].unique(), name="arodes_int_num"))
    summary["top_age"] = g["age"].max()
    summary["top_height"] = top_height
    lead = top.sort_values(["arodes_int_num", "storey_cd", "rank"]).groupby("arodes_int_num").first()
    summary["lead_species"] = lead["species_cd"]
    summary["lead_age"] = lead["age"]

    # udział gatunku ważony wagą piętra (to samo, co wchodzi do hs) – do uzasadnienia w popupie
    wsp = (ss["share"] * ss["storey_w"]).groupby([ss["arodes_int_num"], ss["species_cd"]]).sum()
    acc: dict[str, list] = {}
    for (a, sp), v in wsp.items():
        acc.setdefault(a, []).extend([sp, round(float(v), 3)])
    summary["udzialy"] = pd.Series({k: json.dumps(v, ensure_ascii=False) for k, v in acc.items()})

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
            "lead_species", "lead_age", "composition", "udzialy", *hs.columns, "geometry"]
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
        mark(prot_lists.map(lambda xs, c=code: c in xs), text)
    for code, text in ex.get("rodzaje_powierzchni", {}).items():
        mark(df["area_type_cd"] == code, text)
    has_stand = df["top_age"].notna()
    young = np.where(df["top_height"].notna(),
                     df["top_height"] <= ex["uprawa_max_wysokosc_m"],
                     df["lead_age"] < ex["uprawa_max_wiek_lat"])
    mark(has_stand & young & (df["type_fl"] != ex["nielesne_flaga"]),
         f"uprawa leśna (do {ex['uprawa_max_wysokosc_m']} m) – stały zakaz wstępu")
    mark(df["type_fl"] == ex["nielesne_flaga"], "powierzchnia nieleśna")
    df["wykluczenie"] = reason
    warn = cfg.get("ostrzezenia", {})
    df["ostrzezenie"] = prot_lists.map(lambda xs: " · ".join(warn[c] for c in xs if c in warn))


def build(cfg: dict, paths: Paths) -> gpd.GeoDataFrame:
    parts = [load_package(p, cfg) for p in open_packages(cfg, paths)]
    gdf = pd.concat(parts, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=parts[0].crs)
    # .prj w BDL to ESRI-owy opis CS92 (zależnie od wersji PROJ rozpoznawany jako EPSG:2180
    # albo bez kodu EPSG) – po sprawdzeniu parametrów ustawiamy kanoniczny kod EPSG.
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
