---
name: browser
description: Control Chromium in a session-isolated Docker virtual screen through the browser CLI. Use for web interaction, browser automation, rendered pages, screenshots, and browser login sessions.
---

# Virtual browser

Use `browser` for browser interaction. Each DSH session has its own worker:
a Docker container, Chromium, noVNC screen, Browser Harness daemon, and persistent
profile/login state. Sessions never share tabs, profiles, or daemons. The CLI selects
the worker from `DSH_SESSION_ID`; use `--session ID` at the front to target another
session or when no session ID is set. There is no shared default worker. The first
browser script automatically starts or reuses that worker and verifies its daemon
before connecting.

For public information that does not require browser interaction, use HTTP fetch.

```sh
browser <<'PY'
new_tab("https://www.wikipedia.org")
wait_for_load()
print(page_info())
PY
```

Python helpers are pre-imported: `page_info()`, `list_tabs()`, `current_tab()`,
`switch_tab(target_id)`, `goto_url(url)`, `wait_for_element(selector)`,
`js(expression)`, `cdp(method, **params)`, `click_at_xy(x, y)`, `type_text(text)`,
and `capture_screenshot(path)`.

Prefer accessibility nodes from `cdp("Accessibility.getFullAXTree")` to find
controls. Obtain their coordinates with `cdp("DOM.getBoxModel", backendNodeId=...)`
and click using `click_at_xy`. Use `js` for inspection and verify actions with a
targeted DOM check. Screenshots help when visual layout matters. Capturing a
screenshot brings the requested tab to the front of this worker's virtual screen
to avoid Chromium stalls; it may change what someone viewing this worker in noVNC
sees, but does not affect other sessions.

To target another session, put `--session ID` at the very front, before the command,
harness arguments, or stdin. The CLI removes it before invoking Browser Harness.
The raw session ID is never shown in output; management JSON identifies workers by
`worker_id`.

## Worker commands

- `browser [--session ID] start` — start or reuse that session's worker and daemon.
- `browser [--session ID] status` — report status; never creates anything.
- `browser [--session ID] view [--open]` — print the noVNC URL (with `--open`, also
  open it in the Mac browser). Get the current URL here rather than assuming a
  fixed port; the worker must already be running.
- `browser list` — list managed workers by label/worker ID; never creates anything.
- `browser [--session ID] stop` — stop and remove that worker's container; keep its
  profile for the next start.
- `browser --session ID remove [--purge-profile]` — remove the worker; delete its
  profile only when `--purge-profile` is supplied.
- `browser reap [--timeout SEC] [--dry-run]` — stop workers idle longer than the
  timeout; their profiles are kept. Default is `BROWSER_IDLE_TIMEOUT` (3600 seconds);
  `0` disables automatic reaping.
- `browser [--session ID] forward PORT...` — relay host `127.0.0.1:PORT` into this
  worker, so a page opened inside the worker can reach a dev server running on the
  Mac (for example Vite on 5173) with HMR intact. Only the listed ports are relayed.
- `browser [--session ID] unforward` — stop relaying host ports into this worker.

Workers idle longer than the timeout are stopped on the next `browser start` or
browser script (at most once a minute), keeping their profiles. Use `browser list`
to find leftovers, then explicitly stop or remove the intended worker.
A worker's Chromium profile keeps its login state across restarts until its profile
is purged. Harness state is stored under
`${XDG_STATE_HOME:-~/.local/state}/browser`. Keep credentials, cookies, and downloaded
private content outside this repository. Recording is disabled by default.

For login, reuse this worker's existing session. Request user input for passwords,
MFA, consent, or ambiguous account selection; the user can take over through this
worker's noVNC screen. The Mac browser's login session is separate.

If the connection needs recovery, run `browser --reload` and retry. This reloads only
the current session's daemon; it does not start a worker. Before every script the CLI
also proves the daemon is attached to this worker's Chromium and reloads that daemon
alone when it is not, so a stale or reused port never reaches another worker.
