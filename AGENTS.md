# AGENTS.md

Wskazówki dla agentów kodujących (Claude Code, Codex itp.) pracujących w tym repozytorium.

## Co to jest

Pipeline w Pythonie, który z paczek Banku Danych o Lasach (BDL), pogody z Open-Meteo i obserwacji
GBIF buduje jeden plik `output/mapa.html` (MapLibre GL z CDN, podkład OSM). Mapa pokazuje dla
wydzieleń leśnych potencjał siedliskowy × wskaźnik pogodowy dla 7 gatunków grzybów. Opis modelu
i wnioski z rozpoznania danych są w `README.md`, a pierwotne wymagania w `PLAN.md`.

## Środowisko i komendy

- System docelowy to NixOS. Zależności są tylko we `flake.nix` (`python3.withPackages`: geopandas,
  pyogrio, shapely, pyproj, pandas, numpy, requests, pyyaml). Nie używaj `pip install`; nową
  zależność dodaj do flake'a.
- Komendy uruchamiaj w katalogu repo: kod czyta `config.yaml`, `dane.txt`, `data/` i `output/`
  względem bieżącego katalogu.
  - `nix run .#mapa` lub `nix develop -c python -m grzyby` – pełny pipeline (~15 min na RPi 4)
  - `nix run .#pogoda` lub `python -m grzyby pogoda` – tylko pogoda i HTML (~3–4 min, w tym
    dławienie API); `--force` omija 3-godzinny cache
  - `nix run .#zrzut` – test w headless Chromium: zrzuty, liczba wyrenderowanych wydzieleń,
    błędy JS, popup
  - pozostałe etapy: `python -m grzyby rozpoznanie|gbif|mapa|zrzut`
- Flake widzi tylko pliki śledzone przez gita. Po dodaniu nowego pliku zrób `git add`, zanim
  uruchomisz `nix run`.
- Na Raspberry Pi (aarch64) część pakietów Pythona może nie być w cache binarnym i kompiluje się
  długo, z testami. Nie przerywaj `nix build` ani `nix develop` w trakcie, bo zaczną od nowa.

## Mapa kodu

| plik | odpowiedzialność |
|---|---|
| `grzyby/common.py` | konfiguracja, ścieżki plików pośrednich (`Paths`), `curve()` (interpolacja krzywych z configu) |
| `grzyby/bdl.py` | pobieranie paczek z `dane.txt`, czytanie TXT/SHP bezpośrednio z zipa (`/vsizip/`) |
| `grzyby/rozpoznanie.py` | Krok 1: raport `output/rozpoznanie.md` z realnych kodów |
| `grzyby/habitat.py` | Krok 2 i 4: składy z `f_storey_species.txt`, czynniki żywiciela, wieku i siedliska, wykluczenia → `data/work/wydzielenia.gpkg` |
| `grzyby/weather.py` | Krok 3: siatka 5 km (EPSG:2180), Open-Meteo (multi-location, limiter), wskaźnik na dziś/+3/+7 |
| `grzyby/gbif.py` | Krok 6: pobranie obserwacji, przypisanie do wydzieleń, statystyki |
| `grzyby/mapa.py` | Krok 5: uproszczenie i kodowanie geometrii (delty 1e-5°, gzip, base64), składanie HTML |
| `grzyby/szablon.html` | mapa: dekodowanie danych, wyrażenia kolorów MapLibre, panel, popup |
| `grzyby/zrzut.py` | minimalny klient DevTools Protocol (stdlib) do testu mapy |

## Niezmienniki – pilnuj ich przy zmianach

- **Format payloadu**: `mapa.build_static` (Python) i funkcje `geojson()`/`popupHtml()` w
  `szablon.html` (JS) muszą zgadzać się co do kluczy w `D.f`: `geom`, `comp` (po 5 pól na wiersz
  składu), `ws` (pary kod–udział ważony w %), `warn`, a na gatunek `p_`, `hs_`, `uf_`, `af_`, `hz_`
  i `sf_` (×100, znaczenie opisuje docstring `habitat.host_scores`). Zmieniasz jedną stronę, zmień
  drugą. JS nie liczy modelu od nowa, tylko wyświetla liczby z Pythona.
- **Szybkie odświeżenie pogody** (`etap pogoda`) nie może wczytywać `wydzielenia.gpkg`. Korzysta
  tylko z `data/work/mapa_statyczne.json` i `siatka_pogody.json`. Indeks węzła siatki (`g`)
  w payloadzie statycznym musi odpowiadać kolejności `wezly` w `siatka_pogody.json`. Pilnuje tego
  `siatka_podpis` (sprawdzany w `mapa.render`), a w pełnym pipeline siatka i dane statyczne są
  zapisywane przed krokami sieciowymi.
- **Kod wykluczenia 0 = dostępne**: `wykluczenia[0]` to pusty napis, a filtr warstw w JS zakłada
  `x == 0`.
- **Wszystkie progi i reguły trzymaj w `config.yaml`**, nie w kodzie. Nowe parametry modelu opisuj
  komentarzem w configu.
- **Nie zgaduj kodów BDL.** Sprawdź je w `output/rozpoznanie.md` albo w słownikach `f_*_dic.txt`
  w paczce. Kody mają polskie znaki (`ŚW`, `BMŚW`), a wartości w plikach TXT mają spacje
  dopełniające, które `Package.table()` obcina.
- Pliki TXT z BDL są w UTF-8 (sprawdzone dla paczek 2026). `kodowanie_txt` w configu ma CP1250
  jako zapasowe.
- `.prj` to ESRI-owy opis CS92. `habitat.build` sprawdza parametry odwzorowania
  i ustawia EPSG:2180. Nie usuwaj tego sprawdzenia.

## Zasady

- UI mapy, config, logi i dokumentacja są po polsku. Identyfikatory w Pythonie mogą być angielskie.
- Nie commituj `data/` ani `output/` (są w `.gitignore`). Surowe dane BDL mają warunki ponownego
  wykorzystania: podanie źródła i daty, zgłoszenie przetworzenia na bdl@bdl.lasy.gov.pl.
- Open-Meteo bez klucza ma limity 600 wywołań/min, 5000/h i 10000/dobę. Lokalizacja z ~38 dniami
  danych liczy się jako ~2,7 wywołania. Nie zwiększaj `limit_wywolan_na_minute` powyżej 600
  i nie wyłączaj cache.
- Mapa ma zawsze pokazywać ostrzeżenie, że prezentuje potencjał, a nie pewność, i nie służy do
  oceny jadalności. Nie usuwaj go ani nie osłabiaj.
- Plik `output/mapa.html` ma mieć mniej niż 20 MB. Po zmianach w payloadzie sprawdź rozmiar
  w logu `mapa:`.
- Po zmianach w `szablon.html` uruchom `nix run .#zrzut`. W `output/zrzut_raport.json` ma być
  `bledy_js: []`, niezerowe `kontrola.pot` i niepusty `popup`.
