{
  config,
  lib,
  ...
}:

let
  cfg = config.my.tools.copilot;
in
{
  options.my.tools.copilot.enable = lib.mkEnableOption "copilot toolchain";

  config = lib.mkIf cfg.enable {
    my.tools.aqua.packages = [ "github/copilot-cli" ];
  };
}
