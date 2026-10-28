{
  config,
  lib,
  ...
}:

let
  cfg = config.my.tools.antigravity;
in
{
  options.my.tools.antigravity.enable = lib.mkEnableOption "Antigravity CLI toolchain";

  config = lib.mkIf cfg.enable {
    my.tools.aqua.packages = [ "google-antigravity/antigravity-cli" ];
  };
}
