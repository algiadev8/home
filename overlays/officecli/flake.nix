{
  description = "OfficeCLI overlay.";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-26.05";
  };

  outputs =
    { self, nixpkgs }:
    let
      lib = nixpkgs.lib;
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = lib.genAttrs systems;
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          officecli = pkgs.callPackage ./package.nix { };
        in
        {
          inherit officecli;
          default = officecli;
        }
      );

      overlays.default = _final: prev: {
        officecli = self.packages.${prev.stdenv.hostPlatform.system}.officecli;
      };
    };
}
