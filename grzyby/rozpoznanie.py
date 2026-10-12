"""Krok 1: rozpoznanie danych BDL – raport z faktycznie występujących wartości."""

from __future__ import annotations

import collections
import re

from pyproj import CRS

from .bdl import Package, open_packages
from .common import Paths, log, same_projection


def _md_counts(counter: collections.Counter, names: dict[str, str] | None = None, top: int | None = None) -> str:
    rows = ["| kod | liczba | opis |", "|---|---:|---|"]
    for code, n in counter.most_common(top):
        rows.append(f"| `{code or '(puste)'}` | {n} | {(names or {}).get(code, '')} |")
    return "\n".join(rows)


def run(cfg: dict, paths: Paths) -> str:
    pkgs = open_packages(cfg, paths)
    crs_seen = collections.Counter()
    enc_seen = collections.Counter()
    c = {k: collections.Counter() for k in
         ["species_main", "species_all", "site", "area", "func", "prot", "storey", "part", "subarea_cols"]}
    names: dict[str, dict[str, str]] = {k: {} for k in c}
    n_geom = n_txt = n_multi = n_stands = 0
    per_pkg = []
    p0: Package | None = None
    for pkg in pkgs:
        p0 = p0 or pkg
        crs = CRS.from_wkt(pkg.prj())
        same = same_projection(crs, CRS.from_user_input(cfg["dane"]["crs"]))
        esri = re.search(r'PROJCS\["([^"]+)"', pkg.prj())
        crs_seen[f"`{esri.group(1) if esri else '?'}` (pyproj: {crs.name}) → EPSG:{crs.to_epsg(min_confidence=20)}, "
                 f"parametry {'identyczne z' if same else 'RÓŻNE od'} {cfg['dane']['crs']}"] += 1
        sub = pkg.table("f_subarea.txt")
        ss = pkg.table("f_storey_species.txt")
        cats = pkg.table("f_arod_category.txt")
        for f in ["f_subarea.txt", "f_storey_species.txt", "f_arodes.txt", "f_arod_category.txt"]:
            pkg.table(f)
            enc_seen[pkg.detected_encoding[f]] += 1
        geo = pkg.layer("G_SUBAREA")
        c["subarea_cols"].update(geo.columns)
        n_geom += len(geo)
        n_txt += len(sub)
        c["site"].update(sub["site_type_cd"])
        c["area"].update(sub["area_type_cd"])
        c["func"].update(sub["forest_func_cd"])
        c["prot"].update(cats["prot_category_cd"])
        c["storey"].update(ss["storey_cd"])
        c["part"].update(ss["part_cd_act"])
        main = ss[ss["storey_cd"].isin(["DRZEW", "IP", "IIP"])]
        c["species_main"].update(main["species_cd"])
        c["species_all"].update(ss["species_cd"])
        per_stand = main[main["storey_cd"].isin(["DRZEW", "IP"])].groupby("arodes_int_num")["species_cd"].nunique()
        n_stands += len(per_stand)
        n_multi += int((per_stand > 1).sum())
        per_pkg.append((pkg.code, pkg.name(), len(sub), len(geo)))
        log(f"rozpoznanie {pkg.code} {pkg.name()}")

    assert p0 is not None
    sp = p0.table("f_tree_species_dic.txt").drop_duplicates("species_cd", keep="last")
    names["species_main"] = dict(zip(sp["species_cd"], sp["species_name"] + " (" + sp["latin_name"] + ")"))
    st = p0.table("f_site_type_dic.txt")
    names["site"] = dict(zip(st["site_type_cd"], st["site_type_name"]))
    ad = p0.table("f_area_type_dic.txt").drop_duplicates("area_type_cd", keep="last")
    names["area"] = dict(zip(ad["area_type_cd"], ad["area_type_name"] + " [type_fl=" + ad["type_fl"] + "]"))
    fd = p0.table("f_forest_func_dic.txt")
    names["func"] = dict(zip(fd["forest_func_cd"], fd["forest_func_name"]))
    pd_ = p0.table("f_prot_categ_dic.txt")
    names["prot"] = dict(zip(pd_["prot_category_cd"], pd_["prot_category_name"]))
    sd = p0.table("f_storey_dic.txt")
    names["storey"] = dict(zip(sd["storey_cd"], sd["storey_name"]))
    pt = p0.table("f_part_dic.txt")
    names["part"] = dict(zip(pt["part_cd"], pt["part_name"]))

    md = [
        "# Rozpoznanie danych BDL",
        "",
        "Raport generowany automatycznie (`python -m grzyby rozpoznanie`).",
        "",
        "## Paczki",
        "",
        "| kod | nadleśnictwo | wydzieleń w f_subarea.txt | poligonów w G_SUBAREA |",
        "|---|---|---:|---:|",
        *[f"| {a} | {b} | {c_} | {d} |" for a, b, c_, d in per_pkg],
        f"| | **razem** | **{n_txt}** | **{n_geom}** |",
        "",
        "## Układ współrzędnych i kodowanie",
        "",
        *[f"- `.prj`: {k} ({v} paczek)" for k, v in crs_seen.items()],
        *[f"- pliki tekstowe: kodowanie `{k}` ({v} plików sprawdzonych)" for k, v in enc_seen.items()],
        f"- kolumny `G_SUBAREA`: {', '.join(f'`{x}`' for x in c['subarea_cols'])}",
        "",
        "## Składy gatunkowe",
        "",
        f"`f_storey_species.txt` zawiera pełne składy (wszystkie gatunki w każdym piętrze z udziałem, wiekiem, "
        f"wysokością). Wydzieleń z drzewostanem (DRZEW/IP): {n_stands}, w tym z więcej niż jednym gatunkiem: "
        f"{n_multi} ({n_multi / max(1, n_stands):.0%}). `G_SUBAREA` ma tylko gatunek panujący (`species_cd`).",
        "",
        "### Gatunki drzew w piętrach DRZEW/IP/IIP",
        _md_counts(c["species_main"], names["species_main"]),
        "",
        "### Typy siedliskowe lasu (`site_type_cd`)",
        _md_counts(c["site"], names["site"]),
        "",
        "### Rodzaje powierzchni (`area_type_cd`, 40 najczęstszych)",
        _md_counts(c["area"], names["area"], top=40),
        "",
        "### Funkcja lasu (`forest_func_cd`)",
        _md_counts(c["func"], names["func"]),
        "",
        "### Kategorie ochronności (`f_arod_category.prot_category_cd`)",
        _md_counts(c["prot"], names["prot"]),
        "",
        "### Piętra (`storey_cd`)",
        _md_counts(c["storey"], names["storey"]),
        "",
        "### Udziały (`part_cd_act`)",
        _md_counts(c["part"], names["part"]),
        "",
    ]
    out = paths.out / "rozpoznanie.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"zapisano {out}")
    return str(out)
