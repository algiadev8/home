"""Per-session Browser Harness worker manager (stdlib only)."""
from contextlib import contextmanager
import datetime
import fcntl
import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import socket
import subprocess
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


NAMESPACE = "bhw"
VERSION = "1"
ENGINE_PROFILE = "agent-browser"
CONTAINER_PREFIX = "bhw-v1-"
PROFILE_SUFFIX = "-profile"
DAEMON_PREFIX = "bhw-"
LABEL_MANAGED = "io.dsh.browser.managed"
LABEL_NAMESPACE = "io.dsh.browser.namespace"
LABEL_VERSION = "io.dsh.browser.version"
LABEL_WORKER = "io.dsh.browser.worker"
LABEL_SESSION_SHA256 = "io.dsh.browser.session-sha256"
LABEL_SESSION_HASH_ALG = "io.dsh.browser.session-hash-alg"
LABEL_IMAGE = "io.dsh.browser.image"
LABEL_KEYS = (LABEL_MANAGED, LABEL_NAMESPACE, LABEL_VERSION, LABEL_WORKER, LABEL_SESSION_SHA256, LABEL_SESSION_HASH_ALG)
CONTAINER_CDP_PORT = 9223
CONTAINER_VIEW_PORT = 6080
VIEW_PATH = "/vnc.html?autoconnect=true&resize=scale&reconnect=true"
MANAGEMENT_COMMANDS = frozenset({"start", "status", "view", "list", "stop", "remove", "reap", "forward", "unforward", "help", "-h", "--help", "skill"})
FORWARD_COMMANDS = frozenset({"forward", "unforward"})
PASSTHROUGH_COMMANDS = frozenset({"--version", "--help", "-h", "auth", "telemetry", "recordings", "video", "mac-approve", "--update", "doctor", "--doctor", "--reload"})
STATE = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "browser"
HARNESS = os.environ.get("BROWSER_HARNESS_BIN", "browser-harness")
IMAGE = os.environ.get("BROWSER_DOCKER_IMAGE", "")
SOURCE = os.environ.get("BROWSER_DOCKER_SOURCE", "")
SKILL = os.environ.get("BROWSER_SKILL_PATH", "")
DEFAULT_IDLE_TIMEOUT = 3600
FORWARD_PREFIX = "bhw-fwd-"
FORWARD_IMAGE = os.environ.get("BROWSER_FORWARD_IMAGE", "alpine/socat:latest")
FORWARD_SCRIPT = r"""
# Relay each port from the worker's loopback to the host's loopback.
# The sidecar shares the worker's network namespace, so these listeners are the
# worker's own 127.0.0.1:<port>, which Colima already publishes on the host.
HOST="${BHW_HOST_ALIAS:-host.docker.internal}"
PORTS="${BHW_FORWARD_PORTS:-}"
[ -n "$PORTS" ] || exit 0
for port in $PORTS; do
  socat "TCP-LISTEN:$port,bind=127.0.0.1,fork,reuseaddr" "TCP:$HOST:$port" >/dev/null 2>&1 &
done
wait
"""



class BrowserCLIError(RuntimeError):
    """A safe user-facing error; never include raw session ids."""


def run(argv, capture=False, check=True, *, env=None, input_data=None, timeout=None):
    """Default argv runner; injectable in tests and never invokes a shell."""
    result = subprocess.run(
        list(argv), env=env, input=input_data, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        timeout=timeout, check=False,
    )
    if check and result.returncode:
        raise subprocess.CalledProcessError(result.returncode, list(argv), result.stdout, result.stderr)
    return result


RUNNER = run


def _env_copy(env=None):
    return dict(os.environ if env is None else env)


def _invoke(runner, argv, env, *, capture=False, input_data=None, timeout=None, check=False):
    runner = RUNNER if runner is None else runner
    try:
        params = inspect.signature(runner).parameters
        var_kw = any(item.kind == inspect.Parameter.VAR_KEYWORD for item in params.values())
    except (TypeError, ValueError):
        params, var_kw = {}, True
    accepts = lambda name: var_kw or name in params
    kwargs = {}
    if accepts("env"):
        kwargs["env"] = env
    if accepts("capture"):
        kwargs["capture"] = capture
    elif accepts("capture_output"):
        kwargs["capture_output"] = capture
    if accepts("check"):
        kwargs["check"] = check
    if input_data is not None:
        if accepts("input_data"):
            kwargs["input_data"] = input_data
        elif accepts("input"):
            kwargs["input"] = input_data
    if timeout is not None and accepts("timeout"):
        kwargs["timeout"] = timeout
    return runner(list(argv), **kwargs)


def _returncode(result):
    return int(getattr(result, "returncode", 0) or 0)


def _stdout(result):
    value = getattr(result, "stdout", "")
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def _private_dir(path):
    path = Path(path).expanduser()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def state_root(env=None):
    current = _env_copy(env)
    return Path(current.get("XDG_STATE_HOME") or (Path(current.get("HOME") or Path.home()) / ".local/state")).expanduser() / "browser"


def resolve_session(session_arg=None, env=None, *, required=True):
    current = _env_copy(env)
    if session_arg is not None:
        if not isinstance(session_arg, str) or not session_arg.strip():
            raise BrowserCLIError("session id is empty; use --session <id> or set DSH_SESSION_ID")
        return session_arg
    value = current.get("DSH_SESSION_ID")
    if value is not None:
        if not value.strip():
            raise BrowserCLIError("session id is empty; use --session <id> or set DSH_SESSION_ID")
        return value
    if required:
        raise BrowserCLIError("session id is required; use --session <id> or set DSH_SESSION_ID")
    return None


def parse_session_args(argv, env=None, *, required=True):
    """Return (resolved session id, argv); only leading --session is consumed."""
    args = list(argv)
    explicit = None
    while args:
        token = args[0]
        if token == "--session":
            if len(args) < 2:
                raise BrowserCLIError("--session requires an id")
            if explicit is not None:
                raise BrowserCLIError("--session may be specified only once")
            explicit = args[1]
            del args[:2]
        elif token.startswith("--session="):
            if explicit is not None:
                raise BrowserCLIError("--session may be specified only once")
            explicit = token.partition("=")[2]
            del args[0]
        else:
            break
    return resolve_session(explicit, env, required=required), args


def parse_management_args(argv, env=None):
    """Parse --session anywhere among management arguments; returns session,args,explicit."""
    remaining, explicit, index = [], None, 0
    while index < len(argv):
        token = argv[index]
        if token == "--session":
            if index + 1 >= len(argv):
                raise BrowserCLIError("--session requires an id")
            if explicit is not None:
                raise BrowserCLIError("--session may be specified only once")
            explicit = argv[index + 1]
            index += 2
        elif token.startswith("--session="):
            if explicit is not None:
                raise BrowserCLIError("--session may be specified only once")
            explicit = token.partition("=")[2]
            index += 1
        else:
            remaining.append(token)
            index += 1
    return resolve_session(explicit, env, required=False), remaining, explicit is not None


