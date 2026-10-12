# Rozpoznanie danych BDL

Raport generowany automatycznie (`python -m grzyby rozpoznanie`).

## Paczki

| kod | nadleśnictwo | wydzieleń w f_subarea.txt | poligonów w G_SUBAREA |
|---|---|---:|---:|
| 01_01 | Augustów | 10479 | 8599 |
| 01_02 | Białowieża | 4686 | 4085 |
| 01_03 | Bielsk | 9275 | 8096 |
| 01_04 | Borki | 11897 | 10047 |
| 01_05 | Browsk | 6954 | 5959 |
| 01_06 | Czarna Białostocka | 9744 | 7815 |
| 01_07 | Czerwony Dwór | 9129 | 7697 |
| 01_08 | Dojlidy | 7173 | 6105 |
| 01_09 | Drygały | 13892 | 11467 |
| 01_10 | Ełk | 10514 | 9059 |
| 01_11 | Giżycko | 12043 | 10182 |
| 01_12 | Głęboki Bród | 3378 | 2626 |
| 01_13 | Gołdap | 6503 | 5440 |
| 01_14 | Hajnówka | 8420 | 7307 |
| 01_28 | Knyszyn | 4971 | 4045 |
| 01_29 | Krynki | 5906 | 4906 |
| | **razem** | **134964** | **113435** |

## Układ współrzędnych i kodowanie

- `.prj`: `ETRS_1989_Poland_CS92` (pyproj: ETRF2000-PL / CS92) → EPSG:2180, parametry identyczne z EPSG:2180 (16 paczek)
- pliki tekstowe: kodowanie `utf-8` (64 plików sprawdzonych)
- kolumny `G_SUBAREA`: `a_i_num`, `adr_for`, `area_type`, `site_type`, `silvicult`, `forest_fun`, `stand_stru`, `rotat_age`, `sub_area`, `prot_categ`, `species_cd`, `part_cd`, `spec_age`, `a_year`, `geometry`

## Składy gatunkowe

`f_storey_species.txt` zawiera pełne składy (wszystkie gatunki w każdym piętrze z udziałem, wiekiem, wysokością). Wydzieleń z drzewostanem (DRZEW/IP): 91263, w tym z więcej niż jednym gatunkiem: 88918 (97%). `G_SUBAREA` ma tylko gatunek panujący (`species_cd`).

