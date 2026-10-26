# mdo Computer Use

This repository develops Computer Use on the mdo baseline
`fdd32d6b` from <https://gitee.com/xywhsoft/mdo>. Its own remote is
<https://gitee.com/xywhsoft/mdo-computer-use>.

The implementation uses an unmodified Cua Driver over mdo's existing stdio MCP
transport with protocol `2026-07-28`. Windows is the first validated platform;
Linux and macOS will use platform-specific launch profiles. No additional Agent
prompt, Skill, recovery policy, or Cua compatibility patch is installed.

## Delivery status — 2026-10-26

The Windows integration is implemented and source-built. The official 63-tool
catalog is available, both template variants pass native connection lifecycle
validation, and 25 deterministic desktop/browser/authorization checks pass.
The existing account model completes a real single-click and post-action visual
feedback task on the default Responses route. Complex form/browser tasks still
have the separately recorded failures below. Linux/macOS are extension points,
not device-validated targets. Recording/perception and every individual tool
have not all been exercised; 63 is the discovered schema count.

Start with the [Chinese operating guide](docs/computer-use.md). The sanitized
[machine-readable acceptance record](tests/acceptance/computer-use/windows-2026-10-26.json)
contains both successes and failures without account credentials or runtime IDs.

## Milestones

1. Deploy and smoke-test mdo directly in this checkout, reusing a local executable.
2. Pin the official Cua artifact; supply an installable MCP service template and
   configure a device-local connection without embedding machine paths in it.
3. Validate actual mdo MCP discovery, tool loading, desktop actions and images.
4. Validate the ordinary Agent/model loop, lifecycle and user installation flow.
5. Record known upstream limitations and supported platform scope.

Each completed milestone is committed separately. Runtime files are ignored;
the source checkout and one runtime Home are reused for all stages.

### Stage 1 — environment deployed

Validated on Windows 10 on 2026-10-26: `deploy` reused the existing 6,312,853-byte
mdo executable, and `smoke` started the real application in this checkout,
observed bootstrap `ready`, and stopped its owned process. Its SHA-256 is
`188febb4ad13dc0972ad056d8bb612eaa9c96ee864128c1de3053a18d33d8b4d`.
No SDK checkout, Android toolchain, or duplicate validation application was
created. This stage does not yet configure Cua or a model.

### Stage 2 — official driver and MCP template

The pinned ZIP and all six extracted files have been SHA-256 verified. The
complete official driver is installed once under
`.build/computer-use/cua/0.38.0/`. A second install verifies/reuses it. The
project-local MCP definition starts disabled and mdo's real native parser
accepts it without connecting. The generated service package passes mdo's
`plan_import` API and reports that device configuration is required.

```powershell
python -m computer_use driver --archive PATH_TO_OFFICIAL_ZIP
python -m computer_use configure
python -m computer_use package
python -m unittest discover -s tests -p test_computer_use.py
```

Omit `--archive` to download exactly the pinned official release. The package
output is `.build/computer-use/computer-use.mdo-extension.json`; its contents
contain only a public MCP template. It does not contain the local driver path,
driver binaries, credentials or Agent instructions. Enable the device connection
explicitly with `python -m computer_use configure --enable --replace` while mdo
is stopped, then launch it. On Windows the binary files remain byte-identical
to the official archive. Other platforms are not advertised as validated yet;
their future templates can use the same MCP contract with native launch modes.

### Stage 3 — actual mdo transport and installation flow

`probe` has passed against the real deployed application and official driver:
protocol `2026-07-28`, 63 discovered tools, two discovery requests, successful
refresh operation, and explicit transport disconnect. No alternate MCP client
or driver shim is involved. There were no remaining Cua processes after exit.

`install-template` imports the package through mdo's normal plan/import API.
`verify-template` has passed native parameter preview, creation of a disabled
template-bound connection, and removal of that test connection. It uses the
same project Home and executable, without changing the active Cua connection.

```powershell
python -m computer_use probe
python -m computer_use install-template
python -m computer_use verify-template
```

The existing mdo account is available in this development Home using its
device-protected saved session. No plaintext token or account data is included
in source control. The available account model currently includes
`ornith-1.5-35b` with image and tool capabilities; actual Agent execution is the
next milestone.

### Stage 4 — source-matched build and native acceptance runner

The first real model run exposed that the initially reused executable reported
0.6.0, while this checkout contains 0.7.0. That run exited abnormally during
tool loading before it changed the test controls. It is not a completed desktop
acceptance result or evidence that Cua caused the exit.

