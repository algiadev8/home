{
  config,
  pkgs,
  pkgs_unstable,
  lib,
  ...
}:

let
  cfg = config.my.tools.claude;
in
{
  options.my.tools.claude = {
    enable = lib.mkEnableOption "claude code toolchain";

    useNativeInstall = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Use native installation script instead of nixpkgs (always gets latest version)";
    };
  };

  config =
    lib.mkIf cfg.enable
      # Common configuration
      {
        home.activation = {
          claudeSettings = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
            mkdir -p "$HOME/.claude"

            # Seed the file once, then let Claude manage future edits.
            if [ ! -e "$HOME/.claude/settings.json" ]; then
              cp "${../../dotfiles/.claude/settings.json}" "$HOME/.claude/settings.json"
            fi
          '';
        };

        home.file.".claude/hooks/format.sh".source = ../../dotfiles/.claude/hooks/format.sh;

        # Needed by notify-osc.sh timeout fallback.
        home.packages = [
          pkgs.perl
          pkgs_unstable.claude-code
        ];

      };
}
