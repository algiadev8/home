{
  config,
  pkgs,
  pkgs_unstable,
  lib,
  sops-nix,
  ...
}:
let
  direnvPackage =
    if pkgs.stdenv.isDarwin then
      pkgs.direnv.overrideAttrs (_: {
        doCheck = false;
      })
    else
      pkgs.direnv;
in
{
  imports = [
    sops-nix.homeManagerModules.sops
    ./lang/go.nix
    ./lang/haskell.nix
    ./lang/node.nix
    ./lang/latex.nix
    ./lang/terraform.nix
    ./lang/lean.nix
    ./lang/nix.nix
    ./lang/rust.nix
    ./lang/ruby.nix
    ./lang/python.nix
    ./tools/claude.nix
    ./tools/agent-skills.nix
    ./tools/codex.nix
    ./tools/gemini.nix
    ./tools/antigravity.nix
    ./tools/herdr.nix
    ./tools/neovim.nix
    ./tools/opencode.nix
    ./tools/playwright.nix
    ./tools/scrapling.nix
    ./tools/copilot-cli.nix
    ./tools/officecli.nix
  ];

  home.stateVersion = "26.05";
  programs.home-manager.enable = true;

  home.packages = with pkgs; [
    git
    ripgrep
    fd
    fzf
    jq
    bat
    eza
    zoxide
    tmux
    ghq
    zellij
    lazygit
    gh
    gh-dash
    cmake
    gcc
    gnumake
    wget
    zip
    unzip
    sops
    age
    curl
    htop
  ];

  home.sessionVariables = {
    EDITOR = "nvim";
    HISTSIZE = 1000;
    SAVEHIST = 100000;
    HISTFILE = "$HOME/.zsh_history";
  };

  home.file."powerlevel10k".source = "${pkgs.zsh-powerlevel10k}/share/zsh-powerlevel10k";
  home.file.".p10k.zsh".source = ../dotfiles/.p10k.zsh;
  home.sessionPath = [
    "$HOME/bin"
    "$HOME/.local/bin"
    "$HOME/.local/share/pnpm/bin"
  ];
  home.shell.enableZshIntegration = true;
  home.shellAliases = {
    ls = "eza --icons=always --classify=always --hyperlink";
    ghqcd = "cd $(ghq root)/$(ghq list | fzf)";
  };

  programs.git = {
    enable = true;
    settings = {
      user = {
        name = "algiadev8";
        email = "57441686+algiadev8@users.noreply.github.com";
      };
      init = {
        defaultBranch = "main";
      };
      pull = {
        ff = "only";
      };
    };
  };
  programs.zsh = {
    enable = true;
    enableCompletion = true;
    setOptions = [
      "HIST_IGNORE_DUPS"
      "EXTENDED_HISTORY"
    ];
  };
  programs.zsh.initContent = lib.mkMerge [ (lib.mkOrder 1000 (builtins.readFile ./zsh/rc.zsh)) ];
  programs.direnv = {
    enable = true;
    package = direnvPackage;
    enableZshIntegration = true;
    nix-direnv.enable = true;
  };

  programs.fzf = {
    enable = true;
    enableZshIntegration = true;
  };
  programs.zoxide = {
    enable = true;
    enableZshIntegration = true;
    options = [
      "--cmd"
      "cd"
    ];
  };
  programs.nh = {
    enable = true;
    clean = {
      enable = true;
      dates = "weekly";
      extraArgs = "--keep-since 30d --keep-one";
    };
  };

  xdg.enable = true;
  xdg.configFile."zellij/config.kdl".source = ../config/zellij/config.kdl;
  xdg.configFile."git/ignore".source = ../config/git/ignore;
}
