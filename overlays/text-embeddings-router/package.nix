{
  lib,
  rustPlatform,
  fetchFromGitHub,
  protobuf,
  pkg-config,
  stdenv,
  apple-sdk_15,
}:

let
  src = fetchFromGitHub {
    owner = "huggingface";
    repo = "text-embeddings-inference";
    rev = "fc071b1cb6e1b091b67f20868de7c5982aa7d4d0";
    hash = "sha256-ahX3jsNs/mvK0fnGLW3+ZDsW0VSE1Ykc4FfA+6VqQE4=";
  };
in
rustPlatform.buildRustPackage {
  pname = "text-embeddings-router";
  version = "1.9.3-fc071b1";

  inherit src;

  cargoLock = {
    lockFile = "${src}/Cargo.lock";
    outputHashes = {
      "candle-core-0.8.4" = "sha256-kl3orr5Q6NbgXvWzKVYyB4wG0aYPYPXQwMRrQf7wFkE=";
      "cudarc-0.13.5" = "sha256-XA3f4L46RSU0lagsF6bEnDCkECVH9IGN4u2AbNouSuw=";
      "insta-1.34.0" = "sha256-fA/GyKbV8CYKf1o8cQZ3qxYlX65+/uynrKMROJuDyo4=";
    };
  };

  buildAndTestSubdir = "router";
  buildFeatures = lib.optionals stdenv.hostPlatform.isDarwin [ "metal" ];
  doCheck = false;

  nativeBuildInputs = [
    protobuf
    pkg-config
  ];

  buildInputs = lib.optionals stdenv.hostPlatform.isDarwin [ apple-sdk_15 ];

  env.PROTOC = "${protobuf}/bin/protoc";

  meta = {
    description = "Hugging Face Text Embeddings Inference router, built locally (Metal on Apple Silicon)";
    homepage = "https://github.com/huggingface/text-embeddings-inference";
    mainProgram = "text-embeddings-router";
    platforms = [ "aarch64-darwin" ];
  };
}