def worker_identity(session_id):
    if not isinstance(session_id, str) or not session_id.strip():
        raise BrowserCLIError("session id is empty; use --session <id> or set DSH_SESSION_ID")
    session_hash = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    worker = session_hash[:32]
    return {
        "worker_id": worker,
        "session_hash": session_hash,
        "container": f"{CONTAINER_PREFIX}{worker}",
        "volume": f"{CONTAINER_PREFIX}{worker}{PROFILE_SUFFIX}",
        "bu_name": f"{DAEMON_PREFIX}{worker}",
    }


def labels_for(identity, image=None):
    labels = {
        LABEL_MANAGED: "1",
        LABEL_NAMESPACE: NAMESPACE,
        LABEL_VERSION: VERSION,
        LABEL_WORKER: identity["worker_id"],
        LABEL_SESSION_SHA256: identity["session_hash"],
        LABEL_SESSION_HASH_ALG: "sha256",
    }
    if image is not None:
        labels[LABEL_IMAGE] = str(image)
    return labels


def verify_owned(labels, identity, image=None):
    """Return true only when every required ownership field is an exact match."""
    if not isinstance(labels, dict):
        return False
    expected = labels_for(identity)
    if not all(labels.get(key) == value for key, value in expected.items()):
        return False
    if image is not None and labels.get(LABEL_IMAGE) != str(image):
        return False
    return True


def _labels_from_inspect(inspect_data):
    if not isinstance(inspect_data, dict):
        return {}
    if isinstance(inspect_data.get("Labels"), dict):
        return inspect_data["Labels"]
    config = inspect_data.get("Config")
    if isinstance(config, dict) and isinstance(config.get("Labels"), dict):
        return config["Labels"]
    return inspect_data


def ports_from_inspect(inspect_json):
    """Return loopback host ports as {view:int, cdp:int}, or None if incomplete."""
    if isinstance(inspect_json, str):
        try:
            inspect_json = json.loads(inspect_json)
        except (TypeError, ValueError):
            return None
    if isinstance(inspect_json, list):
        inspect_json = inspect_json[0] if inspect_json else {}
    if not isinstance(inspect_json, dict):
        return None
    ports = (inspect_json.get("NetworkSettings") or {}).get("Ports") or {}
    output = {}
    for name, internal in (("view", CONTAINER_VIEW_PORT), ("cdp", CONTAINER_CDP_PORT)):
        bindings = ports.get(f"{internal}/tcp")
        if not isinstance(bindings, list):
            return None
        for item in bindings:
            if not isinstance(item, dict) or item.get("HostIp") != "127.0.0.1":
                continue
            try:
                port = int(item.get("HostPort"))
            except (TypeError, ValueError):
                continue
            if 1 <= port <= 65535:
                output[name] = port
                break
        if name not in output:
            return None
    return output


def harness_env(identity, ports, state_root, supplied_env):
    """Return isolated Harness variables for one identity, without filesystem I/O."""
    base = _env_copy(supplied_env)
    root = Path(state_root).expanduser()
    home = root / "harness" / identity["worker_id"]
    runtime = _runtime_dir(identity)
    result = base.copy()
    result.update({
        "BH_HOME": str(home),
        "BH_RUNTIME_DIR": str(runtime),
        "BH_TMP_DIR": str(home / "tmp"),
        "BU_NAME": identity["bu_name"],
        "BH_TAB_MARKER": "0",
    })
    for name in ("BU_CDP_WS", "BU_BROWSER_ID", "BH_REQUIRE_EXISTING_DAEMON", "BU_AUTOSPAWN",
                 "BH_RUNTIME_DIR_SHARED", "BH_TMP_DIR_SHARED"):
        result.pop(name, None)
    port = None
    if isinstance(ports, dict):
        port = ports.get("cdp")
    if port is not None:
        result["BU_CDP_URL"] = f"http://127.0.0.1:{int(port)}"
    else:
        result.pop("BU_CDP_URL", None)
    result.setdefault("BH_RECORD", "0")
    return result


def _runtime_dir(identity):
    # AF_UNIX sun_path is capped at 104 bytes on macOS (including the NUL), and
    # the per-user temp dir is already ~90 bytes long, so keep the runtime base
    # short and private instead of using tempfile.gettempdir().
    base = Path("/tmp") if (os.name == "posix" and Path("/tmp").is_dir()) else Path(tempfile.gettempdir())
    return base / ("bhw-" + str(os.getuid())) / identity["worker_id"]


def _verify_runtime_dir(path):
    try:
        info = Path(path).lstat()
    except OSError as error:
        raise BrowserCLIError("Browser Harness runtime directory is unavailable") from error
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700):
        raise BrowserCLIError("Browser Harness runtime directory must be owned by this user with mode 0700")


def _create_runtime_dir(path):
    path = Path(path)
    created = False
    try:
        path.mkdir(mode=0o700)
        created = True
    except FileExistsError:
        pass
    except OSError as error:
        raise BrowserCLIError("Browser Harness runtime directory could not be created") from error
    if created:
        try:
            os.chmod(path, 0o700)
        except OSError as error:
            raise BrowserCLIError("Browser Harness runtime directory permissions could not be set") from error
    _verify_runtime_dir(path)
    return path


def prepare_worker_state(identity, state_root):
    """Create private state directories and enforce the AF_UNIX path budget."""
    root = _private_dir(state_root)
    for child in ("docker", "locks", "logs"):
        _private_dir(root / child)
    home = _private_dir(root / "harness" / identity["worker_id"])
    _private_dir(home / "tmp")
    runtime = _runtime_dir(identity)
    _create_runtime_dir(runtime.parent)
    _create_runtime_dir(runtime)
    if len(os.fsencode(runtime / "bu.sock")) >= 104:
        raise BrowserCLIError("Browser Harness runtime socket path exceeds the AF_UNIX limit")
    return root


def _http_browser_websocket(cdp_url, timeout=1.0):
    try:
        request = urllib.request.Request(cdp_url.rstrip("/") + "/json/version")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
        ws = payload.get("webSocketDebuggerUrl") if isinstance(payload, dict) else None
        return ws if isinstance(ws, str) else None
    except (OSError, ValueError, TypeError, urllib.error.URLError):
        return None


def browser_id_from_websocket_url(websocket_url):
    """Browser identity from a /json/version webSocketDebuggerUrl, if well formed."""
    if not isinstance(websocket_url, str):
        return None
    try:
        parsed = urllib.parse.urlparse(websocket_url)
    except ValueError:
        return None
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 3 or parts[:2] != ["devtools", "browser"]:
        return None
    return parts[2] or None


