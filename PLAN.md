Zbuduj mapę potencjalnych miejsc występowania grzybów jadalnych dla województwa podlaskiego.

Stwórz odpowiedni plik `AGENTS.md` dla tego projektu. Udostępnij projekt na github.

## Dane
- zobacz plik dane.txt
- Resztę pobierz sam przez publiczne API bez kluczy: pogoda z Open-Meteo, obserwacje z GBIF, podkład z OpenStreetMap.

## Środowisko
- Python. Jeśli system to NixOS (sprawdź /etc/os-release), przygotuj flake.nix z devShell (python3.withPackages: geopandas, pyogrio, shapely, pyproj, pandas, numpy, requests, pyyaml) zamiast pip.
- Cały pipeline uruchamiany jedną komendą, plus osobna, szybka komenda odświeżająca tylko pogodę.
- Wszystkie progi i reguły trzymaj w config.yaml, żebym mógł je stroić.

## Krok 1 — rozpoznanie danych
Najpierw obejrzyj dane: układ współrzędnych (spodziewany EPSG:2180, sprawdź .prj), kodowanie plików tekstowych (może być CP1250), kolumny g_subarea, faktycznie występujące kody gatunków (np. SO, ŚW, BK, DB, BRZ, OS) i typów siedliskowych (np. Bs, Bśw, BMśw, LMśw). Nie zgaduj kodów — wypisz realne wartości. Sprawdź, czy pliki tekstowe zawierają pełne składy gatunkowe z domieszkami; jeśli tak, użyj ich, a nie tylko gatunku panującego. Wnioski zapisz w README.

## Krok 2 — potencjał siedliskowy (0–1) dla każdego wydzielenia i gatunku
Reguły startowe (gatunek grzyba: drzewa-żywiciele; wiek drzewostanu; siedliska):
- borowik szlachetny (Boletus edulis): świerk, sosna, buk, dąb, słabiej brzoza; najlepiej ≥ 40 lat; bory świeże, bory mieszane, lasy mieszane, lasy świeże
- podgrzybek brunatny (Imleria badia): sosna, świerk; ≥ 20 lat; bory i bory mieszane świeże i wilgotne
- koźlarz babka (Leccinum scabrum): brzoza, także jako domieszka
- koźlarz czerwony (Leccinum aurantiacum): osika, także jako domieszka
- maślak zwyczajny (Suillus luteus): sosna; 10–30 lat; bory suche i świeże
- rydz (Lactarius deliciosus z sosną, L. deterrimus ze świerkiem): 10–30 lat; bory i bory mieszane świeże
- kurka (Cantharellus cibarius): sosna, świerk, buk, dąb; ≥ 20 lat; ubogie, kwaśne siedliska borowe i mieszane
Wynik zależy od udziału żywiciela w drzewostanie oraz dopasowania wieku i siedliska. Siedliska bagienne i olsy: niski potencjał.

## Krok 3 — wskaźnik pogodowy (0–1)
Z Open-Meteo pobierz dane dzienne (ostatnie ~30 dni + prognoza 7 dni) dla siatki punktów co ~5 km w obrębie nadleśnictwa: suma opadów, temperatura min i średnia, a jeśli dostępna — wilgotność gleby. Nazwy zmiennych sprawdź w dokumentacji API. Heurystyka startowa:
- suma opadów z 14 dni: < 15 mm słabo, 15–40 mm rośnie, > 40 mm pełna wartość; wysyp zwykle 7–14 dni po obfitym deszczu
- średnia temperatura z 7 dni: optimum 10–20°C; poniżej 5°C lub powyżej 25°C słabo
- przymrozek (Tmin < −1°C) w ostatnich 5 dniach mocno obniża wskaźnik
- sezon gatunku (np. kurka VI–IX, borowik VI–X, podgrzybek VIII–XI); poza sezonem 0
Każdemu wydzieleniu przypisz najbliższy punkt siatki. Policz wskaźnik na dziś oraz na +3 i +7 dni z prognozy.

## Krok 4 — wykluczenia
Oznacz jako „niedostępne”: rezerwaty i inne formy ochrony wykluczające zbiór (atrybut kategorii ochrony z BDL), uprawy leśne (stały zakaz wstępu do upraw do 4 m wysokości — przyjmij drzewostany < ~10 lat, chyba że BDL ma lepszy atrybut) oraz powierzchnie nieleśne.

## Krok 5 — mapa
Jeden plik `output/mapa.html` (MapLibre GL lub Leaflet z CDN, podkład OSM), działający po otwarciu w przeglądarce:
- przełącznik gatunku + widok „dowolny gatunek” (maksimum) oraz przełącznik dnia (dziś / +3 / +7)
- kolor wydzielenia = potencjał siedliskowy × wskaźnik pogodowy; wykluczone szare i kreskowane
- popup: adres leśny, skład i wiek drzewostanu, siedlisko, oba wyniki składowe i krótkie uzasadnienie
- legenda, data aktualizacji pogody i widoczna informacja, że mapa pokazuje potencjał, a nie pewność, i nie służy do oceny jadalności
Przelicz do EPSG:4326, uprość geometrię i zaokrąglij współrzędne, żeby plik był lekki (cel < 20 MB).

## Krok 6 — weryfikacja
- Pobierz z GBIF obserwacje powyższych gatunków w obrębie nadleśnictwa (lub szerzej, jeśli jest ich mało) i dodaj je jako opcjonalną warstwę. Policz, jaki odsetek wpada w wydzielenia o wysokim potencjale. To tylko sanity check, nie trening.
- Jeśli dostępna jest przeglądarka headless, zrób zrzut ekranu mapy i sprawdź, czy się renderuje.
- W README opisz: jak uruchomić, skąd dane, ograniczenia modelu.
