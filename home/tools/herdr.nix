{
  pkgs,
  inputs,
  config,
  lib,
  ...
}:

let
  cfg = config.my.tools.herdr;
in
{
  options.my.tools.herdr.enable = lib.mkEnableOption "Herdr terminal workspace manager";

  config = lib.mkIf cfg.enable {
    home.packages = [ inputs.herdr-nix.packages.${pkgs.stdenv.hostPlatform.system}.herdr ];
  };
}
