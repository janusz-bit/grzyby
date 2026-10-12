"""Uruchamianie: python -m grzyby [wszystko|pogoda|rozpoznanie|gbif|mapa|zrzut]"""

from __future__ import annotations

import argparse
import time

from . import gbif, habitat, mapa, rozpoznanie, weather, zrzut
from .common import Paths, load_config, log


def full(cfg: dict, paths: Paths, force_weather: bool) -> None:
    rozpoznanie.run(cfg, paths)
    stands = habitat.build(cfg, paths)
    pts = stands.geometry.representative_point()
    grid_idx = weather.build_grid(pts.get_coordinates().to_numpy(), cfg, paths)
    weather.run(cfg, paths, force=force_weather)
    rows = gbif.fetch(cfg, paths, stands)
    gbif.evaluate(cfg, paths, stands, rows)
    mapa.build_static(cfg, paths, stands, grid_idx)
    mapa.render(cfg, paths)
    zrzut.run(cfg, paths)


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m grzyby", description="Mapa potencjału grzybów (BDL + Open-Meteo + GBIF)")
    ap.add_argument("etap", nargs="?", default="wszystko",
                    choices=["wszystko", "pogoda", "rozpoznanie", "gbif", "mapa", "zrzut"],
                    help="wszystko = pełny pipeline; pogoda = szybkie odświeżenie pogody i mapy")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--force", action="store_true", help="pobierz pogodę mimo świeżego cache")
    a = ap.parse_args()
    cfg = load_config(a.config)
    paths = Paths.from_config(cfg)
    t0 = time.time()
    if a.etap == "wszystko":
        full(cfg, paths, a.force)
    elif a.etap == "pogoda":
        if not paths.static_payload.exists() or not paths.grid.exists():
            raise SystemExit("brak danych statycznych – najpierw uruchom pełny pipeline (python -m grzyby)")
        weather.run(cfg, paths, force=a.force)
        mapa.render(cfg, paths)
    elif a.etap == "rozpoznanie":
        rozpoznanie.run(cfg, paths)
    elif a.etap == "gbif":
        import geopandas as gpd
        stands = gpd.read_file(paths.stands, engine="pyogrio")
        gbif.evaluate(cfg, paths, stands, gbif.fetch(cfg, paths, stands))
        mapa.render(cfg, paths)
    elif a.etap == "mapa":
        mapa.render(cfg, paths)
    elif a.etap == "zrzut":
        zrzut.run(cfg, paths)
    log(f"gotowe w {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
