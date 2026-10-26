"""Large persisted tool results must fit the native session's text cap."""
from test_computer_use_catalog import run_fixture

if __name__ == "__main__":
    code, output = run_fixture("typed-result-cap", "tests/fixtures/computer-use-result-cap.c")
    print(output)
    raise SystemExit(0 if code == 0 and "typed_result_cap=PASS" in output else 1)
