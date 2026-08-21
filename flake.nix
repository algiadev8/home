{
  description = "Home Manager configuration of dmtst";

  nixConfig = {
    extra-substituters = [
      "https://herdr.cachix.org"
      "https://statix.cachix.org"
    ];
    extra-trusted-public-keys = [
      "herdr.cachix.org-1:3nH7IStRsS0ASfdonA0DCRR2ZrSCeWitZ7Kwew0cR4I="
      "statix.cachix.org-1:Z9E/g1YjCjU117QOOt07OjhljCoRZddiAm4VVESvais="
    ];
  };

  inputs = {
    # Specify the source of Home Manager and Nixpkgs.
    nixpkgs.url = "github:nixos/nixpkgs/nixos-26.05";
    nixpkgs_unstable.url = "github:nixos/nixpkgs/nixpkgs-unstable";
    sops-nix = {
      url = "github:Mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    agent-skills = {
      url = "github:Kyure-A/agent-skills-nix";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.home-manager.follows = "home-manager";
    };
    claude-my-skills = {
      url = "git+ssh://git@github.com/daichi-629/claude-my-skills";
      flake = false;
    };
    ppt-master = {
      url = "github:hugohe3/ppt-master";
      flake = false;
    };
    nix-darwin = {
      url = "github:lnl7/nix-darwin/nix-darwin-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    rust-overlay = {
      url = "github:oxalica/rust-overlay";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nvim-config = {
      url = "path:./nixvim";
      inputs.nixpkgs.follows = "nixpkgs_unstable";
    };
    claude-overlay = {
      url = "github:ryoppippi/nix-claude-code";
    };
    codex-overlay = {
      url = "path:./overlays/codex";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    gemini-overlay = {
      url = "path:./overlays/gemini";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    antigravity-overlay = {
      url = "path:./overlays/antigravity";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    playwright-overlay = {
      url = "path:./overlays/playwright";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    wrangler-overlay = {
      url = "path:./overlays/wrangler";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    browser-use-overlay = {
      url = "path:./browser-use";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    officecli-overlay = {
      url = "path:./overlays/officecli";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    herdr-nix = {
      url = "github:herdrdev/herdr-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    statix = {
      url = "github:molybdenumsoftware/statix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    my_secrets = {
      url = "git+ssh://git@github.com/daichi-629/home-secrets";
    };
    brew-nix = {
      url = "github:BatteredBunny/brew-nix";
      inputs.brew-api.follows = "brew-api";
    };
    brew-api = {
      url = "github:BatteredBunny/brew-api";
      flake = false;
    };
  };

  outputs =
    inputs@{
      self,
      nixpkgs,
      rust-overlay,
      claude-overlay,
      codex-overlay,
      gemini-overlay,
      antigravity-overlay,
      playwright-overlay,
      wrangler-overlay,
      browser-use-overlay,
      officecli-overlay,
      brew-nix,
      home-manager,
      nix-darwin,
      nvim-config,
      nixpkgs_unstable,
      my_secrets,
      sops-nix,
      ...
    }:
    let
      lib = nixpkgs.lib;
      overlays = [
        rust-overlay.overlays.default
        (_final: prev: {
          # Remove after home-secrets stops passing the removed withFeatures argument.
          himalaya = prev.himalaya // {
            override = args: prev.himalaya.override (builtins.removeAttrs args [ "withFeatures" ]);
          };
        })
        codex-overlay.overlays.default
        gemini-overlay.overlays.default
        antigravity-overlay.overlays.default
        playwright-overlay.overlays.default
        wrangler-overlay.overlays.default
        browser-use-overlay.overlays.default
        officecli-overlay.overlays.default
        claude-overlay.overlays.default
        brew-nix.overlays.default
      ];
      hostIdentities = my_secrets.lib.my.hosts;
      hostSettings = {
        "1" = {
          system = "x86_64-linux";
        };
        "2" = {
          system = "x86_64-linux";
        };
        "3" = {
          system = "x86_64-linux";
        };
        "4" = {
          system = "aarch64-darwin";
        };
      };
      mkCommonHomeModules =
        {
          hostId,
          username,
          homeDirectory,
          system,
        }:
        [
          inputs.agent-skills.homeManagerModules.default
          sops-nix.homeManagerModules.sops
          my_secrets.homeManagerModules.my.emails
          ./home/common.nix
          {
            home.username = username;
            home.homeDirectory = homeDirectory;
            home.packages = [
              self.packages.${system}.update-all
              self.packages.${system}.update-pins
            ];
          }
        ];
      mkHomeModules =
        {
          hostId,
          username,
          homeDirectory,
          system,
        }:
        (mkCommonHomeModules {
          inherit
            hostId
            username
            homeDirectory
            system
            ;
        })
        ++ [ (./home/hosts + "/${hostId}.nix") ];
      mkHome =
        {
          hostId,
          hostName,
          system,
          username,
        }:
        let
          homeDirectory = if lib.hasSuffix "darwin" system then "/Users/${username}" else "/home/${username}";
        in
        home-manager.lib.homeManagerConfiguration {
          pkgs = import nixpkgs {
            inherit system overlays;
            config = {
              allowUnfree = true;
              permittedInsecurePackages = lib.optionals (hostId == "3") [
                "electron-39.8.10"
              ];
            };
          };

          modules = mkHomeModules {
            inherit
              hostId
              username
              homeDirectory
              system
              ;
          };
          extraSpecialArgs = {
            pkgs_unstable = import nixpkgs_unstable {
              inherit system overlays;
              config = {
                allowUnfree = true;
              };
            };
            inherit
              inputs
              nvim-config
              sops-nix
              self
              hostId
              ;
          };
        };
      mkDarwin =
        {
          hostId,
          hostName,
          system,
          username,
        }:
        let
          homeDirectory = "/Users/${username}";
        in
        nix-darwin.lib.darwinSystem {
          inherit system;
          specialArgs = {
            inherit hostId username;
            hmCommonModules = mkCommonHomeModules {
              inherit
                hostId
                username
                homeDirectory
                system
                ;
            };
            pkgs_unstable = import nixpkgs_unstable {
              inherit system overlays;
              config = {
                allowUnfree = true;
              };
            };
          };
          modules = [
            home-manager.darwinModules.home-manager
            (./home/hosts + "/${hostId}.nix")
            {
              nixpkgs = {
                inherit overlays;
                config.allowUnfree = true;
                hostPlatform = system;
              };

              nix.settings.experimental-features = [
                "nix-command"
                "flakes"
              ];

              system.stateVersion = 6;
              system.primaryUser = username;
              users.users.${username}.home = homeDirectory;

              home-manager.useGlobalPkgs = true;
              home-manager.useUserPackages = true;
              home-manager.extraSpecialArgs = {
                pkgs_unstable = import nixpkgs_unstable {
                  inherit system overlays;
                  config = {
                    allowUnfree = true;
                  };
                };
                inherit
                  inputs
                  nvim-config
                  sops-nix
                  self
                  hostId
                  ;
              };
            }
          ];
        };
      systems = [
        "x86_64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system);
    in
    {
      homeConfigurations =
        lib.mapAttrs'
          (
            hostId: hostSettingsForId:
            let
              identity =
                hostIdentities.${hostId}
                  or (throw "Missing host identity for host id ${hostId} in secrets-home-manager");
            in
            lib.nameValuePair "${identity.username}@${identity.hostName}" (mkHome {
              inherit hostId;
              inherit (hostSettingsForId) system;
              inherit (identity) hostName username;
            })
          )
          (
            lib.filterAttrs (
              _: hostSettingsForId: !(lib.hasSuffix "darwin" hostSettingsForId.system)
            ) hostSettings
          );
      darwinConfigurations =
        lib.mapAttrs'
          (
            hostId: hostSettingsForId:
            let
              identity =
                hostIdentities.${hostId}
                  or (throw "Missing host identity for host id ${hostId} in secrets-home-manager");
              darwinName = identity.darwinName or identity.hostName;
            in
            lib.nameValuePair darwinName (mkDarwin {
              inherit hostId;
              inherit (hostSettingsForId) system;
              inherit (identity) hostName username;
            })
          )
          (
            lib.filterAttrs (_: hostSettingsForId: lib.hasSuffix "darwin" hostSettingsForId.system) hostSettings
          );
      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          updatePins = (import ./scripts/update-pin.nix { inherit pkgs self; }).updatePins;
          updateNpmOverlays =
            (import ./scripts/update-npm-overlays.nix {
              inherit pkgs;
            }).updateNpmOverlays;
          bootstrapNewDevice =
            (import ./scripts/bootstrap-new-device.nix {
              inherit pkgs self;
            }).bootstrapNewDevice;
          updateAll =
            (import ./scripts/update-all.nix {
              inherit hostIdentities pkgs updatePins;
            }).updateAll;
        in
        {
          bootstrap-new-device = bootstrapNewDevice;
          update-all = updateAll;
          update-npm-overlays = updateNpmOverlays;
          update-pins = updatePins;
        }
      );
      apps = forAllSystems (system: {
        bootstrap-new-device = {
          type = "app";
          program = "${self.packages.${system}.bootstrap-new-device}/bin/bootstrap-new-device";
        };
        update-all = {
          type = "app";
          program = "${self.packages.${system}.update-all}/bin/update-all";
        };
        update-npm-overlays = {
          type = "app";
          program = "${self.packages.${system}.update-npm-overlays}/bin/update-npm-overlays";
        };
        update-pins = {
          type = "app";
          program = "${self.packages.${system}.update-pins}/bin/update-pins";
        };
      });
    };
}
