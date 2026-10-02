{ pkgs, pkgs_unstable }:
let
  dockerSource = builtins.path {
    path = ./.;
    name = "virtual-browser";
    filter =
      path: type:
      type == "directory"
      || builtins.elem (baseNameOf path) [
        "Dockerfile"
        "supervisord.conf"
        "start-browser.sh"
        ".dockerignore"
      ];
  };
  imageVersion = builtins.substring 0 16 (
    builtins.hashString "sha256" (
      builtins.readFile ./Dockerfile
      + builtins.readFile ./supervisord.conf
      + builtins.readFile ./start-browser.sh
    )
  );
in
pkgs.writeShellApplication {
  name = "browser";
  runtimeInputs = [
    pkgs_unstable.docker-client
  ]
  ++ pkgs.lib.optionals pkgs.stdenv.hostPlatform.isDarwin [ pkgs_unstable.colima ]
  ++ pkgs.lib.optionals pkgs.stdenv.hostPlatform.isLinux [ pkgs.xdg-utils ];
  text = ''
    export BROWSER_HARNESS_BIN="${pkgs.browser-harness}/bin/browser-harness"
    export BROWSER_DOCKER_SOURCE="${dockerSource}"
    export BROWSER_DOCKER_IMAGE="agent-browser:${imageVersion}"
    export BROWSER_SKILL_PATH="${../../../skills/browser/SKILL.md}"
    exec ${pkgs.python312}/bin/python ${./cli.py} "$@"
  '';
}
