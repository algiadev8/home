"""Synchronize the Nix-owned package set without resetting aqua-owned versions."""

import argparse
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq
from ruamel.yaml.error import YAMLError


def package_key(package):
    if not isinstance(package, dict) or not isinstance(package.get("name"), str):
        raise ValueError("Each package must have a name; package imports are not supported")
    name = package["name"].split("@", 1)[0]
    if not name:
        raise ValueError("Package names must not be empty")
    registry = package.get("registry", "standard")
    if not isinstance(registry, str):
        raise ValueError("Package registry must be a string")
    return (registry, name)


def unique_packages(packages):
    if not isinstance(packages, list):
        raise ValueError("packages must be a list")
    result = {}
    for package in packages:
        key = package_key(package)
        if key in result:
            raise ValueError(f"Duplicate aqua package: {key[1]}")
        result[key] = package
    return result


def has_version(package):
    return bool(package["name"].partition("@")[2] or package.get("version") or package.get("version_expr"))


def resolve_versions(packages, current, aqua):
    """Ask aqua for latest versions using the retained registry configuration."""
    with tempfile.TemporaryDirectory(prefix="aqua-resolve-") as directory:
        config = Path(directory) / "aqua.yaml"
        with config.open("w", encoding="utf-8") as stream:
            YAML().dump({"registries": current["registries"], "packages": []}, stream)
        arguments = [
            name if registry == "standard" else f"{registry},{name}"
            for registry, name in map(package_key, packages)
        ]
        result = subprocess.run(
            [aqua, "--config", str(config), "generate", *arguments],
            check=True, capture_output=True, text=True,
        )
        resolved = unique_packages(YAML().load(result.stdout))
        if set(resolved) != {package_key(entry) for entry in packages}:
            raise ValueError("aqua generated a different package set than requested")
        if not all(has_version(entry) for entry in resolved.values()):
            raise ValueError("aqua did not resolve a version for every new package")
        return resolved


def synchronize(current, initial, aqua):
    """Keep existing entries verbatim, remove disabled ones, seed new ones."""
    if not isinstance(current, dict):
        raise ValueError("The aqua configuration must be a mapping")
    if "registries" in current:
        registries = current["registries"]
        if not isinstance(registries, list) or not all(isinstance(entry, dict) for entry in registries):
            raise ValueError("registries must be a list of mappings")
    if "checksum" in current and not isinstance(current["checksum"], dict):
        raise ValueError("checksum must be a mapping")
    desired = unique_packages(initial["packages"])
    existing = unique_packages(current.get("packages", []))
    packages = [entry for key, entry in existing.items() if key in desired]
    packages.extend(entry for key, entry in desired.items() if key not in existing)
    changed = False
    # Registry refs, checksum preferences, and other settings belong to aqua.
    # Only fill missing defaults, never reset them to the Nix template.
    for key in ("registries", "checksum"):
        if key not in current:
            current[key] = initial[key]
            changed = True
    unresolved = [entry for entry in packages if not has_version(entry)]
    if unresolved:
        resolved = resolve_versions(unresolved, current, aqua)
        packages = [
            dict(entry, **resolved[package_key(entry)]) if not has_version(entry) else entry
            for entry in packages
        ]
    if current.get("packages") != packages:
        current["packages"] = CommentedSeq(packages)
        changed = True
    return changed


def sync_file(config_path, initial, aqua="aqua"):
    # Resolve the parent, not the file: an existing symlink must never be followed.
    requested = Path(config_path).expanduser().absolute()
    path = requested.parent.resolve() / requested.name
    if path.is_symlink():
        raise ValueError(f"Refusing to overwrite a symlink: {path}")
    if path.exists() and not path.is_file():
        raise ValueError(f"Not a regular configuration file: {path}")
    exists = path.exists()
    if not exists and not initial["packages"]:
        return False

    yaml = YAML()
    yaml.preserve_quotes = True
    original = path.read_bytes() if exists else None
    if exists:
        current = yaml.load(original.decode("utf-8"))
    else:
        current = dict(initial, packages=[])
    changed = synchronize(current, initial, aqua)
    if exists and not changed:
        return False

    content = io.StringIO()
    yaml.dump(current, content)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = (stat.S_IMODE(path.stat().st_mode) | stat.S_IWUSR) if exists else 0o600
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content.getvalue())
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        # Verify both absolute paths before atomically replacing the intended file.
        if path.is_symlink() or path.parent.resolve() / path.name != path:
            raise ValueError(f"Configuration path changed during synchronization: {path}")
        if temporary.resolve().parent != path.parent or not temporary.name.startswith(f".{path.name}."):
            raise ValueError("Unexpected temporary configuration path")
        # Do not commit a stale snapshot over an aqua update made while syncing.
        if path.exists() != exists or (exists and path.read_bytes() != original):
            raise ValueError("Configuration changed during synchronization; retry activation")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            if temporary.resolve().parent != path.parent or not temporary.name.startswith(f".{path.name}."):
                raise ValueError("Refusing to remove an unexpected temporary path")
            temporary.unlink()
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--initial", required=True)
    parser.add_argument("--aqua", default="aqua")
    args = parser.parse_args()
    initial = json.loads(Path(args.initial).read_text(encoding="utf-8"))
    try:
        sync_file(args.config, initial, args.aqua)
    except subprocess.CalledProcessError as error:
        parser.exit(1, f"aqua version resolution failed: {error.stderr}\n")
    except (ValueError, OSError, YAMLError) as error:
        parser.exit(1, f"aqua configuration sync failed: {error}\n")


if __name__ == "__main__":
    main()
