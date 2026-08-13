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

      overlays.default = final: _prev: {
        browser-use = self.packages.${final.stdenv.hostPlatform.system}.browser-use;
      };
    };
}
