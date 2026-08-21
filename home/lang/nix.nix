{
  config,
  pkgs,
  lib,
  inputs,
  ...
}:
let
  cfg = config.my.lang.nix;
in
{
  options.my.lang.nix.enable = lib.mkEnableOption "Nix language support";

  config = lib.mkIf cfg.enable {
    home.packages = with pkgs; [
      nil
      nixfmt
      inputs.statix
      deadnix
    ];
  };
}
