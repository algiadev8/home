{
  config,
  pkgs,
  lib,
  ...
}:

let
  cfg = config.my.lang.haskell;
in
{
  options.my.lang.haskell.enable = lib.mkEnableOption "Haskell language support";

  config = lib.mkIf cfg.enable {
    home.packages = with pkgs; [
      ghc
      cabal-install
      stack
      ghcid
      haskell-language-server
      fourmolu
      hlint
      haskellPackages.hoogle
      haskellPackages.fast-tags
      haskellPackages.haskell-debug-adapter
      haskellPackages.implicit-hie
    ];
  };
}