def browser_instance_identity(cdp_url, timeout=2.0):
    """Stable identity of the Chromium instance behind a CDP HTTP endpoint.

    /json/version's webSocketDebuggerUrl carries a browser id unique to one
    Chromium process group, so a reused host port or a restarted Chromium is
    distinguishable. Returns None when the endpoint is unreachable.
    """
    return browser_id_from_websocket_url(_http_browser_websocket(cdp_url, timeout=timeout))


def _ipc_request(identity, request, timeout=1.0):
    """One JSON request to this worker's Harness daemon over its runtime socket."""
    path = _runtime_dir(identity) / "bu.sock"
    client = None
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(timeout)
        client.connect(str(path))
        client.sendall((json.dumps(request) + "\n").encode("utf-8"))
        response = bytearray()
        while not response.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            response.extend(chunk)
        data = json.loads(response or b"{}")
    except (OSError, TypeError, ValueError):
        return None
    finally:
        if client is not None:
            client.close()
    if not isinstance(data, dict) or data.get("error"):
        return None
    return data


def _ipc_browser_target_id(identity, state_root=None, timeout=1.0):
    """The browser-level target id reported by this worker's daemon, if live.

    Chromium mints a new id per CDP connection, so this proves the daemon is
    attached to *a* browser, not which one; browser_instance_identity() does.
    """
    data = _ipc_request(identity, {"method": "Target.getTargetInfo", "params": {}, "session_id": None}, timeout)
    result = data.get("result") if isinstance(data, dict) else None
    info = result.get("targetInfo") if isinstance(result, dict) else None
    target_id = info.get("targetId") if isinstance(info, dict) else None
    return target_id if isinstance(target_id, str) and target_id else None


def _call_query_callback(callback, identity, cdp_url):
    if callback is None:
        return None
    try:
        params = list(inspect.signature(callback).parameters.values())
        positional = [p for p in params if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        has_var = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params)
    except (TypeError, ValueError):
        positional, has_var = [], True
    if has_var or len(positional) >= 3:
        return callback(identity["bu_name"], "Target.getTargetInfo", {})
    if len(positional) == 2:
        return callback(identity, cdp_url)
    if len(positional) == 1:
        name = positional[0].name.lower()
        return callback(identity["bu_name"] if "name" in name or "daemon" in name else identity)
    return callback()


def _call_reload_callback(callback, identity, cdp_url):
    if callback is None:
        return None
    try:
        params = list(inspect.signature(callback).parameters.values())
        positional = [p for p in params if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        has_var = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params)
    except (TypeError, ValueError):
        positional, has_var = [], True
    if has_var or len(positional) >= 2:
        return callback(identity, cdp_url)
    if len(positional) == 1:
        name = positional[0].name.lower()
        return callback(identity["bu_name"] if "name" in name or "daemon" in name else identity)
    return callback()


def _target_id_from_query(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("targetId"), str):
            return value["targetId"]
        result = value.get("result")
        info = result.get("targetInfo") if isinstance(result, dict) else value.get("targetInfo")
        target_id = info.get("targetId") if isinstance(info, dict) else None
        return target_id if isinstance(target_id, str) else None
    return None


def verify_daemon_binding(identity, cdp_url, browser_target_id=None, query=None, reload=None, *, state_root=None):
    """Verify named daemon target id equals Chromium's /json/version identity.

    query and reload are injectable callbacks. The preferred callback forms are
    query(bu_name, method, params), returning a target-id string or an IPC dict
    with result.targetInfo.targetId (also targetInfo.targetId), and reload(bu_name).
    On a mismatch, reload is called once and query is repeated. Raises BrowserCLIError
    if the result is unprovable.
    """
    expected = browser_target_id
    if callable(expected):
        expected = expected(cdp_url)
    if expected is None:
        expected = browser_instance_identity(cdp_url)
    if not expected:
        raise BrowserCLIError("Chromium browser identity could not be read; refusing to execute")

    def read_target():
        if query is None:
            return _ipc_browser_target_id(identity, None)
        return _target_id_from_query(_call_query_callback(query, identity, cdp_url))

    actual = read_target()
    if actual != expected and reload is not None:
        _call_reload_callback(reload, identity, cdp_url)
        actual = read_target()
    if actual != expected:
        raise BrowserCLIError("Browser Harness daemon binding could not be verified; refusing to execute")
    return True


def daemon_binding_state(identity, cdp_url, supplied_env=None, *, state_root=None):
    """Read-only daemon liveness and binding for status/list output."""
    alive = _ipc_browser_target_id(identity, None) is not None
    bound = _daemon_bound(identity, cdp_url, None, None) if alive else False
    return {"daemon_alive": alive, "daemon_bound": bound, "daemon_verified": bound}


def file_lock(path):
    """Context manager for a private, process-shared exclusive flock."""
    @contextmanager
    def locked():
        path_value = Path(path)
        _private_dir(path_value.parent)
        fd = os.open(path_value, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.chmod(path_value, 0o600)
            with os.fdopen(fd, "a+") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except BaseException:
            raise
    return locked()

def configure_engine(env=None, runner=None, *, start=False, platform_name=None):
    current = _env_copy(env) if env is None else env
    runner = RUNNER if runner is None else runner
    platform_name = sys.platform if platform_name is None else platform_name
    current["DOCKER_CONFIG"] = str(state_root(current) / "docker")
    current.pop("DOCKER_CONTEXT", None)
    if start:
        _private_dir(Path(current["DOCKER_CONFIG"]))
    if platform_name == "darwin":
        status = _invoke(runner, ["colima", "--profile", ENGINE_PROFILE, "status", "--json"], current, capture=True)
        socket_path = None
        if _returncode(status) == 0:
            try:
                socket_path = json.loads(_stdout(status)).get("docker_socket")
            except (ValueError, AttributeError):
                socket_path = None
        if not socket_path and start:
            state = _private_dir(state_root(current))
            with file_lock(state / "locks" / "engine.lock"):
                started = _invoke(runner, ["colima", "--profile", ENGINE_PROFILE, "start", "--activate=false", "--cpu", "2", "--memory", "4", "--disk", "20"], current, capture=True)
                if _returncode(started):
                    return False
            status = _invoke(runner, ["colima", "--profile", ENGINE_PROFILE, "status", "--json"], current, capture=True)
            try:
                socket_path = json.loads(_stdout(status)).get("docker_socket")
            except (ValueError, AttributeError):
                socket_path = None
        if not socket_path:
            return False
        current["DOCKER_HOST"] = socket_path
    else:
        current.pop("DOCKER_HOST", None)
    result = _invoke(runner, ["docker", "info", "--format", "{{.OSType}}"], current, capture=True)
    return _returncode(result) == 0



def _inspect_result(result, what):
    if _returncode(result):
        return None
    try:
        data = json.loads(_stdout(result))
    except (TypeError, ValueError) as error:
        raise BrowserCLIError("Docker returned invalid " + what + " inspect data") from error
    if isinstance(data, list):
        return data
    return data if isinstance(data, dict) else None


def _docker(runner, env, *args):
    return _invoke(runner, ["docker", *args], env, capture=True)


def inspect_container(name, env=None, runner=None):
    current = _env_copy(env)
    result = _docker(RUNNER if runner is None else runner, current, "container", "inspect", name)
    data = _inspect_result(result, "container")
    return data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)


