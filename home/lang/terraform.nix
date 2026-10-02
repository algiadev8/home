{
  config,
  pkgs,
  lib,
  ...
}:
let
  cfg = config.my.lang.terraform;
in
{
  options.my.lang.terraform.enable = lib.mkEnableOption "OpenTofu language support";

  config = lib.mkIf cfg.enable {
    home.packages = with pkgs; [
      opentofu
      tofu-ls
    ];
  };
}
