"""Actual native Responses JSON contract, without network or model credentials."""
import json

from test_computer_use_catalog import run_fixture


def main():
    code, output = run_fixture("responses-wire", "tests/fixtures/computer-use-responses.c")
    if code:
        print(output)
        return 1
    values = {}
    schema = None
    for line in output.splitlines():
        if line.startswith("wire_"):
            name, raw = line.split("=", 1)
            values[name[5:]] = json.loads(raw)["input"][0]["output"]
        if line.startswith("schema_wire="):
            schema = json.loads(line.split("=", 1)[1])["tools"]
    expected = {
        "plain": "plain-result", "text": "window-tree",
        "mixed": [{"type": "input_text", "text": "window-tree"},
                  {"type": "input_image", "image_url": "data:image/png;base64,iVBORw=="}],
        "image": [{"type": "input_image", "image_url": "data:image/png;base64,iVBORw=="}],
        "texts": [{"type": "input_text", "text": "window-tree"},
                  {"type": "input_text", "text": "second-part"}],
    }
    if values != expected:
        print("responses_tool_parts=FAIL", json.dumps(values))
        return 1
    print("responses_tool_parts=PASS (plain, typed text, text+image, image-only, multiple texts)")
    if (not schema or schema[0].get("strict") is not False or schema[1].get("strict") is not True
            or schema[0]["parameters"]["properties"]["args"]["additionalProperties"] is not True):
        print("responses_explicit_strict=FAIL", json.dumps(schema))
        return 1
    print("responses_explicit_strict=PASS (non-strict and strict preserved without schema rewriting)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