def inspect_volume(name, env=None, runner=None):
    current = _env_copy(env)
    result = _docker(RUNNER if runner is None else runner, current, "volume", "inspect", name)
    data = _inspect_result(result, "volume")
    return data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)


def _assert_owned(resource, identity, kind):
    if resource is not None and not verify_owned(_labels_from_inspect(resource), identity):
        raise BrowserCLIError("refusing to touch " + kind + ": ownership labels do not match this worker")


def _check(result, description):
    if _returncode(result):
        raise BrowserCLIError(description + " failed")
    return result


def _ensure_image(image, source, env, runner):
    root = _private_dir(state_root(env))
    with file_lock(root / "locks" / "engine.lock"):
        existing = _docker(runner, env, "image", "inspect", image)
        if _returncode(existing):
            _check(_docker(runner, env, "build", "--tag", image, source), "Docker image build")


def _ensure_volume(identity, env, runner):
    volume = inspect_volume(identity["volume"], env, runner)
    _assert_owned(volume, identity, "profile volume")
    if volume is not None:
        return volume
    args = ["volume", "create", "--name", identity["volume"]]
    for key, value in labels_for(identity).items():
        args.extend(["--label", key + "=" + value])
    _check(_docker(runner, env, *args), "Docker profile volume creation")
    volume = inspect_volume(identity["volume"], env, runner)
    if volume is None or not verify_owned(_labels_from_inspect(volume), identity):
        raise BrowserCLIError("Docker did not create the expected profile volume")
    return volume


def _running(container):
    return bool(container and (container.get("State") or {}).get("Running"))


def _container_image(container):
    return _labels_from_inspect(container).get(LABEL_IMAGE) if container else None


def _remove_container(name, env, runner):
    _check(_docker(runner, env, "container", "rm", "--force", name), "Docker container removal")