### Gatunki drzew w piętrach DRZEW/IP/IIP
| kod | liczba | opis |
|---|---:|---|
| `ŚW` | 152237 | świerk pospolity (Picea abies) |
| `BRZ` | 108256 | brzoza brodawkowata (Betula pendula) |
| `SO` | 76926 | sosna zwyczajna (pinus silvestris) |
| `DB` | 69038 | dąb nieokreślony (Quercus species) |
| `OL` | 62123 | olsza czarna (Alnus glutinosa) |
| `GB` | 51175 | grab pospolity (Carpinus betulus) |
| `LP` | 33508 | lipa drobnolistna (Tilia cordata) |
| `OS` | 30671 | topola osika (Populus tremula) |
| `KL` | 26807 | klon pospolity (Acer platanoides) |
| `DB.S` | 23065 | dąb szypułkowy (Quercus robur) |
| `JS` | 16266 | jesion wyniosły (Fraxinus excelsior) |
| `MD` | 11138 | modrzew europejski (Larix decidua) |
| `WZ` | 8523 | wiąz pospolity (Ulmus) |
| `DB.C` | 3959 | dąb czerwony (Quercus rubra) |
| `JW` | 3686 | klon jawor (Acer pseudoplatanus) |
| `IWA` | 3265 | wierzba iwa (Salix caprea) |
| `BK` | 2273 | buk pospolity (Fagus silvatica) |
| `WB` | 1758 | wierzba biała (Salix alba) |
| `BRZ.O` | 1695 | brzoza omszona (Betula pubescens) |
| `JB` | 601 | jabłoń dzika (Malus silvestris) |
| `OL.S` | 555 | olsza szara (Alnus incana) |
| `GR` | 413 | grusza pospolita (Pyrus communis) |
| `AK` | 366 | robinia akacjowa (Robinia pseudoacacia) |
| `CZM` | 316 | czeremcha pospolita (Prunus padus) |
| `JKL` | 293 | klon jesionolistny (Acer negundo) |
| `JRZ` | 252 | jarząb pospolity (Sorbus aucuparia) |
| `CZM.P` | 200 | czeremcha późna (Prunus serotina) |
| `CZR` | 190 | czereśnia pospolita () |
| `CZR.P` | 184 | czereśnia ptasia (Prunus avium) |
| `TP` | 179 | topola biała (Populus alba) |
| `BST` | 129 | wiąz górski (Ulmus glabra) |
| `KSZ` | 100 | kasztanowiec biały (Aesculus hippocastanum) |
| `SO.WE` | 91 | sosna wejmutka (Pinus strobus) |
| `JD` | 86 | jodła pospolita (Abies alba) |
| `DG` | 71 | daglezja zielona (Pseudotsuga menziesii) |
| `TP.C` | 54 | topola czarna (Populus nigra) |
| `ŚL` | 44 | śliwa domowa (Prunus domestica) |
| `GŁG` | 35 | głóg jednoszyjkowy (Crataegus monogyna) |
| `JS.A` | 27 | jesion amerykanski (Fraxinus americana) |
| `WIŚ` | 26 | wiśnia pospolita (Prunus cerasus) |
| `SO.B` | 17 | sosna Banksa (Pinus banksiana) |
| `ŚL.A` | 13 | śliwa ałycza () |
| `DB.B` | 11 | dąb bezszypułkowy (Quercus petraea) |
| `LSZ` | 9 | leszczyna pospolita (Corylus avellana) |
| `SO.S` | 6 | sosna smołowa (Pinus rigida) |
| `SO.C` | 4 | sosna czarna (Pinus nigra) |
| `CIS` | 4 | cis pospolity (Taxus baccata) |
| `ŻYW.O` | 4 | żywotnik olbrzymi (Thuja plicata) |
| `ŻYW.Z` | 4 | żywotnik zachodni (Thuja occidentalis) |
| `JAŁ` | 3 | jałowiec pospolity (Juniperus communis) |
| `SZK` | 3 | szakłak pospolity (Rhamnus cathartica) |
| `ŚL.T` | 2 | śliwa tarnina (Prunus spinosa) |
| `ŚW.SR` | 2 | świerk srebrny (Picea pungens) |
| `BEZ.C` | 1 | bez czarny (Sambucus nigra) |
| `TS.K` | 1 | choina kanadyjska (Tsuga canadensis) |
| `PRZ.C` | 1 | porzeczka czarna (Ribes nigrum) |
| `BEZ.K` | 1 | bez koralowy (Sambucus racemosa) |
| `ŻYW.W` | 1 | żywotnik wschodni (Thuja orintalis) |
| `ŚW.SE` | 1 | świerk serbski (Picea omorika) |
| `KL.P` | 1 | klon polny (Acer campestre) |

### Typy siedliskowe lasu (`site_type_cd`)
| kod | liczba | opis |
|---|---:|---|
| `(puste)` | 38808 |  |
| `BMŚW` | 25048 | Bór mieszany świeży |
| `LMŚW` | 21155 | Las mieszany świeży |
| `LŚW` | 14732 | Las świeży |
| `BŚW` | 6231 | Bór świeży |
| `OL` | 6141 | Ols |
| `LW` | 5816 | Las wilgotny |
| `LMW` | 4529 | Las mieszany wilgotny |
| `LMB` | 4267 | Las mieszany bagienny |
| `BMW` | 3301 | Bór mieszany wilgotny |
| `OLJ` | 2862 | Ols jesionowy |
| `BMB` | 1382 | Bór mieszany bagienny |
| `BB` | 453 | Bór bagienny |
| `BW` | 151 | Bór wilgotny |
| `LŁ` | 56 | Las łęgowy |
| `BS` | 32 | Bór suchy |

