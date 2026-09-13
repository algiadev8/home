{
  config,
  lib,
  pkgs,
  inputs,
  ...
}:
let
  cfg = config.my.tools.opentelemetry;
  settingsFormat = pkgs.formats.yaml { };
  configFile = settingsFormat.generate "opentelemetry-collector.yaml" {
    extensions.file_storage = {
      directory = "${config.xdg.stateHome}/opentelemetry-collector";
      create_directory = true;
    };

    receivers.otlp.protocols = {
      grpc.endpoint = "127.0.0.1:4317";
      http.endpoint = "127.0.0.1:4318";
    };

    processors = {
      memory_limiter = {
        check_interval = "5s";
        limit_mib = 256;
      };
      batch.timeout = "5s";
    };

    exporters."otlp_http/openobserve" = {
      endpoint = "https://openobserve.xn--n9jo7871c64k.jp/api/default";
      headers = {
        Authorization = "Basic \${env:OPENOBSERVE_TOKEN}";
        organization = "default";
        stream-name = "default";
      };
      sending_queue = {
        enabled = true;
        storage = "file_storage";
        queue_size = 10000;
      };
      retry_on_failure = {
        enabled = true;
        initial_interval = "5s";
        max_interval = "60s";
        max_elapsed_time = "0s";
      };
    };

    service = {
      extensions = [ "file_storage" ];
      telemetry.logs.level = "warn";
      pipelines = lib.genAttrs [ "traces" "metrics" "logs" ] (_: {
        receivers = [ "otlp" ];
        processors = [
          "memory_limiter"
          "batch"
        ];
        exporters = [ "otlp_http/openobserve" ];
      });
    };
  };
  tokenSecret = "observability/openobserve-token";
  collectorLauncher = pkgs.writeShellApplication {
    name = "opentelemetry-collector-launcher";
    runtimeInputs = [ pkgs.coreutils ];
    text = ''
      OPENOBSERVE_TOKEN="$(${pkgs.coreutils}/bin/cat ${config.sops.secrets.${tokenSecret}.path})"
      export OPENOBSERVE_TOKEN
      exec ${lib.getExe pkgs.opentelemetry-collector-contrib} --config=file:${configFile}
    '';
  };
in
{
  options.my.tools.opentelemetry.enable = lib.mkEnableOption "OpenTelemetry Collector";

  config = lib.mkIf cfg.enable {
    sops.secrets.${tokenSecret} = {
      sopsFile = "${inputs.my_secrets}/secrets.yaml";
      mode = "0400";
    };

    systemd.user.services.opentelemetry-collector = lib.mkIf pkgs.stdenv.hostPlatform.isLinux {
      Unit = {
        Description = "OpenTelemetry Collector";
        After = [ "sops-nix.service" ];
      };
      Service = {
        ExecStart = "${collectorLauncher}/bin/opentelemetry-collector-launcher";
        Restart = "always";
        RestartSec = "5s";
      };
      Install.WantedBy = [ "default.target" ];
    };

    launchd.agents.opentelemetry-collector = lib.mkIf pkgs.stdenv.hostPlatform.isDarwin {
      enable = true;
      config = {
        ProgramArguments = [ "${collectorLauncher}/bin/opentelemetry-collector-launcher" ];
        RunAtLoad = true;
        KeepAlive = true;
        ThrottleInterval = 5;
        StandardOutPath = "${config.home.homeDirectory}/Library/Logs/opentelemetry-collector.log";
        StandardErrorPath = "${config.home.homeDirectory}/Library/Logs/opentelemetry-collector.error.log";
      };
    };
  };
}
