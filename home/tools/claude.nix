{
  config,
  pkgs,
  lib,
  ...
}:

let
  cfg = config.my.tools.claude;
in
{
  options.my.tools.claude.enable = lib.mkEnableOption "claude code toolchain";

  config = lib.mkIf cfg.enable {
    home.activation.claudeSettings = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      mkdir -p "$HOME/.claude"

      # Seed the file once, then let Claude manage future edits.
      if [ ! -e "$HOME/.claude/settings.json" ]; then
        cp "${../../dotfiles/.claude/settings.json}" "$HOME/.claude/settings.json"
      fi
    '';

    home.file.".claude/hooks/format.sh".source = ../../dotfiles/.claude/hooks/format.sh;

    # Needed by notify-osc.sh timeout fallback.
    home.packages = [ pkgs.perl ];
    my.tools.aqua.packages = [ "anthropics/claude-code" ];
    # Keep the aqua pin authoritative, as the former Nix wrapper did.
    home.sessionVariables = {
      DISABLE_AUTOUPDATER = "1";
      DISABLE_INSTALLATION_CHECKS = "1";
    };
  };
}