The environment now builds the current checkout with the exact SDK lock. One
streamed SDK source export is reused under `.build/computer-use/sdk`; there are
no dependency worktrees or duplicate test deployments. The standard mdo build
uses its existing locked SDK overlay, with no changes to Cua. Startup now
rejects a deployed version that differs from `app/release.json`.

```powershell
python -m computer_use build --xserver-repository D:\GIT\xserver
python -m computer_use smoke
python -m computer_use acceptance --model ornith-1.5-35b
```

The fresh 0.7.0 application passes readiness, 63-tool Cua discovery and template
lifecycle checks. The project Home limits parallel tools and subagents to one
using the standard settings fields, matching this task's sequential constraint.
The acceptance runner uses the existing account, ordinary default Agent and a
normal user task against `tests/fixtures/computer-use-win32.c`. Its fixture is
compiled once and reused; the app and Home remain in this checkout. A real
model outcome is recorded separately from transport success.

### Stage 5 — deterministic host lifetime regression

The fresh 0.7.0 host also exits during dynamic tool loading, before Cua input.
A model-free, Cua-free native regression now reproduces the underlying lifetime
gap: adding a tool retires a catalog whose entries are still borrowed by the
active execution and executor tool view. It prints
`catalog_retired_while_borrowed owners=1` and exits deliberately before accessing
the freed data. Run it directly in this checkout:

```powershell
python tests/test_computer_use_catalog.py
```

This is a generic mdo host integration defect, separate from the deferred Cua
window/cancellation behavior. The required correction belongs to mdo's catalog
ownership; the official Cua binaries and Agent instructions remain unchanged.

### Stage 6 — retained host catalog ownership

The mdo SDK overlay now retains the active tool catalog for the full execution
callback and retains the executor's borrowed descriptor strings until its tool
view is rebuilt or unbound. The public ABI is unchanged. Both ownership paths
are exercised by the native regression, including release counts after unbind
and Agent destruction. It now reports `catalog_lifetime=PASS`.

The authoritative change is in the existing mdo SDK overlay and `deps.lock`,
not just a local SDK edit. Reverse/clean application of the complete overlay
and dependency tree verification passed. The rebuilt 0.7.0 app again passes
readiness, Cua's 63-tool discovery, template connection lifecycle and the four
package checks. Cua's six official files still match the pinned release.

### Stage 7 — reproduced missing multimodal tool output

An offline native test uses the public `xllmClientBuildRequestJson` API without
network calls or credentials. Plain text and one typed text part survive, while
text plus image, image-only and multiple text parts become empty strings in
Responses function outputs. Run `python tests/test_computer_use_responses.py`;
its initial expected failure captures the exact wire defect. The real model
test remains incomplete until this generic host serialization path is fixed.

### Stage 8 — multimodal Responses outputs retained

The generic Responses serializer now emits typed output arrays for multipart
and image-only tool results, as supported by the official function-calling
format. Both existing string forms remain unchanged. All five native wire
checks pass after rebuilding mdo 0.7.0. Catalog lifetime, readiness and the four
package checks also pass. The overlay applies cleanly to its locked SDK base,
and dependency hashes are updated. Real desktop/model acceptance follows next.

### Stage 9 — real model observation, with an independent visual challenge

The Windows fixture now draws a fresh six-digit code only in its canvas; the
accessible tree does not contain it. On 2026-10-26 the existing account model
`ornith-1.5-35b` correctly read that code from the Cua screenshot in its ordinary
assistant response. This verifies the image reached the real model through
mdo's default Responses route after the serialization fix.

The complete action task **failed** after 184.11 seconds: the model repeatedly
generated an invalid `run_steps` field (`args>`), and mdo stopped it with
`loop_guard` after 22 model calls / 31 tool calls. No fixture controls changed;
the app did not crash. This is not a completed autonomous desktop acceptance.
No model retries, corrective prompts or Cua changes were added. The harness
now recognizes every terminal state, uses the native DELETE cancellation route,
records bounded evidence and always disconnects its transport.

### Stage 10 — deterministic native desktop and browser acceptance

`python -m computer_use transport-check` passes 8 desktop checks and 10 browser
checks. The test-only harness uses this checkout's existing native host and the
same public xwork MCP client used by mdo; it does not reimplement the MCP codec
or add a production control API. All 63 official tool schemas load successfully.
This is deterministic transport/action evidence, separate from model autonomy.

The Win32 oracle confirms Chinese text, one button click, checkbox, Green
selection and one canvas pixel click; both captures return image bytes. The
browser oracle confirms Chinese typing, one click, checkbox, Green selection and
600 px scrolling. Exact tab binding, image capture, stale-ref refusal and ending
the owned browser session also pass. The browser fixture runs only on loopback;
Cua owns its disposable test profile and closes it with the session. No user
profile is copied or changed, and no Cua processes remain after the tests.

