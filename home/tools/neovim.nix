{
  config,
  pkgs,
  pkgs_unstable,
  lib,
  nvim-config,
  ...
}:
let
  cfg = config.my.tools.neovim;
in
{
  options.my.nvim.clipboard.provider = lib.mkOption {
    type = lib.types.enum [
      "auto"
      "wayland"
      "xclip"
      "none"
    ];
    default = "auto";
    description = "Neovim clipboard provider to configure on this host.";
  };

  options.my.tools.neovim.options.socket.enable =
    lib.mkEnableOption "derive a socket path and launch nvim in listen mode";

  config = lib.mkMerge [
    {
      home.packages = [
        (nvim-config.lib.mkNixvimPackage {
          inherit pkgs pkgs_unstable;
          lang = config.my.lang;
          clipboardProvider = config.my.nvim.clipboard.provider;
          harperPackage = pkgs_unstable.harper;
          opentofuPackage = pkgs.opentofu;
          tofuLsPackage = pkgs.tofu-ls;
        })
      ];
    }
    (lib.mkIf cfg.options.socket.enable {
      home.file."bin/nvim" = {
        executable = true;
        text = ''
          #!${pkgs.runtimeShell}
          set -euo pipefail

          real_nvim="$(${pkgs.which}/bin/which -a nvim | ${pkgs.gnused}/bin/sed -n '2p')"
          if [ -z "$real_nvim" ]; then
            echo "failed to locate the real nvim binary" >&2
            exit 1
          fi

          for arg in "$@"; do
            case "$arg" in
              --listen|--listen=*)
                exec "$real_nvim" "$@"
                ;;
            esac
          done

          if [ -n "''${NVIM_LISTEN_ADDRESS:-}" ]; then
            exec "$real_nvim" "$@"
          fi

          socket_context="$PWD"
          if [ -n "''${TMUX_PANE:-}" ]; then
            socket_context="$socket_context:tmux:$TMUX_PANE"
          fi
          if [ -n "''${ZELLIJ_SESSION_NAME:-}" ]; then
            socket_context="$socket_context:zellij:$ZELLIJ_SESSION_NAME:''${ZELLIJ_PANE_ID:-}"
          fi
          if [ -z "''${TMUX_PANE:-}" ] && [ -z "''${ZELLIJ_SESSION_NAME:-}" ] && [ -t 0 ]; then
            tty_path="$(${pkgs.coreutils}/bin/tty || true)"
            socket_context="$socket_context:tty:$tty_path"
          fi
          socket_context="$socket_context:pid:$$"

          socket_hash="$(
            printf '%s' "$socket_context" \
              | ${pkgs.coreutils}/bin/cksum \
              | ${pkgs.gawk}/bin/awk '{ print $1 }'
          )"
          socket_dir="''${TMPDIR:-/tmp}/nvim"
          socket_path="$socket_dir/$socket_hash.sock"

          mkdir -p "$socket_dir"
          exec "$real_nvim" --listen "$socket_path" "$@"
        '';
      };
    })
  ];
}
