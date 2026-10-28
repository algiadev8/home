{
  config,
  lib,
  ...
}:

let
  cfg = config.my.tools.codex;
in
{
  options.my.tools.codex.enable = lib.mkEnableOption "Codex toolchain";

  config = lib.mkIf cfg.enable {
    my.tools.aqua.packages = [ "openai/codex" ];
    programs.zsh.initContent = ''
      eval "$(codex completion zsh)"
    '';

    # ~/.codex/config.toml is intentionally NOT managed here (no symlink, no
    # seed-once copy). Codex rewrites it at runtime (trust_level, notices,
    # hooks state, etc.), so a Nix-managed file would either be clobbered on
    # every codex invocation or would need to be read-only and fight the
    # tool. dotfiles/.codex/config.toml exists only as a reference template
    # for manual/first-time setup, not as something home-manager applies.
  };
}