Cua may report `effect: refused` inside a successful MCP result. The tests inspect
its structured action result and independent application state; an MCP transport
success alone is not treated as proof that an action happened.

### Stage 11 — browser model outcome and protocol-selectable acceptance

The unchanged default Agent/model browser task ended with `timed_out` at
301.16 seconds, after 30 model calls / 38 tool calls. It opened the local test
page, encountered Cua's ordinary existing-profile authorization boundary, then
created and exactly bound a driver-owned browser. It subsequently tried to
address the browser's URL bar through page tools on `about:blank`; no form
values changed. The owned browser ended on disconnect. The extra local test
tab opened by the model was closed explicitly after checking its exact title,
without closing the user's browser process or other tabs.

`acceptance --scope browser` now records that independent oracle and compact
session evidence. `--protocol` selects mdo's existing per-session protocol for
explicit compatibility comparisons; it does not alter defaults or add retries.
Separate protocol reports preserve earlier outcomes. Autonomous completion with
the current account model is not yet established by either default-route task.

### Stage 12 — protocol comparison and a completed real closed loop

The same model's Anthropic Messages route timed out on its first model request
at 300.19 seconds, before any tool call. Chat Completions made real progress:
the independent oracle confirms Chinese input, one button click and checkbox
selection. That form run timed out at 300.89 seconds (25 model calls / 43 tools)
while resolving the dropdown, so it is still a failed complete-form test.

A separate, ordinary single-click/read-image task **passed** on the default
Responses route in 172.62 seconds (11 model calls / 10 tools). The real account
model found the window, clicked once, re-read it, and reported `Counter: 1`
and the fresh six-digit canvas code in its final answer. The oracle confirms
one click, an image arrived after the click, and only discovery/loading/Cua
tools were used; the model did not read the fixture source or oracle file.

```powershell
python -m computer_use acceptance --scenario click
```

This establishes a real model/action/visual-feedback loop without additional
prompts or retries. It does not make the failed form or browser tasks pass.

### Stage 13 — explicit official existing-browser authorization

The 0.1.1 service template adds a separate `windows-existing-profile` variant
using official `mcp --direct --grant existing-profile`. The original variant
remains standard and ungranted. The CLI exposes the same explicit choice with
`configure --grant-existing-profile`; it never enables this grant implicitly.
The public package still contains only one MCP template and no Cua changes.

Both variants pass real mdo preview/save-disabled/delete validation. A separate
owned empty Chrome profile verifies 7 checks: refusal without the grant,
attachment with the explicit grant, Unicode input, exact binding, screenshot,
preservation of the externally owned browser on disconnect, and removal of
the test profile after the runner closes it. This test does not attach to a
personal profile or enable remote debugging in the user's browser.

```powershell
python -m computer_use transport-check --scope browser-grant
```

## Local environment

### Remaining acceptance — explicit Responses strictness

The resumed work reproduces another generic host wire mismatch: a non-strict
tool definition omits `strict` instead of sending `false`. Responses may try
strict normalization when this field is omitted, unlike Chat Completions.
An offline native regression checks that both boolean values and open argument
maps survive serialization. This is a possible contributor to malformed batch
arguments; a real model run is still required to establish that relationship.
Reference: https://developers.openai.com/api/docs/guides/function-calling

Python 3.12+ is sufficient for the integration commands. Build this checkout's
Windows product with the locked SDK, without building Android/Linux products:

```powershell
python -m computer_use build --xserver-repository D:\GIT\xserver
python -m computer_use smoke
python -m computer_use run
```

The executable is deployed as `mdo.exe`, the runtime Home is `mdo-home/`, and
bounded stage results/logs live in `.build/computer-use/`. The generated root
`xs.json` is local runtime configuration. `run` opens the desktop UI; `run
--headless` serves the same app on loopback without a visible window. The
default development port is 5391.

The deployment receipt records commit/dirty status, dependency-lock and overlay
hashes, plus binary SHA-256. `deploy --mdo PATH` remains available for explicitly
reusing a version-compatible executable, but does not claim a source build.
Normal source builds use `tools/build_mdo.py` and its locked dependencies.

## Deferred observations

The prior Cua 0.38.0 evaluation found a UWP inner/outer-window discovery/capture
issue and a cancellation delay on ordinary stdio `verify_state`. They remain
unmodified and will be measured separately. Current mdo forwards one supported
MCP image up to 1 MiB to the model; tests must distinguish a returned screenshot
from a screenshot actually reaching the model.