### Rodzaje powierzchni (`area_type_cd`, 40 najczęstszych)
| kod | liczba | opis |
|---|---:|---|
| `D-STAN` | 90330 | drzewostan [type_fl=L] |
| `DROGI L` | 10186 | drogi leśne [type_fl=L] |
| `LINIE` | 8429 | linie nie stanowiące podziału [type_fl=L] |
| `BAGNO` | 4876 | bagno [type_fl=N] |
| `SUKCESJA` | 3538 | sukcesja [type_fl=L] |
| `ROWY` | 2429 | rowy na lasach [type_fl=L] |
| `R` | 2159 | rola [type_fl=N] |
| `PS` | 2158 | pastwisko trwałe [type_fl=N] |
| `L ENERG` | 1487 | linia energetyczna [type_fl=L] |
| `Ł` | 1159 | łąka [type_fl=N] |
| `ZRĄB` | 803 | zrąb [type_fl=L] |
| `PŁAZ` | 742 | płazowina [type_fl=L] |
| `ZADRZEW` | 603 | zadrzewienie, parki wiejskie [type_fl=N] |
| `Ł-ROWY` | 563 | rowy na łąkach [type_fl=N] |
| `POL ŁOW` | 412 | poletko łowieckie [type_fl=L] |
| `LZR-PS` | 326 | zadrz. i zakrz. na pastwiskach [type_fl=N] |
| `SKŁAD DR` | 287 | składnica drewna [type_fl=L] |
| `LZ` | 268 | zadrzewienia pozostałe [type_fl=N] |
| `LZR-Ł` | 222 | zadrz. i zakrz. na łąkach [type_fl=N] |
| `BUD INNE` | 198 | inne tereny zabudowane [type_fl=L] |
| `PS-ROWY` | 194 | rowy na pastwiskach [type_fl=N] |
| `TURYST` | 180 | miejsce turystyczne [type_fl=L] |
| `PL ŁOW-R` | 177 | poletko łowieckie na roli [type_fl=N] |
| `L-CTWO` | 160 | leśnictwo [type_fl=L] |
| `KOLEJ L` | 159 | kolejka leśna [type_fl=L] |
| `PAS PPOŻ` | 157 | pas przeciwpożarowy [type_fl=L] |
| `R-ROWY` | 156 | rowy na rolach [type_fl=N] |
| `RZEKA` | 154 | rzeka [type_fl=N] |
| `N-E` | 138 | użytek ekol. na nieużytkach [type_fl=N] |
| `PAS GRAN` | 134 | pas graniczny [type_fl=L] |
| `DROGI I` | 128 | inne drogi (bez dróg leśnych) [type_fl=N] |
| `LZR-R` | 128 | zadrz. i zakrz. na rolach [type_fl=N] |
| `ZAB INNE` | 125 | inne tereny zabudowane [type_fl=N] |
| `BR-R` | 109 | bud. i urządz. na roli [type_fl=N] |
| `INNE BUD` | 100 | tereny zabudowane inne [type_fl=N] |
| `WRZOS` | 100 | wrzosowisko [type_fl=N] |
| `PIASKI` | 78 | piaski [type_fl=N] |
| `E-N` | 78 | użytek ekol. na nieużytkach [type_fl=N] |
| `TER ZDEW` | 78 | tereny zdewastowane [type_fl=N] |
| `ZBIORNIK` | 70 | zbiornik wody [type_fl=N] |

### Funkcja lasu (`forest_func_cd`)
| kod | liczba | opis |
|---|---:|---|
| `GOSP` | 89053 | lasy gospodarcze |
| `(puste)` | 39117 |  |
| `REZ` | 4962 | rezerwat |
| `REZ CZ` | 1831 | rezerwat częściowy |
| `OCHR` | 1 | lasy ochronne |

### Kategorie ochronności (`f_arod_category.prot_category_cd`)
| kod | liczba | opis |
|---|---:|---|
| `OCH CENNE` | 44373 | cenne fragm. Przyrody |
| `OCH WOD` | 26668 | wodochronne |
| `OCH MIAST` | 9744 | w miastach i wokół miast |
| `OCH OSTOJ` | 4236 | ostoje zwierząt |
| `OCH OBR` | 3638 | obronne |
| `OCH UZDR` | 378 | uzdrowiskowe |
| `OCH BADAW` | 304 | stałe pow. badaw. i dośw. |
| `OCH GLEB` | 199 | glebochronne |
| `OCH NAS` | 73 | nasienne |

### Piętra (`storey_cd`)
| kod | liczba | opis |
|---|---:|---|
| `DRZEW` | 669103 | warstwa drzew |
| `PODSZ` | 339648 | podszyt |
| `PRZES` | 40320 | przestoje, nasienniki i przedr |
| `PODR` | 38858 | podrost |
| `PODRII` | 28676 | podrost o charakt. II piętra |
| `ZAKRZEW` | 19712 | zakrzewienie |
| `ZADRZEW` | 19022 | zadrzewienie |
| `IP` | 11505 | piętro pierwsze |
| `IIP` | 10062 | piętro drugie |
| `NAL` | 4872 | nalot |
| `PODS` | 4402 | podsadzenia pod osłoną |
| `SAMOS` | 494 | samosiew |
| `PLANT` | 49 | plantacja choinkowa |

### Udziały (`part_cd_act`)
| kod | liczba | opis |
|---|---:|---|
| `(puste)` | 419056 |  |
| `MJS` | 329389 | poniżej 5 % - miejscami |
| `1` | 108472 | udział 10 % |
| `PJD` | 105612 | ponizej 5 % - pojedynczo |
| `2` | 61252 | udział 20 % |
| `10` | 35243 | udział 100 % |
| `3` | 34560 | udział 30 % |
| `4` | 20893 | udział 40 % |
| `6` | 16209 | udział 60 % |
| `5` | 16152 | udział 50 % |
| `7` | 15594 | udział 70 % |
| `8` | 14009 | udział 80 % |
| `9` | 10282 | udział 90 % |
