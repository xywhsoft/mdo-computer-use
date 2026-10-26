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
        self.assertTrue(first["enabled"])
        self.assertFalse(second["enabled"])
        self.assertEqual(first["transport"]["program"], str(binary))


if __name__ == "__main__":
    unittest.main()
