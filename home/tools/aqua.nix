{
  config,
  pkgs,
  pkgs_unstable,
  lib,
  ...
}:

let
  cfg = config.my.tools.aqua;
  configFile = "${config.xdg.configHome}/aqua/aqua.yaml";
  rootDir = "${config.xdg.dataHome}/aquaproj-aqua";
  python = pkgs.python3.withPackages (ps: [ ps.ruamel-yaml ]);
  initialConfig = pkgs.writeText "aqua-initial.json" (
    builtins.toJSON {
      registries = [
        {
          type = "standard";
          ref = "v4.579.0";
        }
      ];
      checksum.enabled = true;
      packages = map (name: { inherit name; }) cfg.packages;
    }
  );
in
{
  options.my.tools.aqua.packages = lib.mkOption {
    type = lib.types.listOf lib.types.str;
    default = [ ];
    description = ''
      Nix-managed aqua package names. Aqua resolves the latest version only for
      newly added tools; activation preserves existing versions and registry
      settings selected with aqua update.
    '';
    example = [ "openai/codex" ];
  };

  config = lib.mkMerge [
    {
      # Run even for an empty package set so disabling the last tool removes it
      # from the existing config. A fresh host with no tools creates no file.
      # linkGeneration removes the former Nix-managed config symlink first.
      home.activation.aquaSync = lib.hm.dag.entryAfter [ "linkGeneration" ] ''
        run ${python}/bin/python ${./aqua/sync.py} \
          --config ${lib.escapeShellArg configFile} --initial ${initialConfig} \
          --aqua ${pkgs_unstable.aqua}/bin/aqua
      '';
    }
    (lib.mkIf (cfg.packages != [ ]) {
      home.packages = [ pkgs_unstable.aqua ];
      home.sessionVariables = {
        AQUA_GLOBAL_CONFIG = configFile;
        AQUA_ROOT_DIR = rootDir;
      };
      home.sessionPath = [ "${rootDir}/bin" ];

      # The config is a writable regular file, never a Home Manager symlink.
      # Install from the synchronized file, not from the initial Nix template.
      home.activation.aquaInstall = lib.hm.dag.entryAfter [ "aquaSync" ] ''
        run env AQUA_ROOT_DIR=${lib.escapeShellArg rootDir} \
          AQUA_GLOBAL_CONFIG=${lib.escapeShellArg configFile} \
          ${pkgs_unstable.aqua}/bin/aqua --config ${lib.escapeShellArg configFile} install
      '';
    })
  ];
}
