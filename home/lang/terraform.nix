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
  options.my.lang.terraform.enable = lib.mkEnableOption "Terraform language support";

  config = lib.mkIf cfg.enable {
    home.packages = with pkgs; [
      terraform
      terraform-ls
    ];
  };
}