def _http_ready(url, timeout=1.0):
    try:
        target = url.split("?", 1)[0]
        with urllib.request.urlopen(target, timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _worker_ready(cdp_url, view_url):
    return bool(_http_browser_websocket(cdp_url)) and _http_ready(view_url)


def forward_container(identity):
    return FORWARD_PREFIX + identity["worker_id"]


def _forward_args(identity, ports):
    """Sidecar that relays each port from the worker's loopback to the host loopback.

    Docker refuses to publish ports on a container that shares another
    container's network namespace, so the sidecar only listens inside the
    worker's netns; the worker's own Colima forwarder already publishes those
    ports on the host's 127.0.0.1.
    """
    args = [
        "run", "--detach", "--name", forward_container(identity), "--init",
        "--restart", "unless-stopped", "--stop-timeout", "10",
        # Sharing the worker's network namespace also shares its /etc/hosts, so
        # host.docker.internal resolves exactly as it does inside the worker.
        "--network", "container:" + identity["container"],
    ]
    for key, value in labels_for(identity).items():
        args.extend(["--label", key + "=" + value])
    args.extend(["--env", "BHW_FORWARD_PORTS=" + " ".join(str(port) for port in ports)])
    args.extend(["--entrypoint", "/bin/sh", FORWARD_IMAGE, "-c", FORWARD_SCRIPT])
    return args


def _remove_forwarder(identity, env, runner):
    existing = inspect_container(forward_container(identity), env, runner)
    _assert_owned(existing, identity, "port forwarder")
    if existing is not None:
        _check(_docker(runner, env, "container", "rm", "--force", forward_container(identity)),
               "Docker forwarder removal")
    return existing is not None


def _forwarder_ports(identity, env, runner):
    """Ports this forwarder currently relays, from its recorded command, or None."""
    forwarder = inspect_container(forward_container(identity), env, runner)
    _assert_owned(forwarder, identity, "port forwarder")
    if forwarder is None:
        return None
    if not _running(forwarder):
        return []
    raw = ((forwarder.get("Config") or {}).get("Env") or [])
    for entry in raw:
        if isinstance(entry, str) and entry.startswith("BHW_FORWARD_PORTS="):
            return _normalize_ports(entry.split("=", 1)[1].split())
    return []


def _ensure_forwarder(identity, ports, env, runner, *, timeout=30.0):
    """Create or reconcile this worker's loopback relay; return the relayed ports."""
    wanted = _normalize_ports(ports)
    existing = _forwarder_ports(identity, env, runner)
    if existing is not None and existing == wanted:
        return wanted
    if existing is not None:
        _remove_forwarder(identity, env, runner)
    _check(_docker(runner, env, "image", "inspect", FORWARD_IMAGE),
           "Docker forwarder image is unavailable; pull it once with docker pull " + FORWARD_IMAGE)
    _check(_docker(runner, env, *_forward_args(identity, wanted)), "Docker forwarder creation")
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        forwarder = inspect_container(forward_container(identity), env, runner)
        _assert_owned(forwarder, identity, "port forwarder")
        if forwarder is not None:
            if not _running(forwarder):
                raise BrowserCLIError("the host port forwarder exited immediately")
            return wanted
        if time.monotonic() >= deadline:
            raise BrowserCLIError("the host port forwarder did not start")
        time.sleep(0.2)


def start_forwarding(session_id, ports, env=None, runner=None):
    """Forward host 127.0.0.1:<port> into this worker for every listed port."""
    current = _env_copy(env)
    runner = RUNNER if runner is None else runner
    identity = worker_identity(session_id)
    wanted = _normalize_ports(ports)
    if not wanted:
        raise BrowserCLIError("forward requires at least one port")
    state = prepare_worker_state(identity, state_root(current))
    with file_lock(state / "locks" / (identity["worker_id"] + ".lock")):
        docker_env = current.copy()
        if not configure_engine(docker_env, runner, start=False):
            raise BrowserCLIError("Docker is unavailable; unable to forward host ports")
        container = inspect_container(identity["container"], docker_env, runner)
        _assert_owned(container, identity, "container")
        if not _running(container):
            raise BrowserCLIError("this worker is not running; run browser start first")
        published = _ensure_forwarder(identity, wanted, docker_env, runner)
        return {"worker_id": identity["worker_id"], "forwarded": published}


def stop_forwarding(session_id, env=None, runner=None):
    current = _env_copy(env)
    runner = RUNNER if runner is None else runner
    identity = worker_identity(session_id)
    state = prepare_worker_state(identity, state_root(current))
    with file_lock(state / "locks" / (identity["worker_id"] + ".lock")):
        docker_env = current.copy()
        if not configure_engine(docker_env, runner, start=False):
            return {"worker_id": identity["worker_id"], "forwarded": [], "removed": False}
        removed = _remove_forwarder(identity, docker_env, runner)
        return {"worker_id": identity["worker_id"], "forwarded": [], "removed": removed}


def _normalize_ports(values):
    output = []
    for value in values:
        text = str(value).strip()
        if not text.isdigit() or not 1 <= int(text) <= 65535:
            raise BrowserCLIError("forward requires TCP ports between 1 and 65535")
        port = int(text)
        if port not in output:
            output.append(port)
    return output


def ensure_worker(session_id, env=None, runner=None, *, timeout=45.0):
    """Ensure this session's owned worker and profile; return freshly inspected ports."""
    current = _env_copy(env)
    runner = RUNNER if runner is None else runner
    identity = worker_identity(session_id)
    root = prepare_worker_state(identity, state_root(current))
    image = current.get("BROWSER_DOCKER_IMAGE") or IMAGE
    source = current.get("BROWSER_DOCKER_SOURCE") or SOURCE
    if not image or not source:
        raise BrowserCLIError("browser image configuration is missing")
    lock_path = root / "locks" / (identity["worker_id"] + ".lock")
    with file_lock(lock_path):
        docker_env = current.copy()
        if not configure_engine(docker_env, runner, start=True):
            raise BrowserCLIError("Docker/Colima is unavailable; unable to start this browser worker")
        container = inspect_container(identity["container"], docker_env, runner)
        _assert_owned(container, identity, "container")
        old_ports = ports_from_inspect(container) if container else None
        _ensure_image(image, source, docker_env, runner)
        _ensure_volume(identity, docker_env, runner)
        changed = False
        if container is not None and _container_image(container) != image:
            _remove_container(identity["container"], docker_env, runner)
            container = None
            changed = True
        if container is None:
            args = [
                "run", "--detach", "--name", identity["container"], "--init",
                "--restart", "unless-stopped", "--shm-size", "1g", "--stop-timeout", "30",
                "--publish", "127.0.0.1::6080", "--publish", "127.0.0.1::9223",
                "--volume", identity["volume"] + ":/profile",
            ]
            for key, value in labels_for(identity, image).items():
                args.extend(["--label", key + "=" + value])
            args.append(image)
            _check(_docker(runner, docker_env, *args), "Docker worker creation")
            changed = True
            container = inspect_container(identity["container"], docker_env, runner)
            if container is None:
                raise BrowserCLIError("Docker did not create the expected browser worker")
            _assert_owned(container, identity, "container")
        elif not _running(container):
            _check(_docker(runner, docker_env, "container", "start", identity["container"]), "Docker worker start")
            changed = True

        deadline = time.monotonic() + max(0.0, timeout)
        observed_ports = None
        while True:
            # Host ports are always obtained from inspect, never guessed or cached.
            container = inspect_container(identity["container"], docker_env, runner)
            if container is None:
                raise BrowserCLIError("browser worker disappeared during startup")
            _assert_owned(container, identity, "container")
            if _running(container):
                ports = ports_from_inspect(container)
                if ports:
                    if old_ports and old_ports != ports:
                        changed = True
                    observed_ports = ports
                    cdp_url = "http://127.0.0.1:" + str(ports["cdp"])
                    view_url = "http://127.0.0.1:" + str(ports["view"]) + VIEW_PATH
                    if _worker_ready(cdp_url, view_url):
                        return {
                            **identity, "ports": ports, "cdp": cdp_url, "view": view_url,
                            "changed": changed, "container_inspect": container,
                        }
            if time.monotonic() >= deadline:
                break
            time.sleep(0.25)
        if observed_ports:
            raise BrowserCLIError("Chromium or noVNC did not become ready within the startup timeout")
        raise BrowserCLIError("Docker did not publish the browser worker ports")


def _harness_binary(env):
    return env.get("BROWSER_HARNESS_BIN") or HARNESS


def touch_worker(identity, state):
    """Record that this worker was just used, for the idle reaper."""
    try:
        home = Path(state) / "harness" / identity["worker_id"]
        home.mkdir(parents=True, exist_ok=True)
        (home / "last_use").write_text(str(int(time.time())))
    except OSError:
        pass


def _harness_log_tail(env, lines=5):
    """Last daemon log lines for diagnostics; the log holds no page content."""
    try:
        path = Path(env["BH_TMP_DIR"]) / ("bu-" + env["BU_NAME"] + ".log")
        if not path.is_file():
            path = Path(env["BH_TMP_DIR"]) / "bu.log"
        text = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except (KeyError, OSError):
        return ""
    return "\n".join(text[-lines:])


def _harness_call(args, env, runner, *, input_data=None, timeout=30):
    binary = _harness_binary(env)
    result = _invoke(runner, [binary, *args], env, capture=True, input_data=input_data, timeout=timeout)
    if _returncode(result):
        detail = (getattr(result, "stderr", "") or "").strip().splitlines()
        message = "Browser Harness command failed"
        if detail:
            message += ": " + detail[-1][:300]
        log = _harness_log_tail(env)
        if log:
            message += "\n" + log
        raise BrowserCLIError(message)
    return result


def _reload_and_bootstrap(identity, env, runner):
    # BU_NAME in env scopes this to exactly one Harness daemon.
    _harness_call(["--reload"], env, runner)
    # This is a fixed literal script, never the user's stdin.
    _harness_call([], env, runner, input_data="pass\n")
    # The daemon binds its IPC socket in BH_RUNTIME_DIR; prove it listened there
    # so a later exec cannot fall back to a different runtime directory.
    sock = Path(env["BH_RUNTIME_DIR"]) / "bu.sock"
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if sock.exists() and _ipc_browser_target_id(identity, None) is not None:
            return
        time.sleep(0.2)
    raise BrowserCLIError("Browser Harness daemon did not publish its IPC socket")


def _daemon_bound(identity, cdp_url, env, runner, timeout=2.0):
    """True only when this worker's daemon is attached to this worker's Chromium.

    Chromium mints a fresh browser target id for every CDP connection, so the
    daemon's browser-level target id cannot be compared with /json/version.
    Instead, ask the daemon for the browser context id: it belongs to the
    profile and is stable for the life of one Chromium process group, so a
    daemon left attached to a previous Chromium (or to another worker that
    reused the same host port) reports a different one.
    """
    expected = browser_instance_identity(cdp_url)
    if not expected:
        return False
    response = _ipc_request(identity, {"method": "Target.getBrowserContexts", "params": {}}, timeout)
    result = response.get("result") if isinstance(response, dict) else None
    context = result.get("defaultBrowserContextId") if isinstance(result, dict) else None
    if not isinstance(context, str) or not context:
        return False
    direct = _browser_default_context(cdp_url)
    return bool(direct) and direct == context


def _browser_default_context(cdp_url, timeout=2.0):
    """Default browser context id of the Chromium behind a CDP HTTP endpoint."""
    websocket = _http_browser_websocket(cdp_url, timeout=timeout)
    if not websocket:
        return None
    parsed = urllib.parse.urlparse(websocket)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port
    if not port:
        return None
    try:
        client = socket.create_connection((host, port), timeout=timeout)
    except OSError:
        return None
    try:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        client.sendall(
            (
                f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
        )
        if b" 101 " not in client.recv(4096).split(b"\r\n", 1)[0]:
            return None
        payload = json.dumps({"id": 1, "method": "Target.getBrowserContexts", "params": {}}).encode()
        mask = os.urandom(4)
        header = bytes([0x81])
        length = len(payload)
        if length < 126:
            header += bytes([0x80 | length])
        else:
            header += bytes([0x80 | 126]) + length.to_bytes(2, "big")
        client.sendall(header + mask + bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload)))
        while True:
            head = client.recv(2)
            if len(head) < 2:
                return None
            size = head[1] & 0x7F
            if size == 126:
                size = int.from_bytes(client.recv(2), "big")
            elif size == 127:
                size = int.from_bytes(client.recv(8), "big")
            body = b""
            while len(body) < size:
                chunk = client.recv(size - len(body))
                if not chunk:
                    return None
                body += chunk
            message = json.loads(body)
            if message.get("id") != 1:
                continue
            result = message.get("result") or {}
            context = result.get("defaultBrowserContextId")
            return context if isinstance(context, str) and context else None
    except (OSError, ValueError):
        return None
    finally:
        client.close()


