{
  config,
  pkgs,
  lib,
  ...
}:

let
  cfg = config.my.tools.officecli;
in
{
  options.my.tools.officecli.enable = lib.mkEnableOption "OfficeCLI toolchain";

  config = lib.mkIf cfg.enable {
    home.packages = [ pkgs.officecli ];
  };
}
