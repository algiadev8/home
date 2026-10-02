{
  config,
  pkgs,
  pkgs_unstable,
  lib,
  ...
}:
let
  cfg = config.my.tools.browser;
in
{
  options.my.tools.browser.enable = lib.mkEnableOption "Shared Docker browser with CDP and noVNC";
  config = lib.mkIf cfg.enable {
    home.packages = [ (import ./browser/package.nix { inherit pkgs pkgs_unstable; }) ];
    home.file.".agents/skills/browser" = {
      source = ../../skills/browser;
      recursive = true;
    };
  };
}