def ensure_daemon(identity, cdp_url, env, runner, *, force_reload=False, timeout=12.0):
    """Bind this worker's daemon to its current CDP endpoint, or fail closed.

    Only this worker's daemon (BU_NAME) is ever reloaded. A daemon that cannot
    be proven to reach this worker's Chromium is stopped and started again on
    the current endpoint; if that still cannot be proven, raise.
    """
    prepare_worker_state(identity, state_root(env))
    reload_callback = lambda bu_name: _reload_and_bootstrap(identity, env, runner)
    if force_reload:
        reload_callback(identity["bu_name"])
    if _daemon_bound(identity, cdp_url, env, runner):
        return True
    reload_callback(identity["bu_name"])
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        if _daemon_bound(identity, cdp_url, env, runner):
            return True
        if time.monotonic() >= deadline:
            raise BrowserCLIError(
                "Browser Harness daemon is not bound to this worker's Chromium; refusing to execute"
            )
        time.sleep(0.2)


def _container_image_label(container):
    return _labels_from_inspect(container).get(LABEL_IMAGE) if container else None


def _status_for(identity, container, supplied_env, state):
    running = _running(container)
    ports = ports_from_inspect(container) if running else None
    cdp = f"http://127.0.0.1:{ports['cdp']}" if ports else None
    view = f"http://127.0.0.1:{ports['view']}{VIEW_PATH}" if ports else None
    ready = bool(ports and _worker_ready(cdp, view))
    if ports:
        daemon = daemon_binding_state(identity, cdp, supplied_env, state_root=state)
    else:
        daemon = {"daemon_alive": False, "daemon_bound": False, "daemon_verified": False}
    return {
        "worker_id": identity["worker_id"], "session_hash": identity["session_hash"],
        "container": identity["container"],
        "running": running, "ready": ready, "cdp": cdp, "view": view, **daemon,
    }


def worker_status(session_id, env=None, runner=None):
    current = _env_copy(env)
    runner = RUNNER if runner is None else runner
    identity = worker_identity(session_id)
    state = state_root(current)
    docker_env = current.copy()
    if not configure_engine(docker_env, runner, start=False):
        return {
            "worker_id": identity["worker_id"], "container": identity["container"],
            "running": False, "ready": False, "cdp": None, "view": None,
            "daemon_alive": False, "daemon_bound": False, "daemon_verified": False,
        }
    container = inspect_container(identity["container"], docker_env, runner)
    _assert_owned(container, identity, "container")
    return _status_for(identity, container, current, state)


def list_workers(env=None, runner=None):
    current = _env_copy(env)
    runner = RUNNER if runner is None else runner
    state = state_root(current)
    docker_env = current.copy()
    if not configure_engine(docker_env, runner, start=False):
        return []
    found = _docker(runner, docker_env, "container", "ls", "--all", "--quiet",
                    "--filter", f"label={LABEL_MANAGED}=1")
    if _returncode(found):
        return []
    ids = [line.strip() for line in _stdout(found).splitlines() if line.strip()]
    if not ids:
        return []
    result = _docker(runner, docker_env, "container", "inspect", *ids)
    if _returncode(result):
        return []
    try:
        containers = json.loads(_stdout(result))
    except (TypeError, ValueError):
        return []
    if not isinstance(containers, list):
        return []
    records = []
    for container in containers:
        if not isinstance(container, dict):
            continue
        labels = _labels_from_inspect(container)
        name = str(container.get("Name", "")).lstrip("/")
        wid = labels.get(LABEL_WORKER, "")
        full = labels.get(LABEL_SESSION_SHA256, "")
        if (labels.get(LABEL_MANAGED) != "1" or labels.get(LABEL_NAMESPACE) != NAMESPACE
                or labels.get(LABEL_VERSION) != VERSION or labels.get(LABEL_SESSION_HASH_ALG) != "sha256"
                or len(wid) != 32 or len(full) != 64 or full[:32] != wid
                or any(char not in "0123456789abcdef" for char in wid + full)
                or name != f"{CONTAINER_PREFIX}{wid}"):
            continue
        identity = {
            "worker_id": wid, "session_hash": full, "container": name,
            "volume": f"{CONTAINER_PREFIX}{wid}{PROFILE_SUFFIX}", "bu_name": f"{DAEMON_PREFIX}{wid}",
        }
        records.append(_status_for(identity, container, current, state))
    return records


def idle_timeout(env=None):
    """Configured idle timeout in seconds; 0 disables automatic reaping."""
    current = _env_copy(env)
    raw = current.get("BROWSER_IDLE_TIMEOUT", "")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_IDLE_TIMEOUT
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_IDLE_TIMEOUT
    return value if value >= 0 else DEFAULT_IDLE_TIMEOUT


