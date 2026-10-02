"""Lifecycle for the shared virtual browser; browser interactions use Browser Harness."""

import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request


CONTAINER = "agent-browser"
CDP_URL = "http://127.0.0.1:9222"
VIEW_URL = "http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale&reconnect=true"
STATE = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "browser"
HARNESS = os.environ["BROWSER_HARNESS_BIN"]
IMAGE = os.environ["BROWSER_DOCKER_IMAGE"]
SOURCE = os.environ["BROWSER_DOCKER_SOURCE"]


def run(command, *, capture=False, check=True):
    return subprocess.run(
        command, check=check, text=True,
        stdout=subprocess.PIPE if capture else sys.stderr,
        stderr=subprocess.PIPE if capture else sys.stderr,
    )


def configure_engine(start=False):
    # Use an isolated config so obsolete Docker Desktop credential helpers and
    # the user's active Docker context cannot redirect this browser.
    config_dir = STATE / "docker"
    config_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DOCKER_CONFIG"] = str(config_dir)
    os.environ.pop("DOCKER_CONTEXT", None)
    if sys.platform == "darwin":
        command = ["colima", "--profile", CONTAINER]
        status = run(command + ["status", "--json"], capture=True, check=False)
        if status.returncode and start:
            run(command + ["start", "--activate=false", "--cpu", "2", "--memory", "4", "--disk", "20"])
            status = run(command + ["status", "--json"], capture=True)
        if status.returncode:
            return False
        os.environ["DOCKER_HOST"] = json.loads(status.stdout)["docker_socket"]
    return run(["docker", "info", "--format", "{{.OSType}}"], capture=True, check=False).returncode == 0


def inspect():
    result = run(["docker", "container", "inspect", CONTAINER], capture=True, check=False)
    return json.loads(result.stdout)[0] if result.returncode == 0 else None


def ready():
    try:
        with urllib.request.urlopen(CDP_URL + "/json/version", timeout=1) as response:
            version = json.load(response)
        with urllib.request.urlopen("http://127.0.0.1:6080/vnc.html", timeout=1) as response:
            return bool(version.get("webSocketDebuggerUrl")) and response.status == 200
    except (OSError, ValueError, urllib.error.URLError):
        return False


def reset_daemon():
    run([HARNESS, "--reload"], capture=True, check=False)


def start():
    if not configure_engine(start=True):
        raise RuntimeError("Docker is unavailable. Start the Docker engine and retry.")
    container = inspect()
    if container and container["Config"]["Image"] != IMAGE:
        reset_daemon()
        run(["docker", "rm", "--force", CONTAINER])
        container = None
    if container is None:
        if run(["docker", "image", "inspect", IMAGE], capture=True, check=False).returncode:
            run(["docker", "build", "--tag", IMAGE, SOURCE])
        run([
            "docker", "run", "--detach", "--name", CONTAINER, "--init",
            "--restart", "unless-stopped", "--shm-size", "1g", "--stop-timeout", "30",
            "--publish", "127.0.0.1:6080:6080", "--publish", "127.0.0.1:9222:9223",
            "--volume", "agent-browser-profile:/profile", IMAGE,
        ])
    elif not container["State"]["Running"]:
        reset_daemon()
        run(["docker", "start", CONTAINER])
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if ready():
            return
        time.sleep(0.5)
    run(["docker", "logs", "--tail", "30", CONTAINER], check=False)
    raise RuntimeError("Chromium or noVNC did not become ready within 45 seconds.")


def main():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.environ["BH_HOME"] = str(STATE / "harness")
    os.environ["BU_NAME"] = "default"
    os.environ["BU_CDP_URL"] = CDP_URL
    os.environ.pop("BU_CDP_WS", None)
    os.environ.pop("BU_BROWSER_ID", None)
    os.environ["BH_TAB_MARKER"] = "0"
    os.environ.setdefault("BH_RECORD", "0")
    args = sys.argv[1:]
    command = args[0] if args else None
    if command in ("--help", "-h", "help"):
        print("browser [start|stop|status|view]\n"
              "browser <<'PY'\nprint(page_info())\nPY\n\n"
              "start: prepare Chromium and noVNC; also runs automatically for browser scripts\n"
              "stop: stop Chromium and its dedicated Colima VM; preserve the profile\n"
              "status: report readiness without starting anything\n"
              "view: start the browser and open its noVNC screen\n\n"
              "Python helpers: new_tab(url), page_info(), js(expression), cdp(method, **params),\n"
              "click_at_xy(x, y), type_text(text), capture_screenshot(path).")
        return
    if command in ("start", "stop", "status", "view") and len(args) != 1:
        raise RuntimeError(f"browser {command} does not take arguments")
    if command == "skill":
        print(Path(os.environ["BROWSER_SKILL_PATH"]).read_text(), end="")
        return
    if command in ("--version", "--reload", "recordings", "telemetry"):
        os.execv(HARNESS, [HARNESS, *args])
    with (STATE / "lifecycle.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if command == "status":
            engine = configure_engine()
            container = inspect() if engine else None
            running = bool(container and container["State"]["Running"])
            print(json.dumps({"running": running, "ready": running and ready(), "cdp": CDP_URL, "view": VIEW_URL}))
            return
        if command == "stop":
            reset_daemon()
            if configure_engine() and inspect():
                run(["docker", "stop", CONTAINER])
            if sys.platform == "darwin":
                run(["colima", "--profile", CONTAINER, "stop"], check=False)
            return
        start()
    if command == "start":
        print(json.dumps({"cdp": CDP_URL, "view": VIEW_URL}))
    elif command == "view":
        run(["open" if sys.platform == "darwin" else "xdg-open", VIEW_URL])
    else:
        os.execv(HARNESS, [HARNESS, *args])


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"browser: {error}", file=sys.stderr)
        sys.exit(1)
