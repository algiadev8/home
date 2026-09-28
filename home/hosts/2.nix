{
  pkgs,
  pkgs_unstable,
  config,
  lib,
  ...
}:
{
  my.nvim.clipboard.provider = "wayland";
  my.lang.go.enable = true;
  my.lang.node.enable = true;
  my.lang.python.enable = true;
  my.lang.rust.enable = true;
  my.lang.nix.enable = true;
  my.tools.claude.enable = true;
  my.lang.latex.enable = true;
  my.lang.ruby.enable = true;
  my.tools.codex.enable = true;
  my.tools.opencode.enable = true;
  my.tools.playwright.enable = true;
  my.tools.scrapling.enable = true;
  my.tools.copilot.enable = true;
  my.tools.herdr.enable = true;
  my.tools.antigravity.enable = true;

  home.packages = with pkgs; [
    wl-clipboard
    poppler-utils
    ni
    graphviz-nox
    flatpak
    hledger
    hledger-ui
    hledger-web
    bitwarden-cli
    imagemagick
    git-crypt
  ];
  programs.sioyek = {
    enable = true;
    bindings.synctex_under_cursor = "x";
  };
  targets.genericLinux.gpu.enable = true;
  programs.gpg.enable = true;
  services.gpg-agent = {
    enable = true;
    enableZshIntegration = true;
    pinentry.package = pkgs.pinentry-curses;
  };

  my.emails.enableAccounts = [
    "gmail1"
    "campus_mail"
  ];
  programs.himalaya.package = lib.mkForce pkgs.himalaya;
  sops.age.keyFile = "${config.xdg.configHome}/sops/age/keys.txt";

  home.sessionVariables = {
    DISPLAY = ":0";
    XDG_DATA_DIRS = "${config.home.homeDirectory}/.local/share/flatpak/exports/share:/var/lib/flatpak/exports/share";
  };
}
