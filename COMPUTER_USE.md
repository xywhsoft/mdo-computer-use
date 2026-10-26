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
