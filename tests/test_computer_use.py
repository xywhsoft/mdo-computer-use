"""Small integration-package checks; no duplicate mdo deployment or desktop calls."""
import json
from pathlib import Path
import unittest

from computer_use import driver
from computer_use.__main__ import STATE


class ComputerUsePackage(unittest.TestCase):
    def test_public_template_contains_only_device_binding(self):
        package = driver.extension_package()
        self.assertEqual([item["kind"] for item in package["resources"]], ["mcp"])
        template = json.loads(package["resources"][0]["content"])
        config = template["variants"][0]["config"]
        self.assertEqual(config["transport"]["program"], {"input": "driver-path"})
        self.assertEqual(config["protocol_version"], "2026-07-28")
        self.assertEqual(config["transport"]["arguments"], ["mcp", "--direct"])
        self.assertNotIn(str(Path.cwd()), json.dumps(package))

    def test_existing_browser_grant_is_a_separate_explicit_variant(self):
        template = json.loads(driver.extension_package()["resources"][0]["content"])
        variants = {v["id"]: v for v in template["variants"]}
        ordinary = variants["windows"]["config"]["transport"]["arguments"]
        granted = variants["windows-existing-profile"]["config"]["transport"]["arguments"]
        self.assertNotIn("--grant", ordinary)
        self.assertEqual(granted, ordinary + ["--grant", "existing-profile"])
        self.assertNotIn("--dangerously-bypass-approvals", granted)

    def test_unverified_archive_cannot_create_install(self):
        # Reuse an existing tiny source file as invalid input, without temporary
        # copies of the app or official 94 MiB driver.
        target = STATE / "rejected-driver"
        self.assertFalse(target.exists())
        with self.assertRaisesRegex(ValueError, "archive size/SHA-256"):
            driver.install(target, Path(__file__))
        self.assertFalse(target.exists())

    def test_device_connection_requires_pinned_files(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            driver.connection(Path(__file__))

    def test_installed_driver_is_reused_and_template_is_not_mutated(self):
        installed = STATE / "cua" / driver.LOCK["version"]
        if not installed.exists():
            self.skipTest("Install the official driver to verify reuse")
        binary = driver.install(STATE)
        first = driver.connection(binary, True)
        second = driver.connection(binary)
        granted = driver.connection(binary, grant_existing_profile=True)
        self.assertTrue(first["enabled"])
        self.assertFalse(second["enabled"])
        self.assertEqual(first["transport"]["program"], str(binary))
        self.assertEqual(granted["transport"]["arguments"], ["mcp", "--direct", "--grant", "existing-profile"])
        self.assertEqual(second["transport"]["arguments"], ["mcp", "--direct"])


if __name__ == "__main__":
    unittest.main()
