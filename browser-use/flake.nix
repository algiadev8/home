{
  description = "browser-use Python application overlay.";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      pyproject-nix,
      pyproject-build-systems,
      uv2nix,
    }:
    let
      lib = nixpkgs.lib;
      systems = [
        "x86_64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = lib.genAttrs systems;

      mkBrowserUse = system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };
          workspace = uv2nix.lib.workspace.loadWorkspace {
            workspaceRoot = ./.;
          };
          uvOverlay = workspace.mkPyprojectOverlay {
            sourcePreference = "wheel";
          };
          python = pkgs.python312;
          pythonSet =
            (pkgs.callPackage pyproject-nix.build.packages {
              inherit python;
            }).overrideScope
              (lib.composeManyExtensions [
                pyproject-build-systems.overlays.default
                uvOverlay
              ]);
        in
        pythonSet.mkVirtualEnv "browser-use-env" workspace.deps.default;
    in
    {
      packages = forAllSystems (
        system:
        let
          browserUse = mkBrowserUse system;
        in
        {
          browser-use = browserUse;
          default = browserUse;
        }
      );

      apps = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          update = pkgs.writeShellApplication {
            name = "update-browser-use";
            runtimeInputs = [ pkgs.uv ];
            text = ''
              set -euo pipefail

              workspace_root="''${BROWSER_USE_ROOT:-$PWD}"
              if [ ! -f "$workspace_root/pyproject.toml" ] && [ -f "$workspace_root/browser-use/pyproject.toml" ]; then
                workspace_root="$workspace_root/browser-use"
              fi

              if [ ! -f "$workspace_root/pyproject.toml" ]; then
                echo "Could not find browser-use/pyproject.toml." >&2
                echo "Run this command from the repository root or browser-use/." >&2
                exit 1
              fi

              cd "$workspace_root"
              uv lock --upgrade-package browser-use
            '';
          };
        in
        {
          update = {
            type = "app";
            program = "${update}/bin/update-browser-use";
          };
        }
      );

      overlays.default = final: _prev: {
        browser-use = self.packages.${final.stdenv.hostPlatform.system}.browser-use;
      };
    };
}
