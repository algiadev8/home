"""Contract tests for the per-session Browser Harness CLI."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest import mock

# cli.py is a Nix wrapper entry point and reads these values when imported.
_TEST_ENV = {
    "BROWSER_HARNESS_BIN": "/fake/browser-harness",
    "BROWSER_DOCKER_IMAGE": "browser-test-image",
    "BROWSER_DOCKER_SOURCE": "/fake/browser-source",
    "BROWSER_SKILL_PATH": "/fake/SKILL.md",
}
with mock.patch.dict(os.environ, _TEST_ENV):
    import cli


MANAGED = "io.dsh.browser.managed"
NAMESPACE = "io.dsh.browser.namespace"
VERSION = "io.dsh.browser.version"
WORKER = "io.dsh.browser.worker"
SESSION_HASH = "io.dsh.browser.session-sha256"
HASH_ALG = "io.dsh.browser.session-hash-alg"
IMAGE_LABEL = "io.dsh.browser.image"


class FakeRunner:
    """A docker/colima runner that records argv and never starts real services."""

    def __init__(self):
        self.calls = []
        self.responses = []
        self.handler = None

    def __call__(self, argv, *, capture=False, check=True):
        argv = list(argv)
        self.calls.append(argv)
        for predicate, response in self.responses:
            if predicate(argv):
                return response
        if self.handler is not None:
            return self.handler(argv, capture=capture, check=check)
        # Empty inspect means absent; other commands succeed without side effects.
        stdout = "[]" if "inspect" in argv else ""
        return SimpleNamespace(returncode=1 if "inspect" in argv else 0,
                               stdout=stdout, stderr="")

    def reply(self, predicate, *, returncode=0, stdout="", stderr=""):
        self.responses.insert(0, (predicate, SimpleNamespace(
            returncode=returncode, stdout=stdout, stderr=stderr)))


def completed(stdout="", returncode=0, stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def container_inspect(identity, *, image=cli.IMAGE, running=True, view_port=50180, cdp_port=50181):
    return [{
        "Id": "container-id",
        "Name": f"/{identity['container']}",
        "Config": {"Labels": cli.labels_for(identity, image=image)},
        "State": {"Running": running},
        "NetworkSettings": {"Ports": {
            "6080/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(view_port)}],
            "9223/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(cdp_port)}],
        }},
    }]


def volume_inspect(identity):
    return [{"Name": identity["volume"], "Labels": cli.labels_for(identity)}]


def json_reply(value, returncode=0):
    return completed(json.dumps(value), returncode)


class SessionSelectionTests(unittest.TestCase):
    def test_explicit_session_wins_and_is_removed_from_harness_argv(self):
        session, remaining = cli.parse_session_args(
            ["--session", "cli-session", "--version", "--flag"],
            {"DSH_SESSION_ID": "environment-session"},
        )
        self.assertEqual(session, "cli-session")
        self.assertEqual(remaining, ["--version", "--flag"])

    def test_environment_session_is_used_when_flag_absent(self):
        session, remaining = cli.parse_session_args(
            ["click", "--arg"], {"DSH_SESSION_ID": "from-env"}
        )
        self.assertEqual(session, "from-env")
        self.assertEqual(remaining, ["click", "--arg"])

    def test_missing_session_explains_both_supported_sources(self):
        with self.assertRaises((ValueError, RuntimeError)) as caught:
            cli.parse_session_args(["--version"], {})
        message = str(caught.exception)
        self.assertIn("--session", message)
        self.assertIn("DSH_SESSION_ID", message)

    def test_empty_and_whitespace_explicit_session_are_rejected(self):
        for value in ("", " ", "\t\n"):
            with self.subTest(value=repr(value)):
                with self.assertRaises((ValueError, RuntimeError)):
                    cli.parse_session_args(["--session", value], {})

    def test_equals_form_is_supported(self):
        session, remaining = cli.parse_session_args(
            ["--session=opaque/id with spaces", "--version"], {}
        )
        self.assertEqual(session, "opaque/id with spaces")
        self.assertEqual(remaining, ["--version"])

    def test_session_flag_is_only_removed_at_front(self):
        session, remaining = cli.parse_session_args(
            ["--session", "front", "click", "--session", "later"], {}
        )
        self.assertEqual(session, "front")
        self.assertEqual(remaining, ["click", "--session", "later"])


class IdentityAndOwnershipTests(unittest.TestCase):
    SESSION = "session with arbitrary / punctuation !"

    def setUp(self):
        self.identity = cli.worker_identity(self.SESSION)

    def test_worker_identity_is_stable_full_hash_and_128_bit_prefix(self):
        expected_full = hashlib.sha256(self.SESSION.encode("utf-8")).hexdigest()
        worker_id = self.identity["worker_id"]
        self.assertEqual(worker_id, cli.worker_identity(self.SESSION)["worker_id"])
        self.assertEqual(self.identity["session_hash"], expected_full)
        self.assertEqual(worker_id, expected_full[:32])
        self.assertEqual(len(worker_id), 32)
        self.assertRegex(worker_id, r"^[0-9a-f]{32}$")

    def test_unicode_session_uses_utf8_hash_and_never_leaks_into_names(self):
        session = "セッション with spaces/and/slashes"
        identity = cli.worker_identity(session)
        full_hash = hashlib.sha256(session.encode("utf-8")).hexdigest()
        self.assertEqual(identity["session_hash"], full_hash)
        self.assertEqual(identity["worker_id"], full_hash[:32])
        self.assertEqual(identity["container"], f"bhw-v1-{full_hash[:32]}")
        self.assertEqual(identity["volume"], f"bhw-v1-{full_hash[:32]}-profile")
        self.assertEqual(identity["bu_name"], f"bhw-{full_hash[:32]}")
        for key in ("container", "volume", "bu_name"):
            self.assertNotIn(session, identity[key])

    def test_docker_names_and_daemon_name_are_safe(self):
        worker_id = self.identity["worker_id"]
        self.assertEqual(self.identity["container"], f"bhw-v1-{worker_id}")
        self.assertEqual(self.identity["volume"], f"bhw-v1-{worker_id}-profile")
        self.assertEqual(self.identity["bu_name"], f"bhw-{worker_id}")
        for key in ("container", "volume"):
            self.assertRegex(self.identity[key], r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
        self.assertRegex(self.identity["bu_name"], r"^[A-Za-z0-9_-]{1,64}$")
        for key in ("container", "volume", "bu_name"):
            self.assertNotIn(self.SESSION, self.identity[key])

    def test_labels_include_full_sha256_on_container_and_volume(self):
        labels = cli.labels_for(self.identity, image="test-image")
        for key in (MANAGED, NAMESPACE, VERSION, WORKER, SESSION_HASH, HASH_ALG):
            self.assertEqual(labels[key], {
                MANAGED: "1", NAMESPACE: "bhw", VERSION: "1",
                WORKER: self.identity["worker_id"],
                SESSION_HASH: self.identity["session_hash"],
                HASH_ALG: "sha256",
            }[key])
        self.assertEqual(labels[IMAGE_LABEL], "test-image")
        volume_labels = cli.labels_for(self.identity)
        self.assertNotIn(IMAGE_LABEL, volume_labels)
        self.assertEqual(volume_labels[SESSION_HASH], self.identity["session_hash"])

    def test_matching_ownership_labels_are_accepted(self):
        labels = cli.labels_for(self.identity, image="test-image")
        self.assertTrue(cli.verify_owned(labels, self.identity))
        self.assertTrue(cli.verify_owned(labels, self.identity, image="test-image"))
        self.assertFalse(cli.verify_owned(labels, self.identity, image="replacement-image"))

    def test_collision_with_same_worker_prefix_but_wrong_full_hash_is_refused(self):
        labels = cli.labels_for(self.identity, image="test-image")
        replacement_tail = "0" * 32 if self.identity["session_hash"][32:] != "0" * 32 else "1" * 32
        colliding_full_hash = self.identity["worker_id"] + replacement_tail
        self.assertEqual(colliding_full_hash[:32], self.identity["worker_id"])
        self.assertNotEqual(colliding_full_hash, self.identity["session_hash"])
        labels[SESSION_HASH] = colliding_full_hash
        self.assertFalse(cli.verify_owned(labels, self.identity))

    def test_wrong_or_missing_ownership_labels_are_refused(self):
        valid = cli.labels_for(self.identity, image="test-image")
        for key, wrong in ((MANAGED, "0"), (NAMESPACE, "other"),
                           (VERSION, "2"), (WORKER, "0" * 32)):
            with self.subTest(key=key):
                labels = dict(valid)
                labels[key] = wrong
                self.assertFalse(cli.verify_owned(labels, self.identity))
        for key in (MANAGED, NAMESPACE, VERSION, WORKER, SESSION_HASH, HASH_ALG):
            with self.subTest(missing=key):
                labels = dict(valid)
                del labels[key]
                self.assertFalse(cli.verify_owned(labels, self.identity))


class InspectionAndEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.identity = cli.worker_identity("port-and-env-session")

    def test_dynamic_host_ports_are_read_from_inspect_json(self):
        inspect_json = [{"NetworkSettings": {"Ports": {
            "6080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "50180"}],
            "9223/tcp": [{"HostIp": "127.0.0.1", "HostPort": "50181"}],
        }}}]
        ports = cli.ports_from_inspect(inspect_json)
        self.assertEqual(ports["view"], 50180)
        self.assertEqual(ports["cdp"], 50181)

    def test_port_extraction_rejects_non_loopback_publish(self):
        inspect_json = [{"NetworkSettings": {"Ports": {
            "6080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "50180"}],
            "9223/tcp": [{"HostIp": "127.0.0.1", "HostPort": "50181"}],
        }}}]
        self.assertIsNone(cli.ports_from_inspect(inspect_json))

    def test_harness_environment_is_per_worker_and_preserves_recording_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            supplied = {"BH_RECORD": "1", "BU_CDP_WS": "stale", "BU_BROWSER_ID": "stale",
                        "BH_RUNTIME_DIR_SHARED": "1", "BH_TMP_DIR_SHARED": "1"}
            env = cli.harness_env(self.identity, {"cdp": 50181}, tmp, supplied)
            self.assertEqual(env["BU_NAME"], self.identity["bu_name"])
            self.assertEqual(env["BU_CDP_URL"], "http://127.0.0.1:50181")
            runtime_dir = Path(env["BH_RUNTIME_DIR"])
            self.assertEqual(runtime_dir.name, self.identity["worker_id"])
            self.assertLessEqual(len(os.fsencode(runtime_dir / "bu.sock")), 104)
            self.assertNotEqual(runtime_dir.parent, Path(tmp))
            second_identity = cli.worker_identity("another-worker")
            second_env = cli.harness_env(second_identity, {"cdp": 50182}, tmp, {})
            self.assertNotEqual(env["BH_RUNTIME_DIR"], second_env["BH_RUNTIME_DIR"])
            self.assertEqual(env["BH_RECORD"], "1")
            for name in ("BU_CDP_WS", "BU_BROWSER_ID", "BH_REQUIRE_EXISTING_DAEMON",
                         "BU_AUTOSPAWN", "BH_RUNTIME_DIR_SHARED", "BH_TMP_DIR_SHARED"):
                self.assertNotIn(name, env)
            self.assertEqual(env["BH_TAB_MARKER"], "0")
            self.assertEqual(env["BH_HOME"], os.path.join(tmp, "harness", self.identity["worker_id"]))
            self.assertEqual(env["BH_TMP_DIR"], os.path.join(env["BH_HOME"], "tmp"))

    def test_recording_defaults_to_zero_and_runtime_socket_stays_within_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = cli.harness_env(self.identity, {"cdp": 9223}, tmp, {})
            self.assertEqual(env["BH_RECORD"], "0")
            self.assertLessEqual(len(os.fsencode(os.path.join(env["BH_RUNTIME_DIR"], "bu.sock"))), 104)

    def test_default_xdg_state_path_keeps_name_and_socket_within_budgets(self):
        with tempfile.TemporaryDirectory() as home:
            root = cli.state_root({"HOME": home, "XDG_STATE_HOME": ""})
            self.assertEqual(root, Path(home) / ".local/state/browser")
            env = cli.harness_env(self.identity, {"cdp": 9223}, root, {"HOME": home})
            self.assertLessEqual(len(env["BU_NAME"]), 64)
            runtime = Path(env["BH_RUNTIME_DIR"])
            socket_path = runtime / "bu.sock"
            self.assertLessEqual(len(os.fsencode(socket_path)), 104)
            self.assertEqual(runtime.name, self.identity["worker_id"])
            self.assertFalse(runtime.is_relative_to(root))
            cli.prepare_worker_state(self.identity, root)
            self.assertEqual(os.stat(runtime.parent).st_mode & 0o777, 0o700)
            self.assertEqual(os.stat(runtime).st_mode & 0o777, 0o700)


class DaemonBindingTests(unittest.TestCase):
    def setUp(self):
        self.identity = cli.worker_identity("daemon-session")
        self.cdp_url = "http://127.0.0.1:49223"

    def test_matching_daemon_browser_identity_is_accepted_without_reload(self):
        queried = []
        reloaded = []
        result = cli.verify_daemon_binding(
            self.identity, self.cdp_url, browser_target_id="browser-1",
            query=lambda name, method, params: (queried.append((name, method, params)) or
                                                  {"targetInfo": {"targetId": "browser-1"}}),
            reload=lambda name: reloaded.append(name),
        )
        self.assertTrue(result)
        self.assertEqual(queried, [(self.identity["bu_name"], "Target.getTargetInfo", {})])
        self.assertEqual(reloaded, [])

    def test_mismatch_reloads_only_this_worker_then_fails_closed_if_still_wrong(self):
        identities = iter(("old-browser", "still-wrong"))
        reloaded = []
        with self.assertRaises((RuntimeError, ValueError)):
            cli.verify_daemon_binding(
                self.identity, self.cdp_url, browser_target_id="browser-1",
                query=lambda name, method, params: {"targetInfo": {"targetId": next(identities)}},
                reload=lambda name: reloaded.append(name),
            )
        self.assertEqual(reloaded, [self.identity["bu_name"]])


class CommandAndPassthroughTests(unittest.TestCase):
    def invoke(self, argv, runner=None, env=None):
        out, err = StringIO(), StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            old_state = cli.STATE
            cli.STATE = Path(tmp) / "browser"
            isolated_env = dict(os.environ)
            isolated_env.pop("DSH_SESSION_ID", None)
            isolated_env["XDG_STATE_HOME"] = tmp
            if env:
                isolated_env.update(env)
            try:
                with mock.patch.dict(os.environ, isolated_env, clear=True), mock.patch.object(sys, "argv", ["browser", *argv]), \
                     mock.patch.object(cli, "RUNNER", runner or FakeRunner()), \
                     redirect_stdout(out), redirect_stderr(err):
                    cli.main()
            finally:
                cli.STATE = old_state
        return out.getvalue(), err.getvalue()

    def test_nonexistent_stop_is_idempotent_and_does_not_stop_engine_or_other_workers(self):
        runner = FakeRunner()
        with mock.patch.object(sys, "platform", "linux"):
            self.invoke(["--session", "not-running", "stop"], runner)
        destructive = [call for call in runner.calls if call[:2] in (
            ["docker", "stop"], ["docker", "rm"], ["docker", "container"],
            ["colima", "--profile"],
        ) and (call[:2] != ["docker", "container"] or "stop" in call)]
        self.assertFalse(any(call[:2] in (["docker", "stop"], ["docker", "rm"]) for call in destructive))
        self.assertFalse(any("other" in call for call in runner.calls))
        self.assertFalse(any(call[:2] == ["colima", "stop"] for call in runner.calls))

    def test_remove_requires_an_explicit_session(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            _, err = self.invoke(["remove"])
        self.assertIn("--session", err)

    def test_remove_keeps_profile_volume_unless_purge_is_requested(self):
        # Exercise both forms with a fake Docker runner; no real Docker/Colima is run.
        identity = cli.worker_identity("remove-session")
        container = container_inspect(identity)[0]
        volume = volume_inspect(identity)[0]
        for args, should_remove_volume in ((["remove"], False),
                                           (["remove", "--purge-profile"], True)):
            runner = FakeRunner()

            def respond(argv, *, capture=False, check=True):
                if argv[:2] == ["docker", "info"]:
                    return completed("linux")
                if argv[:3] == ["docker", "container", "inspect"]:
                    return json_reply([container])
                if argv[:3] == ["docker", "volume", "inspect"]:
                    return json_reply([volume])
                return completed()

            runner.handler = respond
            with self.subTest(args=args), mock.patch.object(sys, "platform", "linux"):
                self.invoke(["--session", "remove-session", *args], runner)
            volume_removes = [call for call in runner.calls if call[:2] == ["docker", "volume"] and "rm" in call]
            self.assertEqual(bool(volume_removes), should_remove_volume)

    def test_skill_prints_documentation_without_starting_worker_or_exec(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_path = os.path.join(tmp, "SKILL.md")
            contents = "# Browser skill\ncontract fixture\n"
            with open(skill_path, "w", encoding="utf-8") as stream:
                stream.write(contents)
            runner = FakeRunner()
            exec_calls = []
            out, err = StringIO(), StringIO()
            with mock.patch.dict(os.environ, {"BROWSER_SKILL_PATH": skill_path}), \
                 mock.patch.object(sys, "argv", ["browser", "--session=skill-session", "skill"]), \
                 mock.patch.object(cli, "RUNNER", runner), \
                 mock.patch.object(cli.os, "execv", side_effect=lambda path, argv: exec_calls.append((path, argv))), \
                 redirect_stdout(out), redirect_stderr(err):
                cli.main()
            self.assertEqual(out.getvalue(), contents)
            self.assertEqual(err.getvalue(), "")
            self.assertEqual(runner.calls, [])
            self.assertEqual(exec_calls, [])

    def test_passthrough_exec_preserves_argv_and_never_reads_stdin(self):
        class UnreadableStdin:
            def read(self, *args, **kwargs):
                raise AssertionError("CLI must not read Python stdin")

        exec_calls = []
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(sys, "argv", ["browser", "--session", "exec-session", "--version", "--verbose"]), \
             mock.patch.object(sys, "stdin", UnreadableStdin()), \
             mock.patch.object(cli.os, "execv", side_effect=lambda path, argv: exec_calls.append((path, argv))), \
             mock.patch.object(cli, "RUNNER", FakeRunner()):
            cli.main()
        self.assertEqual(exec_calls, [(cli.HARNESS, [cli.HARNESS, "--version", "--verbose"])])

    def test_unknown_first_token_is_harness_passthrough_not_management(self):
        exec_calls = []
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(sys, "argv", ["browser", "--session=unknown", "nonesuch", "arg"]), \
             mock.patch.object(cli.os, "execv", side_effect=lambda path, argv: exec_calls.append((path, argv))), \
             mock.patch.object(cli, "RUNNER", FakeRunner()):
            cli.main()
        self.assertEqual(exec_calls, [(cli.HARNESS, [cli.HARNESS, "nonesuch", "arg"])])


class LifecycleHelperTests(unittest.TestCase):
    def setUp(self):
        self.session = "lifecycle-session"
        self.identity = cli.worker_identity(self.session)

    def runner_for(self, containers=None, volumes=None):
        containers = [] if containers is None else containers
        volumes = [] if volumes is None else volumes
        runner = FakeRunner()
        container_ids = [item.get("Id", "container-id") for item in containers]

        def respond(argv, *, capture=False, check=True):
            if argv[:3] == ["colima", "--profile", cli.ENGINE_PROFILE] and "status" in argv:
                return completed(json.dumps({"docker_socket": "/fake/docker.sock"}))
            if argv[:2] == ["docker", "info"]:
                return completed("linux")
            if "ls" in argv and "container" in argv:
                return completed("\n".join(container_ids))
            if "inspect" in argv:
                if "volume" in argv:
                    return json_reply(volumes, 0 if volumes else 1)
                return json_reply(containers, 0 if containers else 1)
            return completed()

        runner.handler = respond
        return runner

    def mutable_worker_runner(self, container, volume, replacement=None):
        runner = FakeRunner()
        state = {"container": container, "volume": volume, "replacement": replacement}

        def respond(argv, *, capture=False, check=True):
            if argv[:2] == ["docker", "info"]:
                return completed("linux")
            if argv[:3] == ["docker", "image", "inspect"]:
                return completed("browser-image")
            if argv[:3] == ["docker", "container", "inspect"]:
                records = [state["container"]] if state["container"] is not None else []
                return json_reply(records, 0 if records else 1)
            if argv[:3] == ["docker", "volume", "inspect"]:
                records = [state["volume"]] if state["volume"] is not None else []
                return json_reply(records, 0 if records else 1)
            if argv[:3] == ["docker", "container", "start"]:
                state["container"]["State"]["Running"] = True
                return completed()
            if argv[:3] == ["docker", "container", "rm"]:
                state["container"] = None
                return completed()
            if argv[:2] == ["docker", "run"]:
                state["container"] = state["replacement"]
                return completed()
            return completed()

        runner.handler = respond
        return runner, state

    def test_nonexistent_status_is_read_only_and_reports_not_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = self.runner_for()
            status = cli.worker_status(self.session, {"XDG_STATE_HOME": tmp}, runner)
        self.assertFalse(status["running"])
        self.assertFalse(status["ready"])
        self.assertFalse(any(call[:2] in (["docker", "start"], ["docker", "run"])
                             for call in runner.calls))
        self.assertFalse(any("colima" in call and "start" in call for call in runner.calls))

    def test_list_includes_only_managed_namespace_and_version_workers(self):
        valid = container_inspect(self.identity, running=False)[0]
        wrong_namespace = container_inspect(self.identity, running=False)[0]
        wrong_namespace["Config"]["Labels"][NAMESPACE] = "elsewhere"
        wrong_version = container_inspect(self.identity, running=False)[0]
        wrong_version["Config"]["Labels"][VERSION] = "2"
        unmanaged = container_inspect(self.identity, running=False)[0]
        unmanaged["Config"]["Labels"][MANAGED] = "0"
        runner = self.runner_for([valid, wrong_namespace, wrong_version, unmanaged])
        with tempfile.TemporaryDirectory() as tmp:
            records = cli.list_workers({"XDG_STATE_HOME": tmp}, runner)
        self.assertEqual([item["worker_id"] for item in records], [self.identity["worker_id"]])
        self.assertFalse(any(call[:2] in (["docker", "start"], ["docker", "run"])
                             for call in runner.calls))
        self.assertFalse(any("colima" in call and "start" in call for call in runner.calls))

    def test_start_reuses_running_worker_and_uses_inspected_ports(self):
        container = container_inspect(self.identity, running=True, view_port=50186, cdp_port=50222)[0]
        volume = volume_inspect(self.identity)[0]
        runner, _ = self.mutable_worker_runner(container, volume)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(cli.sys, "platform", "linux"):
            with mock.patch.object(cli, "_worker_ready", return_value=True):
                worker = cli.ensure_worker(
                    self.session, {"XDG_STATE_HOME": tmp}, runner, timeout=0
                )
        self.assertFalse(worker["changed"])
        self.assertEqual(worker["ports"], {"view": 50186, "cdp": 50222})
        self.assertFalse(any(call[:3] in (
            ["docker", "container", "rm"], ["docker", "container", "start"],
            ["docker", "run"],
        ) for call in runner.calls))

    def test_image_change_recreates_only_container_and_preserves_profile(self):
        old = container_inspect(self.identity, image="older-image", running=True)[0]
        replacement = container_inspect(
            self.identity, image=cli.IMAGE, running=True, view_port=50187, cdp_port=50223
        )[0]
        volume = volume_inspect(self.identity)[0]
        runner, state = self.mutable_worker_runner(old, volume, replacement)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(cli.sys, "platform", "linux"):
            with mock.patch.object(cli, "_worker_ready", return_value=True):
                worker = cli.ensure_worker(
                    self.session, {"XDG_STATE_HOME": tmp}, runner, timeout=0
                )
        self.assertTrue(worker["changed"])
        self.assertEqual(state["container"]["Config"]["Labels"][IMAGE_LABEL], cli.IMAGE)
        self.assertIs(state["volume"], volume)
        self.assertEqual(sum(call[:3] == ["docker", "container", "rm"] for call in runner.calls), 1)
        self.assertEqual(sum(call[:2] == ["docker", "run"] for call in runner.calls), 1)
        self.assertFalse(any(call[:3] == ["docker", "volume", "rm"] for call in runner.calls))

    def test_start_recovers_stopped_worker_and_requests_daemon_reload(self):
        container = container_inspect(self.identity, running=False)[0]
        volume = volume_inspect(self.identity)[0]
        runner, state = self.mutable_worker_runner(container, volume)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(cli.sys, "platform", "linux"):
            with mock.patch.object(cli, "_worker_ready", return_value=True), \
                 mock.patch.object(cli, "ensure_daemon") as ensure_daemon, \
                 redirect_stdout(StringIO()):
                result = cli.main(
                    ["--session", self.session, "start"],
                    env={"XDG_STATE_HOME": tmp}, runner=runner,
                )
        self.assertEqual(result, 0)
        self.assertTrue(state["container"]["State"]["Running"])
        self.assertEqual(sum(call[:3] == ["docker", "container", "start"] for call in runner.calls), 1)
        self.assertFalse(any(call[:2] == ["docker", "run"] or call[:3] == ["docker", "container", "rm"]
                             for call in runner.calls))
        ensure_daemon.assert_called_once()
        args, kwargs = ensure_daemon.call_args
        self.assertEqual(args[0]["bu_name"], self.identity["bu_name"])
        self.assertEqual(args[2]["BU_NAME"], self.identity["bu_name"])
        self.assertTrue(kwargs["force_reload"])

    def test_stop_refuses_wrong_container_or_volume_ownership(self):
        for bad_resource in ("container", "volume"):
            with self.subTest(bad_resource=bad_resource), tempfile.TemporaryDirectory() as tmp:
                container = container_inspect(self.identity, running=True)[0]
                volume = volume_inspect(self.identity)[0]
                if bad_resource == "container":
                    container["Config"]["Labels"][SESSION_HASH] = "f" * 64
                else:
                    volume["Labels"][HASH_ALG] = "wrong"
                runner, _ = self.mutable_worker_runner(container, volume)
                with mock.patch.object(cli.sys, "platform", "linux"):
                    with self.assertRaises(cli.BrowserCLIError):
                        cli.stop_worker(self.session, {"XDG_STATE_HOME": tmp}, runner)
                self.assertFalse(any(call[:3] == ["docker", "container", "rm"]
                                     or call[:3] == ["docker", "volume", "rm"]
                                     or call[0] == _TEST_ENV["BROWSER_HARNESS_BIN"]
                                     for call in runner.calls))

    def test_reload_passthrough_targets_only_this_worker_without_starting_container(self):
        class EnvironmentRunner(FakeRunner):
            def __init__(self):
                super().__init__()
                self.environments = []

            def __call__(self, argv, *, env=None, capture=False, check=True):
                self.environments.append((list(argv), dict(env or {})))
                return super().__call__(argv, capture=capture, check=check)

        runner = EnvironmentRunner()
        with mock.patch.dict(os.environ, {}, clear=True):
            result = cli.main(
                ["--session", self.session, "--reload"],
                env={"XDG_STATE_HOME": "/fake-state"}, runner=runner,
            )
        self.assertEqual(result, 0)
        self.assertEqual(runner.calls, [[_TEST_ENV["BROWSER_HARNESS_BIN"], "--reload"]])
        self.assertEqual(runner.environments[0][1]["BU_NAME"], self.identity["bu_name"])
        self.assertFalse(any(call and call[0] == "docker" for call in runner.calls))

    def test_view_uses_inspected_port_and_opens_only_when_requested(self):
        record = container_inspect(self.identity, running=True, view_port=50185, cdp_port=50221)
        for should_open in (False, True):
            with self.subTest(should_open=should_open), tempfile.TemporaryDirectory() as tmp:
                runner = self.runner_for(record)
                with mock.patch.object(cli.sys, "platform", "darwin"):
                    result = cli.view_worker(
                        self.session, {"XDG_STATE_HOME": tmp}, runner, open_view=should_open
                    )
                self.assertEqual(result["view"], f"http://127.0.0.1:50185{cli.VIEW_PATH}")
                open_calls = [call for call in runner.calls if call and call[0] == "open"]
                self.assertEqual(len(open_calls), int(should_open))
                if should_open:
                    self.assertEqual(open_calls[0][1], result["view"])


class BrowserBindingProbeTests(unittest.TestCase):
    """The binding proof compares browser context ids, never per-connection ids."""

    def setUp(self):
        self.identity = cli.worker_identity("binding-probe-session")
        self.cdp_url = "http://127.0.0.1:50123"

    def test_browser_instance_identity_comes_from_json_version(self):
        websocket = "ws://127.0.0.1:50123/devtools/browser/7447a5de-9b8f-4868-aad5-77c9f6b2127a"
        with mock.patch.object(cli, "_http_browser_websocket", return_value=websocket):
            self.assertEqual(
                cli.browser_instance_identity(self.cdp_url),
                "7447a5de-9b8f-4868-aad5-77c9f6b2127a",
            )

    def test_unreachable_endpoint_has_no_identity(self):
        with mock.patch.object(cli, "_http_browser_websocket", return_value=None):
            self.assertIsNone(cli.browser_instance_identity(self.cdp_url))

    def test_daemon_bound_when_context_ids_match(self):
        requests = []

        def ipc_request(identity, request, timeout=1.0):
            requests.append(request)
            return {"result": {"browserContextIds": [], "defaultBrowserContextId": "CTX1"}}

        with mock.patch.object(cli, "_http_browser_websocket", return_value="ws://x/devtools/browser/id"), \
             mock.patch.object(cli, "_browser_default_context", return_value="CTX1"), \
             mock.patch.object(cli, "_ipc_request", side_effect=ipc_request):
            self.assertTrue(cli._daemon_bound(self.identity, self.cdp_url, None, None))
        self.assertEqual(requests, [{"method": "Target.getBrowserContexts", "params": {}}])

    def test_daemon_bound_false_when_context_ids_differ(self):
        def ipc_request(identity, request, timeout=1.0):
            return {"result": {"defaultBrowserContextId": "OTHER"}}

        with mock.patch.object(cli, "_http_browser_websocket", return_value="ws://x/devtools/browser/id"), \
             mock.patch.object(cli, "_browser_default_context", return_value="CTX1"), \
             mock.patch.object(cli, "_ipc_request", side_effect=ipc_request):
            self.assertFalse(cli._daemon_bound(self.identity, self.cdp_url, None, None))

    def test_daemon_bound_false_without_live_daemon(self):
        with mock.patch.object(cli, "_http_browser_websocket", return_value="ws://x/devtools/browser/id"), \
             mock.patch.object(cli, "_browser_default_context", return_value="CTX1"), \
             mock.patch.object(cli, "_ipc_request", return_value=None):
            self.assertFalse(cli._daemon_bound(self.identity, self.cdp_url, None, None))

    def test_ensure_daemon_reloads_only_this_worker_until_bound(self):
        reloads = []
        bound = iter((False, True))

        def reload_callback(identity, env, runner):
            reloads.append(identity["bu_name"])

        with mock.patch.object(cli, "prepare_worker_state"), \
             mock.patch.object(cli, "_reload_and_bootstrap", side_effect=reload_callback), \
             mock.patch.object(cli, "_daemon_bound", side_effect=lambda *a, **k: next(bound)):
            self.assertTrue(cli.ensure_daemon(self.identity, self.cdp_url, {}, None))
        self.assertEqual(reloads, [self.identity["bu_name"]])

    def test_ensure_daemon_fails_closed_when_binding_never_proves(self):
        with mock.patch.object(cli, "prepare_worker_state"), \
             mock.patch.object(cli, "_reload_and_bootstrap"), \
             mock.patch.object(cli, "_daemon_bound", return_value=False):
            with self.assertRaises(cli.BrowserCLIError):
                cli.ensure_daemon(self.identity, self.cdp_url, {}, None, timeout=0)

    def test_ensure_daemon_does_not_reload_a_bound_daemon(self):
        reloads = []
        with mock.patch.object(cli, "prepare_worker_state"), \
             mock.patch.object(cli, "_reload_and_bootstrap", side_effect=lambda *a: reloads.append(a)), \
             mock.patch.object(cli, "_daemon_bound", return_value=True):
            self.assertTrue(cli.ensure_daemon(self.identity, self.cdp_url, {}, None))
        self.assertEqual(reloads, [])


class RuntimeDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.identity = cli.worker_identity("runtime-dir-session")

    def test_runtime_socket_path_fits_macos_af_unix_limit(self):
        path = cli._runtime_dir(self.identity) / "bu.sock"
        self.assertLess(len(os.fsencode(path)), 104)

    def test_runtime_dir_is_per_worker_and_private(self):
        other = cli.worker_identity("another-runtime-session")
        self.assertNotEqual(cli._runtime_dir(self.identity), cli._runtime_dir(other))
        self.assertEqual(cli._runtime_dir(self.identity).parent, cli._runtime_dir(other).parent)
        self.assertTrue(str(cli._runtime_dir(self.identity)).startswith("/tmp/"))

    def test_prepare_worker_state_creates_private_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli.prepare_worker_state(self.identity, Path(tmp) / "browser")
            runtime = cli._runtime_dir(self.identity)
            try:
                mode = runtime.stat().st_mode & 0o777
                self.assertEqual(mode, 0o700)
                self.assertEqual(runtime.parent.stat().st_mode & 0o777, 0o700)
            finally:
                for directory in (runtime, runtime.parent):
                    try:
                        directory.rmdir()
                    except OSError:
                        pass


class HarnessFailureReportingTests(unittest.TestCase):
    def test_failed_harness_call_reports_stderr_and_daemon_log(self):
        identity = cli.worker_identity("failure-report-session")
        with tempfile.TemporaryDirectory() as tmp:
            env = cli.harness_env(identity, {"cdp": 50123}, Path(tmp), {})
            Path(env["BH_TMP_DIR"]).mkdir(parents=True, exist_ok=True)
            (Path(env["BH_TMP_DIR"]) / "bu.log").write_text("connecting to ws://127.0.0.1:50123\n")

            def runner(argv, **kwargs):
                return SimpleNamespace(returncode=1, stdout="", stderr="browser-harness: fatal: AF_UNIX path too long\n")

            with self.assertRaises(cli.BrowserCLIError) as caught:
                cli._harness_call(["--reload"], env, runner)
            message = str(caught.exception)
            self.assertIn("AF_UNIX path too long", message)
            self.assertIn("connecting to ws://127.0.0.1:50123", message)


class IdleTimeoutTests(unittest.TestCase):
    def test_default_timeout_is_one_hour(self):
        self.assertEqual(cli.idle_timeout({}), 3600)

    def test_zero_disables_reaping(self):
        self.assertEqual(cli.idle_timeout({"BROWSER_IDLE_TIMEOUT": "0"}), 0)

    def test_explicit_seconds_are_used(self):
        self.assertEqual(cli.idle_timeout({"BROWSER_IDLE_TIMEOUT": "90"}), 90)

    def test_invalid_values_fall_back_to_the_default(self):
        for value in ("", "abc", "-5", "  "):
            self.assertEqual(cli.idle_timeout({"BROWSER_IDLE_TIMEOUT": value}), 3600)

    def test_started_at_parses_nanosecond_timestamps(self):
        parsed = cli._container_started_at(
            {"State": {"StartedAt": "2026-11-08T15:14:41.018872474Z"}})
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.microsecond, 18872)

    def test_started_at_tolerates_missing_data(self):
        self.assertIsNone(cli._container_started_at(None))
        self.assertIsNone(cli._container_started_at({}))
        self.assertIsNone(cli._container_started_at({"State": {"StartedAt": "not a time"}}))

    def test_idle_seconds_uses_the_newest_marker(self):
        identity = cli.worker_identity("idle-seconds-session")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            home = state / "harness" / identity["worker_id"]
            home.mkdir(parents=True)
            (home / "last_use").write_text("0")
            container = {"State": {"StartedAt": "2020-01-01T00:00:00Z"}}
            self.assertLess(cli._idle_seconds(identity, container, state, now=1000.0), 5.0)

    def test_idle_seconds_returns_none_without_any_marker(self):
        identity = cli.worker_identity("idle-none-session")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(cli._idle_seconds(identity, {}, Path(tmp) / "missing", now=1000.0))

    def test_touch_worker_records_last_use(self):
        identity = cli.worker_identity("touch-session")
        with tempfile.TemporaryDirectory() as tmp:
            cli.touch_worker(identity, Path(tmp))
            marker = Path(tmp) / "harness" / identity["worker_id"] / "last_use"
            self.assertTrue(marker.is_file())


class ReapTests(unittest.TestCase):
    def setUp(self):
        self.identity = cli.worker_identity("reap-session")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"XDG_STATE_HOME": self.tmp.name, "HOME": self.tmp.name}

    def _records(self, *, running=True):
        return [{
            "worker_id": self.identity["worker_id"],
            "session_hash": self.identity["session_hash"],
            "container": self.identity["container"],
            "running": running, "ready": running,
        }]

    def test_zero_timeout_reaps_nothing(self):
        runner = FakeRunner()
        with mock.patch.object(cli, "list_workers", return_value=self._records()):
            result = cli.reap_idle_workers({**self.env, "BROWSER_IDLE_TIMEOUT": "0"}, runner)
        self.assertEqual(result["reaped"], [])
        self.assertEqual(result["timeout"], 0)

    def test_recent_worker_is_skipped(self):
        runner = FakeRunner()
        container = {"State": {"StartedAt": "2026-11-08T15:14:41.018872474Z"}}
        with mock.patch.object(cli, "list_workers", return_value=self._records()), \
                mock.patch.object(cli, "configure_engine", return_value=True), \
                mock.patch.object(cli, "inspect_container", return_value=container), \
                mock.patch.object(cli, "_idle_seconds", return_value=5.0), \
                mock.patch.object(cli, "_stop_worker_identity") as stop:
            result = cli.reap_idle_workers(self.env, runner, timeout=60)
        self.assertEqual(result["reaped"], [])
        self.assertEqual(len(result["skipped"]), 1)
        stop.assert_not_called()

    def test_idle_worker_is_stopped_without_purging_the_profile(self):
        runner = FakeRunner()
        container = {"State": {"StartedAt": "2026-11-08T15:14:41.018872474Z"}}
        with mock.patch.object(cli, "list_workers", return_value=self._records()), \
                mock.patch.object(cli, "configure_engine", return_value=True), \
                mock.patch.object(cli, "inspect_container", return_value=container), \
                mock.patch.object(cli, "_idle_seconds", return_value=9999.0), \
                mock.patch.object(cli, "_stop_worker_identity") as stop:
            result = cli.reap_idle_workers(self.env, runner, timeout=60)
        self.assertEqual([item["worker_id"] for item in result["reaped"]], [self.identity["worker_id"]])
        stop.assert_called_once()
        self.assertFalse(stop.call_args.kwargs.get("purge_profile", False))

    def test_dry_run_reports_without_stopping(self):
        runner = FakeRunner()
        container = {"State": {"StartedAt": "2026-11-08T15:14:41.018872474Z"}}
        with mock.patch.object(cli, "list_workers", return_value=self._records()), \
                mock.patch.object(cli, "configure_engine", return_value=True), \
                mock.patch.object(cli, "inspect_container", return_value=container), \
                mock.patch.object(cli, "_idle_seconds", return_value=9999.0), \
                mock.patch.object(cli, "_stop_worker_identity") as stop:
            result = cli.reap_idle_workers(self.env, runner, timeout=60, dry_run=True)
        self.assertEqual(len(result["reaped"]), 1)
        stop.assert_not_called()

    def test_vanished_container_is_skipped_not_reaped(self):
        runner = FakeRunner()
        with mock.patch.object(cli, "list_workers", return_value=self._records()), \
                mock.patch.object(cli, "configure_engine", return_value=True), \
                mock.patch.object(cli, "inspect_container", return_value=None), \
                mock.patch.object(cli, "_stop_worker_identity") as stop:
            result = cli.reap_idle_workers(self.env, runner, timeout=1)
        self.assertEqual(result["reaped"], [])
        stop.assert_not_called()

    def test_stop_worker_identity_uses_the_given_identity(self):
        """Reaping must not re-hash an already hashed worker id."""
        runner = FakeRunner()
        with mock.patch.object(cli, "configure_engine", return_value=True), \
                mock.patch.object(cli, "inspect_container", return_value=None), \
                mock.patch.object(cli, "inspect_volume", return_value=None), \
                mock.patch.object(cli, "worker_identity") as rehash:
            result = cli._stop_worker_identity(self.identity, self.env, runner)
        rehash.assert_not_called()
        self.assertEqual(result["worker_id"], self.identity["worker_id"])

    def test_maybe_reap_is_rate_limited(self):
        runner = FakeRunner()
        with mock.patch.object(cli, "reap_idle_workers") as reap:
            cli.maybe_reap_idle(self.env, runner)
            cli.maybe_reap_idle(self.env, runner)
        self.assertEqual(reap.call_count, 1)

    def test_maybe_reap_never_raises(self):
        runner = FakeRunner()
        with mock.patch.object(cli, "reap_idle_workers", side_effect=cli.BrowserCLIError("boom")):
            cli.maybe_reap_idle(self.env, runner)


class ForwardingTests(unittest.TestCase):
    def setUp(self):
        self.identity = cli.worker_identity("forward-session")

    def test_forwarder_name_is_derived_from_the_worker_id(self):
        name = cli.forward_container(self.identity)
        self.assertEqual(name, "bhw-fwd-" + self.identity["worker_id"])
        self.assertNotIn("forward-session", name)

    def test_forwarder_shares_the_worker_network_namespace(self):
        args = cli._forward_args(self.identity, [5173, 8080])
        self.assertEqual(args[args.index("--network") + 1], "container:" + self.identity["container"])
        self.assertIn("BHW_FORWARD_PORTS=5173 8080", args)
        self.assertNotIn("--publish", args)

    def test_forwarder_carries_ownership_labels(self):
        args = cli._forward_args(self.identity, [5173])
        for key, value in cli.labels_for(self.identity).items():
            self.assertIn(key + "=" + value, args)

    def test_port_normalization_rejects_invalid_values(self):
        self.assertEqual(cli._normalize_ports(["5173", "5173", " 8080 "]), [5173, 8080])
        for bad in ("0", "65536", "abc", "-1", ""):
            with self.assertRaises(cli.BrowserCLIError):
                cli._normalize_ports([bad])

    def test_forwarding_requires_a_running_worker(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cli, "configure_engine", return_value=True), \
                mock.patch.object(cli, "inspect_container", return_value=None):
            with self.assertRaises(cli.BrowserCLIError):
                cli.start_forwarding("forward-session", ["5173"], {"XDG_STATE_HOME": tmp, "HOME": tmp}, runner)

    def test_forwarding_rejects_a_foreign_forwarder(self):
        runner = FakeRunner()
        foreign = {"Name": "/bhw-fwd-" + self.identity["worker_id"],
                   "Config": {"Labels": {MANAGED: "1", NAMESPACE: "bhw", VERSION: "1",
                                         WORKER: self.identity["worker_id"],
                                         SESSION_HASH: "0" * 64, HASH_ALG: "sha256"}},
                   "State": {"Running": True}}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cli, "configure_engine", return_value=True), \
                mock.patch.object(cli, "inspect_container", return_value=foreign):
            with self.assertRaises(cli.BrowserCLIError):
                cli.start_forwarding("forward-session", ["5173"], {"XDG_STATE_HOME": tmp, "HOME": tmp}, runner)

    def test_unforward_is_idempotent(self):
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cli, "configure_engine", return_value=True), \
                mock.patch.object(cli, "inspect_container", return_value=None):
            result = cli.stop_forwarding("forward-session", {"XDG_STATE_HOME": tmp, "HOME": tmp}, runner)
        self.assertEqual(result["forwarded"], [])
        self.assertFalse(result["removed"])

    def test_management_commands_include_forward_and_reap(self):
        for command in ("forward", "unforward", "reap"):
            self.assertIn(command, cli.MANAGEMENT_COMMANDS)


class ManagementCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"XDG_STATE_HOME": self.tmp.name, "HOME": self.tmp.name,
                    "DSH_SESSION_ID": "management-session"}

    def _run(self, argv, runner=None):
        runner = FakeRunner() if runner is None else runner
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv, self.env, runner)
        return code, out.getvalue(), err.getvalue()

    def test_reap_dry_run_prints_json(self):
        with mock.patch.object(cli, "list_workers", return_value=[]):
            code, out, err = self._run(["reap", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["reaped"], [])
        self.assertEqual(err, "")

    def test_reap_rejects_unknown_arguments(self):
        code, out, err = self._run(["reap", "--nope"])
        self.assertEqual(code, 1)
        self.assertIn("reap accepts only", err)

    def test_reap_rejects_a_non_numeric_timeout(self):
        code, out, err = self._run(["reap", "--timeout", "soon"])
        self.assertEqual(code, 1)
        self.assertIn("whole seconds", err)

    def test_forward_requires_ports(self):
        code, out, err = self._run(["forward"])
        self.assertEqual(code, 1)
        self.assertIn("at least one port", err)

    def test_unforward_rejects_arguments(self):
        code, out, err = self._run(["unforward", "5173"])
        self.assertEqual(code, 1)
        self.assertIn("unforward does not accept arguments", err)

    def test_help_lists_the_new_commands(self):
        code, out, err = self._run(["help"])
        self.assertEqual(code, 0)
        for command in ("reap", "forward", "unforward"):
            self.assertIn(command, out)


if __name__ == "__main__":
    unittest.main()