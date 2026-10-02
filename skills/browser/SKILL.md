---
name: browser
description: Control Chromium in a Docker virtual screen through the shared browser CLI. Use for web interaction, browser automation, rendered pages, screenshots, and browser login sessions.
---

# Virtual browser

Use `browser` for browser interaction. It starts the dedicated Docker browser
automatically and attaches through CDP. The browser runs in a Linux virtual
screen; normal operations do not open or foreground a Mac browser.

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
targeted DOM check. Screenshots help when visual layout matters.

The CLI uses one shared browser, profile, and daemon across agents. Reuse tabs
for the same task. Coordinate simultaneous browser operations so another agent
does not change the attached tab during an action. Do not stop the shared browser
or close another task's tabs when finishing your own task.

`browser status` checks readiness without starting it. `browser start` explicitly
starts it. `browser stop` stops it while preserving its profile. Use `browser view`
only when the user requests the visible screen; it opens noVNC in their browser.
The screen is also available at
`http://127.0.0.1:6080/vnc.html?autoconnect=true&resize=scale&reconnect=true`.

For login, reuse the container's existing session. Request user input for passwords,
MFA, consent, or ambiguous account selection; the user can take over through noVNC.
The Mac browser's login session is separate.

State and harness files are in `${XDG_STATE_HOME:-~/.local/state}/browser`.
The Chromium profile is in the `agent-browser-profile` Docker volume.
Keep credentials, cookies, and downloaded private content outside this repository.
Recording is disabled by default; enable it only when requested for the task.

Connection recovery: `browser --reload` resets this browser's daemon, then retry
the operation. Do not launch local Chrome, switch to Browser Use Cloud, or call
an unwrapped `browser-harness` or `browser-use` command to work around a failure.
