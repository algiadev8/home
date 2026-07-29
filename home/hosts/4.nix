{
  hmCommonModules,
  username,
  pkgs,
  pkgs_unstable,
  ...
}:
{
  homebrew = {
    enable = true;
    onActivation = {
      autoUpdate = true;
      upgrade = true;
    };
    brews = [
      "gmp"
    ];
    casks = [
      "brave-browser"
      "slack"
      "skim"
      "tailscale-app"
      "zoom"
      "microsoft-teams"
      "bitwarden"
      {
        name = "obsidian";
        greedy = true;
      }
      "zotero"
      "lm-studio"
      "microsoft-office"
      "ghostty"
      "docker-desktop"
    ];
  };

  home-manager.users.${username} = { config, ... }: {
    imports = hmCommonModules;
    my.lang.node.enable = true;
    my.lang.rust.enable = true;
    my.lang.nix.enable = true;
    my.lang.latex.enable = true;
    my.lang.haskell.enable = true;
    my.tools.claude.enable = true;
    my.tools.codex.enable = true;
    my.tools.antigravity.enable = true;
    my.tools.herdr.enable = true;
    my.lang.lean.enable = true;
    my.tools.neovim.options.socket.enable = true;
    my.tools.scrapling.enable = true;
    my.tools.playwright.enable = true;
    home.packages = with pkgs; [
      git-crypt
      poppler-utils
      wrangler
    ];
    programs.gpg.enable = true;
    services.gpg-agent = {
      enable = true;
      enableZshIntegration = true;
      pinentry.package = pkgs.pinentry-curses;
    };

    launchd.agents.tei-embeddings = {
      enable = true;
      config = {
        ProgramArguments = [
          "${pkgs.text-embeddings-router}/bin/text-embeddings-router"
          "--model-id"
          "intfloat/multilingual-e5-small"
          "--port"
          "8787"
        ];
        RunAtLoad = true;
        KeepAlive = true;
        StandardOutPath = "${config.home.homeDirectory}/Library/Logs/tei-embeddings.log";
        StandardErrorPath = "${config.home.homeDirectory}/Library/Logs/tei-embeddings.error.log";
      };
    };

    programs.ghostty = {
      enable = false;

      package = pkgs.brewCasks.ghostty;

      enableZshIntegration = true;

      settings = {
        shell-integration-features = "ssh-env,ssh-terminfo";
      };
    };
  };
}
