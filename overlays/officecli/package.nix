{
  lib,
  fetchurl,
  makeWrapper,
  stdenvNoCC,
}:

let
  sources = lib.importJSON ./sources.json;
  source =
    sources.${stdenvNoCC.hostPlatform.system}
      or (throw "Unsupported OfficeCLI platform: ${stdenvNoCC.hostPlatform.system}");
in
stdenvNoCC.mkDerivation {
  pname = "officecli";
  inherit (source) version;

  src = fetchurl {
    inherit (source) url hash;
  };

  dontUnpack = true;
  nativeBuildInputs = [ makeWrapper ];

  installPhase = ''
    runHook preInstall

    install -Dm755 "$src" "$out/libexec/officecli"
    makeWrapper "$out/libexec/officecli" "$out/bin/officecli" \
      --set OFFICECLI_SKIP_UPDATE 1

    runHook postInstall
  '';

  meta = {
    description = "Office suite CLI for AI-agent-friendly Office document automation";
    homepage = "https://github.com/iOfficeAI/OfficeCLI";
    license = lib.licenses.asl20;
    mainProgram = "officecli";
    platforms = builtins.attrNames sources;
    sourceProvenance = with lib.sourceTypes; [ binaryNativeCode ];
  };
}
