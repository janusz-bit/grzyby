"""Konfiguracja, ścieżki i drobne narzędzia wspólne dla etapów pipeline'u."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

ROOT = Path.cwd()


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def load_config(path: str | Path = "config.yaml") -> dict:
    with open(ROOT / path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    # YAML czyta klucze miesięcy jako int, kody gatunków jako str – ujednolicamy.
    for sp in cfg["gatunki"].values():
        sp["sezon"] = {int(k): float(v) for k, v in (sp.get("sezon") or {}).items()}
        sp["zywiciele"] = {str(k): float(v) for k, v in sp["zywiciele"].items()}
        sp["siedliska"] = {str(k): float(v) for k, v in sp["siedliska"].items()}
    return cfg


@dataclass(frozen=True)
class Paths:
    raw: Path
    work: Path
    out: Path

    @classmethod
    def from_config(cls, cfg: dict) -> "Paths":
        d = cfg["dane"]
        p = cls(ROOT / d["katalog_surowe"], ROOT / d["katalog_robocze"], ROOT / d["katalog_wyniki"])
        for x in (p.raw, p.work, p.out):
            x.mkdir(parents=True, exist_ok=True)
        return p

    # Pliki pośrednie
    @property
    def stands(self) -> Path:  # wydzielenia: atrybuty + potencjał siedliskowy
        return self.work / "wydzielenia.gpkg"

    @property
    def static_payload(self) -> Path:  # zakodowana geometria i atrybuty dla mapy
        return self.work / "mapa_statyczne.json"

    @property
    def grid(self) -> Path:
        return self.work / "siatka_pogody.json"

    @property
    def weather_raw(self) -> Path:
        return self.work / "pogoda_open_meteo.json"

    @property
    def weather_index(self) -> Path:
        return self.work / "pogoda_wskaznik.json"

    @property
    def gbif(self) -> Path:
        return self.work / "gbif.json"

    @property
    def gbif_report(self) -> Path:
        return self.work / "gbif_weryfikacja.json"


def curve(x, points) -> np.ndarray:
    """Interpolacja liniowa po punktach [[x, y], ...] z wartościami brzegowymi poza zakresem."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return np.interp(np.asarray(x, dtype=float), xs, ys)


def same_projection(a, b) -> bool:
    """Porównanie parametrów odwzorowania (BDL zapisuje CS92 w wariancie ESRI bez kodu EPSG)."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return a.to_proj4() == b.to_proj4()


def species_keys(cfg: dict) -> list[str]:
    return list(cfg["gatunki"].keys())


def write_json(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)


def read_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
