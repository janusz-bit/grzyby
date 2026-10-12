"""Pobieranie i wczytywanie paczek Banku Danych o Lasach (BDL)."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
import requests

from .common import ROOT, Paths, log

URL_RE = re.compile(r"https://\S+?file=(\S+\.zip)")


def package_urls(cfg: dict) -> list[tuple[str, str]]:
    """(nazwa_pliku, url) z pliku z linkami (dane.txt)."""
    text = (ROOT / cfg["dane"]["bdl_lista"]).read_text(encoding="utf-8")
    return [(m.group(1), m.group(0)) for m in URL_RE.finditer(text)]


def download(cfg: dict, paths: Paths) -> list[Path]:
    files = []
    for name, url in package_urls(cfg):
        dest = paths.raw / name
        if not dest.exists() or dest.stat().st_size == 0:
            log(f"pobieram {name}")
            r = requests.get(url, timeout=300)
            r.raise_for_status()
            tmp = dest.with_suffix(".part")
            tmp.write_bytes(r.content)
            tmp.replace(dest)
        files.append(dest)
    log(f"paczek BDL: {len(files)}")
    return files


class Package:
    """Jedna paczka BDL (zip) – dostęp do tabel tekstowych i warstw SHP bez rozpakowywania."""

    def __init__(self, path: Path, encodings: list[str]):
        self.path = path
        self.zip = zipfile.ZipFile(path)
        self.prefix = next(n for n in self.zip.namelist() if n.endswith("/")).rstrip("/")
        self.encodings = encodings
        self.detected_encoding: dict[str, str] = {}

    @property
    def code(self) -> str:  # np. 01_02
        m = re.search(r"BDL_(\d\d_\d\d)_", self.path.name)
        return m.group(1) if m else self.path.stem

    def raw(self, name: str) -> bytes:
        return self.zip.read(f"{self.prefix}/{name}")

    def text(self, name: str) -> str:
        data = self.raw(name)
        for enc in self.encodings:
            try:
                txt = data.decode(enc)
                self.detected_encoding[name] = enc
                return txt
            except UnicodeDecodeError:
                continue
        raise UnicodeDecodeError(name, data, 0, 1, f"żadne z kodowań {self.encodings} nie pasuje")

    def table(self, name: str) -> pd.DataFrame:
        df = pd.read_csv(io.StringIO(self.text(name)), sep="\t", dtype=str, keep_default_na=False,
                         quoting=3)
        for c in df.columns:
            df[c] = df[c].str.strip()
        return df

    def layer(self, name: str) -> gpd.GeoDataFrame:
        return pyogrio.read_dataframe(f"/vsizip/{self.path}/{self.prefix}/{name}.shp")

    def prj(self, name: str = "G_SUBAREA") -> str:
        return self.raw(f"{name}.prj").decode("ascii", "replace")

    def name(self) -> str:
        return self.table("f_inspectorate.txt")["inspectorate_name"].iloc[0]


def open_packages(cfg: dict, paths: Paths) -> list[Package]:
    encs = cfg["dane"]["kodowanie_txt"]
    return [Package(p, encs) for p in download(cfg, paths)]


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.replace("", None), errors="coerce")


def clean_address(a: str) -> str:
    """'01-02-1-01-123   -a   -00' -> '01-02-1-01-123-a-00'"""
    return "-".join(p.strip() for p in a.split("-") if p.strip() != "") if a else ""
