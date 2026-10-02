{
  description = "Standalone nixvim configuration";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-unstable";
    nixvim = {
      url = "github:nix-community/nixvim";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      nixvim,
      ...
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      lib.mkNixvimPackage =
        {
          pkgs,
          pkgs_unstable ? pkgs,
          lang ? { },
          clipboardProvider ? "auto",
          harperPackage ? pkgs_unstable.harper,
          opentofuPackage ? pkgs.opentofu,
          tofuLsPackage ? pkgs.tofu-ls,
        }:
        nixvim.legacyPackages.${pkgs.stdenv.hostPlatform.system}.makeNixvimWithModule {
          pkgs = pkgs_unstable;
          module = import ./module.nix;
          extraSpecialArgs = {
            inherit
              clipboardProvider
              harperPackage
              lang
              opentofuPackage
              tofuLsPackage
              ;
          };
        };

      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };
        in
        {
          default = self.lib.mkNixvimPackage { inherit pkgs; };
          nvim = self.packages.${system}.default;
        }
      );

      checks = forAllSystems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };
          nixvimModule = {
            inherit pkgs;
            module = import ./module.nix;
            extraSpecialArgs = {
              clipboardProvider = "auto";
              lang = { };
            };
          };
        in
        {
          default = nixvim.lib.${system}.check.mkTestDerivationFromNixvimModule nixvimModule;
        }
      );
    };
}
