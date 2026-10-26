"""Native MCP transport must retain a valid image above the old 1 MiB limit."""
from pathlib import Path
import runpy
from test_computer_use_catalog import run_fixture, ROOT, STATE

if __name__ == '__main__':
    code, output = run_fixture('large-image-cap', 'tests/fixtures/computer-use-image-cap.c')
    print(output)
    expected = runpy.run_path(str(ROOT / 'tests/fixtures/computer-use-image-peer.py'))['image']()
    path = STATE / 'large-image-result.png'
    raise SystemExit(0 if code == 0 and 'large_mcp_image=PASS' in output
                     and path.read_bytes() == expected else 1)