def _container_started_at(container):
    if not isinstance(container, dict):
        return None
    state = container.get("State") or {}
    value = state.get("StartedAt") or container.get("Created")
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Docker reports nanosecond precision; trim to microseconds for fromisoformat.
    if "." in text:
        head, _, tail = text.partition(".")
        offset = ""
        for index, char in enumerate(tail):
            if char in "+-":
                offset, tail = tail[index:], tail[:index]
                break
        text = head + "." + (tail + "000000")[:6] + offset
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _idle_seconds(identity, container, state, now=None):
    """Seconds since this worker was last used, or None when it cannot be known."""
    now = time.time() if now is None else now
    started = _container_started_at(container)
    candidates = [started.timestamp()] if started is not None else []
    for path in (
        state / "harness" / identity["worker_id"] / "last_use",
        state / "harness" / identity["worker_id"],
        _runtime_dir(identity) / "bu.sock",
    ):
        try:
            candidates.append(path.stat().st_mtime)
        except OSError:
            continue
    if not candidates:
        return None
    return max(0.0, now - max(candidates))


def reap_idle_workers(env=None, runner=None, *, timeout=None, dry_run=False):
    """Stop workers untouched for longer than the idle timeout; keep their profiles."""
    current = _env_copy(env)
    runner = RUNNER if runner is None else runner
    state = state_root(current)
    limit = idle_timeout(current) if timeout is None else int(timeout)
    records = list_workers(current, runner)
    if limit <= 0:
        return {"timeout": limit, "reaped": [], "skipped": records}
    reaped, skipped = [], []
    for record in records:
        if not record.get("running"):
            skipped.append(record)
            continue
        identity = {
            "worker_id": record["worker_id"],
            "session_hash": record["session_hash"],
            "container": record["container"],
            "volume": record["container"] + PROFILE_SUFFIX,
            "bu_name": DAEMON_PREFIX + record["worker_id"],
        }
        container = inspect_container(identity["container"], current, runner)
        if container is None:
            skipped.append(record)
            continue
        idle = _idle_seconds(identity, container, state)
        if idle is None or idle < limit:
            skipped.append(record)
            continue
        if not dry_run:
            _stop_worker_identity(identity, current, runner)
        reaped.append({"worker_id": record["worker_id"], "container": record["container"],
                       "idle_seconds": int(idle)})
    return {"timeout": limit, "reaped": reaped, "skipped": skipped}


def maybe_reap_idle(env=None, runner=None):
    """Best-effort background reap used before a worker is started; never fails a start."""
    current = _env_copy(env)
    runner = RUNNER if runner is None else runner
    if idle_timeout(current) <= 0:
        return
    state = state_root(current)
    stamp = state / "locks" / "reap.stamp"
    now = time.time()
    try:
        if now - stamp.stat().st_mtime < 60:
            return
    except OSError:
        pass
    try:
        _private_dir(state / "locks")
        stamp.write_text(str(int(now)))
    except OSError:
        return
    try:
        reap_idle_workers(current, runner)
    except (BrowserCLIError, OSError):
        pass


def _existing_worker(session_id, env, runner):
    identity = worker_identity(session_id)
    docker_env = env.copy()
    if not configure_engine(docker_env, runner, start=False):
        raise BrowserCLIError("Docker is unavailable; unable to inspect this worker")
    container = inspect_container(identity["container"], docker_env, runner)
    _assert_owned(container, identity, "container")
    return identity, container, docker_env


def view_worker(session_id, env=None, runner=None, *, open_view=False):
    current = _env_copy(env)
    runner = RUNNER if runner is None else runner
    identity = worker_identity(session_id)
    docker_env = current.copy()
    if not configure_engine(docker_env, runner, start=False):
        return {"worker_id": identity["worker_id"], "running": False, "view": None}
    container = inspect_container(identity["container"], docker_env, runner)
    _assert_owned(container, identity, "container")
    if not _running(container):
        raise BrowserCLIError("this worker is not running; run browser start first")
    ports = ports_from_inspect(container)
    if not ports:
        raise BrowserCLIError("Docker has not published this worker's ports")
    url = f"http://127.0.0.1:{ports['view']}{VIEW_PATH}"
    if open_view:
        opener = ["open", url] if sys.platform == "darwin" else ["xdg-open", url]
        _check(_invoke(runner, opener, docker_env, capture=True), "opening noVNC")
    return {"worker_id": identity["worker_id"], "running": True, "view": url}


def stop_worker(session_id, env=None, runner=None, *, purge_profile=False):
    return _stop_worker_identity(worker_identity(session_id), env, runner, purge_profile=purge_profile)


def _stop_worker_identity(identity, env=None, runner=None, *, purge_profile=False):
    current = _env_copy(env)
    runner = RUNNER if runner is None else runner
    state = prepare_worker_state(identity, state_root(current))
    lock = state / "locks" / (identity["worker_id"] + ".lock")
    with file_lock(lock):
        harness_environment = harness_env(identity, None, state, current)
        docker_env = current.copy()
        if not configure_engine(docker_env, runner, start=False):
            raise BrowserCLIError("Docker is unavailable; unable to stop this worker")
        container = inspect_container(identity["container"], docker_env, runner)
        _assert_owned(container, identity, "container")
        profile = inspect_volume(identity["volume"], docker_env, runner)
        _assert_owned(profile, identity, "profile volume")
        if purge_profile and profile is None and container is not None:
            raise BrowserCLIError("profile volume does not exist; refusing to purge it")
        if (_runtime_dir(identity) / "bu.sock").exists():
            _harness_call(["--reload"], harness_environment, runner)
        _remove_forwarder(identity, docker_env, runner)
        if container is not None:
            _check(_docker(runner, docker_env, "container", "rm", "--force", identity["container"]), "Docker container removal")
        if purge_profile and profile is not None:
            _check(_docker(runner, docker_env, "volume", "rm", identity["volume"]), "Docker profile removal")
        return {"worker_id": identity["worker_id"], "removed": True,
                "profile_purged": bool(purge_profile and profile is not None)}


MANAGER_HELP = """browser [--session ID] [start|status|view|list|stop|remove|reap|forward|skill|help]

Management commands:
  start                 Start or recover this session's isolated worker
  status                Show this session's worker without starting it
  view [--open]         Print or open this worker's noVNC URL
  list                  List managed browser workers
  stop                  Remove this worker container; preserve profile
  remove --session ID [--purge-profile]
                        Remove worker; purge profile only when requested
  reap [--timeout SEC] [--dry-run]
                        Stop workers idle longer than BROWSER_IDLE_TIMEOUT
                        (default 3600s; 0 disables); profiles are preserved
  forward PORT...       Forward host 127.0.0.1:PORT into this worker
  unforward             Stop forwarding host ports into this worker
  skill                 Print the Browser Harness skill text
  help, -h, --help      Show this manager help

With no harness arguments, Browser Harness receives stdin unchanged.
"""


