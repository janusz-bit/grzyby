{
  description = "Mapa potencjalnych miejsc występowania grzybów jadalnych (BDL + Open-Meteo + GBIF)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      pythonEnv = pkgs: pkgs.python3.withPackages (ps: with ps; [
        geopandas
        pyogrio
        shapely
        pyproj
        pandas
        numpy
        requests
        pyyaml
      ]);

      # Aplikacje uruchamiają kod z repozytorium, a config.yaml, dane.txt, data/ i output/
      # biorą z bieżącego katalogu – uruchamiaj je w katalogu projektu.
      app = pkgs: name: etap: extraPath: {
        type = "app";
        program = toString (pkgs.writeShellScript "grzyby-${name}" ''
          export PYTHONPATH=${self}''${PYTHONPATH:+:$PYTHONPATH}
          ${pkgs.lib.optionalString (extraPath != [ ]) "export PATH=${pkgs.lib.makeBinPath extraPath}:$PATH"}
          exec ${pythonEnv pkgs}/bin/python -m grzyby ${etap} "$@"
        '');
      };
    in
    {
      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [ (pythonEnv pkgs) ];
        };
      });

      apps = forAll (pkgs: rec {
        # pełny pipeline: BDL -> siedliska -> pogoda -> GBIF -> output/mapa.html
        mapa = app pkgs "mapa" "wszystko" [ ];
        # szybkie odświeżenie: tylko pogoda + przebudowa HTML
        pogoda = app pkgs "pogoda" "pogoda" [ ];
        # zrzut ekranu mapy przeglądarką headless (Chromium z nixpkgs, tylko Linux)
        zrzut = app pkgs "zrzut" "zrzut" (pkgs.lib.optional pkgs.stdenv.isLinux pkgs.chromium);
        default = mapa;
      });
    };
}
