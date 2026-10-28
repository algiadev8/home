import copy
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ruamel.yaml import YAML

from sync import sync_file


def template(*names):
    return {
        "registries": [{"type": "standard", "ref": "v4.579.0"}],
        "checksum": {"enabled": True},
        "packages": [{"name": name} for name in names],
    }


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="aqua-sync-test-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "config" / "aqua.yaml"
        self.yaml = YAML()

    def load(self):
        return self.yaml.load(self.path.read_text())

    def save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w") as stream:
            self.yaml.dump(data, stream)

    def test_names_only_resolve_latest_on_first_activation(self):
        result = subprocess.CompletedProcess([], 0, stdout='- name: cli/cli@v2.102.0\n', stderr='')
        with patch("sync.subprocess.run", return_value=result) as generate:
            sync_file(self.path, template("cli/cli"), aqua="/aqua")
        self.assertEqual(self.load()["packages"], [{"name": "cli/cli@v2.102.0"}])
        command = generate.call_args.args[0]
        self.assertEqual(command[0], "/aqua")
        self.assertEqual(command[-2:], ["generate", "cli/cli"])

    def test_names_only_keep_existing_version_without_network(self):
        self.save(template("cli/cli@v2.101.0"))
        before = self.path.read_bytes()
        with patch("sync.subprocess.run") as generate:
            self.assertFalse(sync_file(self.path, template("cli/cli")))
        generate.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_names_only_resolve_new_tools_using_existing_registry_ref(self):
        current = template("cli/cli@v2.101.0", "nektos/act@v0.2.88")
        current["registries"][0]["ref"] = "v4.600.0"
        self.save(current)
        def generate(command, **kwargs):
            config = self.yaml.load(Path(command[2]).read_text())
            self.assertEqual(config["registries"][0]["ref"], "v4.600.0")
            self.assertEqual(command[-2:], ["generate", "x-motemen/ghq"])
            return subprocess.CompletedProcess(command, 0, stdout='- name: x-motemen/ghq@v1.9.4\n', stderr='')
        with patch("sync.subprocess.run", side_effect=generate):
            sync_file(self.path, template("cli/cli", "x-motemen/ghq"))
        self.assertEqual(self.load()["packages"], [
            {"name": "cli/cli@v2.101.0"}, {"name": "x-motemen/ghq@v1.9.4"},
        ])

    def test_resolution_failure_does_not_commit_package_removals(self):
        self.save(template("cli/cli@v2.101.0", "nektos/act@v0.2.88"))
        before = self.path.read_bytes()
        with patch("sync.subprocess.run", side_effect=subprocess.CalledProcessError(1, "aqua", stderr="offline")):
            with self.assertRaises(subprocess.CalledProcessError):
                sync_file(self.path, template("cli/cli", "x-motemen/ghq"))
        self.assertEqual(self.path.read_bytes(), before)

    def test_resolution_failure_on_fresh_host_creates_no_config(self):
        with patch("sync.subprocess.run", side_effect=subprocess.CalledProcessError(1, "aqua")):
            with self.assertRaises(subprocess.CalledProcessError):
                sync_file(self.path, template("cli/cli"))
        self.assertFalse(self.path.exists())

    def test_unexpected_resolver_output_is_not_committed(self):
        for output in ['- name: wrong/package@v1\n', '- name: cli/cli\n']:
            with self.subTest(output=output):
                result = subprocess.CompletedProcess([], 0, stdout=output, stderr='')
                with patch("sync.subprocess.run", return_value=result):
                    with self.assertRaises(ValueError):
                        sync_file(self.path, template("cli/cli"))
                self.assertFalse(self.path.exists())

    def test_first_activation_creates_writable_regular_file(self):
        initial = template("openai/codex@rust-v0.159.3")
        self.assertTrue(sync_file(self.path, initial))
        self.assertEqual(self.load(), initial)
        self.assertFalse(self.path.is_symlink())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_add_remove_and_keep_updated_version_together(self):
        current = template("openai/codex@rust-v0.164.0", "github/copilot-cli@v1.0.88")
        current["registries"][0]["ref"] = "v4.600.0"
        current["checksum"]["require_checksum"] = True
        self.save(current)
        desired = template("openai/codex@rust-v0.159.3", "anomalyco/opencode@v1.18.31")
        self.assertTrue(sync_file(self.path, desired))
        expected = copy.deepcopy(current)
        expected["packages"][1] = desired["packages"][1]
        self.assertEqual(self.load(), expected)

    def test_changing_nix_seed_does_not_change_existing_version(self):
        self.save(template("openai/codex@rust-v0.164.0"))
        before = self.path.read_bytes()
        self.assertFalse(sync_file(self.path, template("openai/codex@rust-v0.999.0")))
        self.assertEqual(self.path.read_bytes(), before)

    def test_preserves_explicit_version_and_package_options(self):
        current = template()
        entry = {
            "name": "openai/codex", "version": "rust-v0.164.0",
            "tags": ["agent"], "update": {"enabled": False},
        }
        current["packages"] = [entry]
        self.save(current)
        sync_file(self.path, template("openai/codex@rust-v0.159.3"))
        self.assertEqual(self.load()["packages"], [entry])

    def test_removing_last_tool_empties_existing_config(self):
        self.save(template("openai/codex@rust-v0.164.0"))
        sync_file(self.path, template())
        self.assertEqual(self.load()["packages"], [])

    def test_no_tools_on_fresh_host_creates_nothing(self):
        self.assertFalse(sync_file(self.path, template()))
        self.assertFalse(self.path.parent.exists())

    def test_noop_preserves_comments_and_file_identity(self):
        self.path.parent.mkdir()
        self.path.write_text(
            "# local settings\nregistries:\n- type: standard\n  ref: v4.600.0\n"
            "checksum:\n  enabled: true\npackages:\n- name: openai/codex@rust-v0.164.0 # chosen version\n"
        )
        before = self.path.read_bytes()
        inode = self.path.stat().st_ino
        self.assertFalse(sync_file(self.path, template("openai/codex@rust-v0.159.3")))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.path.stat().st_ino, inode)

    def test_missing_defaults_are_filled_without_losing_other_settings(self):
        self.save({"packages": [], "import_dir": "custom"})
        sync_file(self.path, template("openai/codex@rust-v0.159.3"))
        self.assertEqual(self.load()["import_dir"], "custom")
        self.assertEqual(self.load()["registries"], template()["registries"])

    def test_nonstandard_registry_is_not_mistaken_for_standard(self):
        current = template()
        current["packages"] = [{"name": "openai/codex@custom", "registry": "local"}]
        self.save(current)
        desired = template("openai/codex@rust-v0.159.3")
        sync_file(self.path, desired)
        self.assertEqual(self.load()["packages"], desired["packages"])

    def test_imports_are_rejected_without_overwriting(self):
        self.save({"packages": [{"import": "other/*.yaml"}]})
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            sync_file(self.path, template("openai/codex@rust-v0.159.3"))
        self.assertEqual(self.path.read_bytes(), before)

    def test_duplicate_entries_are_rejected_without_overwriting(self):
        self.save(template("openai/codex@rust-v0.164.0", "openai/codex@rust-v0.159.3"))
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            sync_file(self.path, template("openai/codex@rust-v0.159.3"))
        self.assertEqual(self.path.read_bytes(), before)

    def test_duplicate_nix_entries_are_rejected(self):
        with self.assertRaises(ValueError):
            sync_file(self.path, template("openai/codex@a", "openai/codex@b"))
        self.assertFalse(self.path.exists())

    def test_invalid_root_is_rejected_without_overwriting(self):
        self.path.parent.mkdir()
        self.path.write_text("[]\n")
        with self.assertRaises(ValueError):
            sync_file(self.path, template("openai/codex@rust-v0.159.3"))
        self.assertEqual(self.path.read_text(), "[]\n")

    def test_invalid_registry_or_checksum_shapes_are_not_overwritten(self):
        for key, value in [("registries", None), ("registries", "invalid"),
                           ("registries", ["invalid"]), ("checksum", "invalid")]:
            with self.subTest(key=key, value=value):
                current = template("openai/codex@rust-v0.164.0")
                current[key] = value
                self.save(current)
                before = self.path.read_bytes()
                with self.assertRaises(ValueError):
                    sync_file(self.path, template())
                self.assertEqual(self.path.read_bytes(), before)

    def test_concurrent_aqua_update_is_not_overwritten(self):
        self.save(template("openai/codex@rust-v0.164.0"))
        newer = template("openai/codex@rust-v0.165.0")
        newer["registries"][0]["ref"] = "v4.601.0"
        with patch("sync.os.fsync", side_effect=lambda _: self.save(newer)):
            with self.assertRaisesRegex(ValueError, "changed during synchronization"):
                sync_file(self.path, template())
        self.assertEqual(self.load(), newer)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_concurrently_created_config_is_not_overwritten(self):
        newer = template("openai/codex@rust-v0.165.0")
        with patch("sync.os.fsync", side_effect=lambda _: self.save(newer)):
            with self.assertRaisesRegex(ValueError, "changed during synchronization"):
                sync_file(self.path, template("openai/codex@rust-v0.159.3"))
        self.assertEqual(self.load(), newer)

    def test_symlinks_are_rejected_without_touching_target(self):
        target = Path(self.directory.name) / "target.yaml"
        target.write_text("keep me\n")
        self.path.parent.mkdir()
        self.path.symlink_to(target)
        with self.assertRaises(ValueError):
            sync_file(self.path, template("openai/codex@rust-v0.159.3"))
        self.assertTrue(self.path.is_symlink())
        self.assertEqual(target.read_text(), "keep me\n")

    def test_broken_symlink_is_not_overwritten(self):
        self.path.parent.mkdir()
        self.path.symlink_to(self.path.parent / "missing.yaml")
        with self.assertRaises(ValueError):
            sync_file(self.path, template("openai/codex@rust-v0.159.3"))
        self.assertTrue(self.path.is_symlink())

    def test_checksum_sidecar_is_untouched(self):
        self.save(template("openai/codex@rust-v0.164.0"))
        sidecar = self.path.parent / "aqua-checksums.json"
        sidecar.write_text('{"checksums": {}}\n')
        sync_file(self.path, template())
        self.assertEqual(sidecar.read_text(), '{"checksums": {}}\n')

    def test_preserves_file_mode_and_leaves_no_temporary_files(self):
        self.save(template("openai/codex@rust-v0.164.0"))
        os.chmod(self.path, 0o640)
        sync_file(self.path, template())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


if __name__ == "__main__":
    unittest.main()