def _print_json(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _exec_harness(binary, argv, env):
    os.environ.clear()
    os.environ.update(env)
    os.execv(binary, [binary, *argv])


def _management(command, args, current, runner, *, leading_explicit=False):
    session, remaining, explicit = parse_management_args(args, current)
    explicit = explicit or leading_explicit
    if command in {"help", "-h", "--help"}:
        if remaining:
            raise BrowserCLIError("manager help does not accept arguments")
        print(MANAGER_HELP, end="")
        return 0
    if command == "skill":
        if remaining:
            raise BrowserCLIError("skill does not accept arguments")
        skill_value = current.get("BROWSER_SKILL_PATH") or SKILL
        if not skill_value or not Path(skill_value).is_file():
            raise BrowserCLIError("Browser skill file is unavailable")
        try:
            sys.stdout.write(Path(skill_value).read_text())
        except OSError as error:
            raise BrowserCLIError("Browser skill file is unavailable") from error
        return 0
    if command == "list":
        if remaining:
            raise BrowserCLIError("list does not accept arguments")
        records = list_workers(current, runner)
        if session is not None:
            wanted = worker_identity(session)["worker_id"]
            records = [item for item in records if item["worker_id"] == wanted]
        _print_json(records)
        return 0
    if command == "reap":
        timeout = None
        dry_run = False
        index = 0
        while index < len(remaining):
            value = remaining[index]
            if value == "--dry-run":
                dry_run = True
                index += 1
            elif value == "--timeout" and index + 1 < len(remaining):
                try:
                    timeout = int(remaining[index + 1])
                except (TypeError, ValueError):
                    raise BrowserCLIError("reap --timeout requires whole seconds")
                index += 2
            elif value.startswith("--timeout="):
                try:
                    timeout = int(value.split("=", 1)[1])
                except (TypeError, ValueError):
                    raise BrowserCLIError("reap --timeout requires whole seconds")
                index += 1
            else:
                raise BrowserCLIError("reap accepts only --timeout SEC and --dry-run")
        _print_json(reap_idle_workers(current, runner, timeout=timeout, dry_run=dry_run))
        return 0
    if command in FORWARD_COMMANDS:
        if session is None:
            raise BrowserCLIError("session id is required; use --session <id> or set DSH_SESSION_ID")
        if command == "unforward":
            if remaining:
                raise BrowserCLIError("unforward does not accept arguments")
            _print_json(stop_forwarding(session, current, runner))
            return 0
        if not remaining:
            raise BrowserCLIError("forward requires at least one port")
        _print_json(start_forwarding(session, remaining, current, runner))
        return 0
    if command == "remove" and not explicit:
        raise BrowserCLIError("remove requires an explicit --session <id>")
    if session is None:
        raise BrowserCLIError("session id is required; use --session <id> or set DSH_SESSION_ID")
    if command == "start":
        if remaining:
            raise BrowserCLIError("start does not accept extra arguments")
        maybe_reap_idle(current, runner)
        worker = ensure_worker(session, current, runner)
        environment = harness_env(worker, worker["ports"], state_root(current), current)
        ensure_daemon(worker, worker["cdp"], environment, runner, force_reload=worker["changed"])
        _print_json({"worker_id": worker["worker_id"], "cdp": worker["cdp"],
                     "view": worker["view"]})
        return 0
    if command == "status":
        if remaining:
            raise BrowserCLIError("status does not accept extra arguments")
        _print_json(worker_status(session, current, runner))
        return 0
    if command == "view":
        if any(value != "--open" for value in remaining) or remaining.count("--open") > 1:
            raise BrowserCLIError("view accepts only --open")
        _print_json(view_worker(session, current, runner, open_view="--open" in remaining))
        return 0
    if command == "stop":
        if remaining:
            raise BrowserCLIError("stop does not accept extra arguments")
        _print_json(stop_worker(session, current, runner))
        return 0
    if command == "remove":
        if any(value != "--purge-profile" for value in remaining) or remaining.count("--purge-profile") > 1:
            raise BrowserCLIError("remove accepts only --purge-profile")
        _print_json(stop_worker(session, current, runner, purge_profile="--purge-profile" in remaining))
        return 0
    raise BrowserCLIError("unknown browser manager command")


def _passthrough(session, argv, current, runner, do_exec):
    identity = worker_identity(session)
    state = state_root(current)
    touch_worker(identity, state)
    ports = None
    # Harness commands that inspect or reload a worker use currently published
    # ports when available, but never start Docker containers. --reload needs
    # no endpoint: it only stops this worker's daemon.
    if argv and argv[0] != "--reload":
        try:
            identity_found, container, docker_env = _existing_worker(session, current, runner)
            if _running(container):
                ports = ports_from_inspect(container)
        except BrowserCLIError:
            ports = None
    environment = harness_env(identity, ports, state, current)
    binary = _harness_binary(environment)
    if do_exec:
        _exec_harness(binary, argv, environment)
    result = _invoke(runner, [binary, *argv], environment, capture=False)
    return _returncode(result)


def main(argv=None, env=None, runner=None):
    """CLI entrypoint. Read sys.argv by default; passthrough uses os.execv."""
    do_exec = runner is None
    runner = RUNNER if runner is None else runner
    current = _env_copy(env)
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        # --session is recognized only at the front before harness passthrough.
        leading_explicit = bool(args and (args[0] == "--session" or args[0].startswith("--session=")))
        leading_session, remainder = parse_session_args(args, current, required=False)
        if remainder and remainder[0] in MANAGEMENT_COMMANDS:
            command, *management_args = remainder
            # A leading --session takes precedence over the environment, while
            # options after a management command are also supported.
            command_env = current.copy()
            if leading_session is not None:
                command_env["DSH_SESSION_ID"] = leading_session
            return _management(command, management_args, command_env, runner,
                                leading_explicit=leading_explicit)

        if not remainder and not args:
            session = resolve_session(leading_session, current)
            if sys.stdin.isatty():
                return _passthrough(session, [], current, runner, do_exec)
            maybe_reap_idle(current, runner)
            worker = ensure_worker(session, current, runner)
            touch_worker(worker, state_root(current))
            environment = harness_env(worker, worker["ports"], state_root(current), current)
            ensure_daemon(worker, worker["cdp"], environment, runner, force_reload=worker["changed"])
            if do_exec:
                _exec_harness(_harness_binary(environment), [], environment)
            result = _invoke(runner, [_harness_binary(environment)], environment, capture=False)
            return _returncode(result)

        # Every non-management token is passed through without starting a worker.
        session = resolve_session(leading_session, current)
        return _passthrough(session, remainder, current, runner, do_exec)
    except BrowserCLIError as error:
        print(f"browser: {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(f"browser: command failed with exit status {error.returncode}", file=sys.stderr)
        return int(error.returncode or 1)


if __name__ == "__main__":
    raise SystemExit(main())
