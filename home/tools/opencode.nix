{ config, lib, ... }:

let
  cfg = config.my.tools.opencode;
in
{
  options.my.tools.opencode.enable = lib.mkEnableOption "Opencode toolchain";

  config = lib.mkIf cfg.enable {
    my.tools.aqua.packages = [ "anomalyco/opencode" ];
  };
}
