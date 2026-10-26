# mdo Computer Use

This repository develops Computer Use on the mdo baseline
`fdd32d6b` from <https://gitee.com/xywhsoft/mdo>. Its own remote is
<https://gitee.com/xywhsoft/mdo-computer-use>.

The implementation uses an unmodified Cua Driver over mdo's existing stdio MCP
transport with protocol `2026-07-28`. Windows is the first validated platform;
Linux and macOS will use platform-specific launch profiles. No additional Agent
prompt, Skill, recovery policy, or Cua compatibility patch is installed.

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

## Local environment

Python 3.12+ is sufficient for the integration commands. Reuse an existing mdo
executable instead of rebuilding unrelated Android/Linux products:

```powershell
python -m computer_use deploy --mdo D:\GIT\mdo\mdo.exe
python -m computer_use smoke
python -m computer_use run
```

The executable is deployed as `mdo.exe`, the runtime Home is `mdo-home/`, and
bounded stage results/logs live in `.build/computer-use/`. The generated root
`xs.json` is local runtime configuration. `run` opens the desktop UI; `run
--headless` serves the same app on loopback without a visible window. The
default development port is 5391.

The deployment receipt records binary provenance and SHA-256. Reusing a binary
does not claim it was rebuilt from this checkout. Normal source builds still
use the upstream `tools/build_mdo.py` and its locked dependencies.

## Deferred observations

The prior Cua 0.38.0 evaluation found a UWP inner/outer-window discovery/capture
issue and a cancellation delay on ordinary stdio `verify_state`. They remain
unmodified and will be measured separately. Current mdo forwards one supported
MCP image up to 1 MiB to the model; tests must distinguish a returned screenshot
from a screenshot actually reaching the model.
