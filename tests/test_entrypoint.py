"""Guards for the frozen exe's real startup path (main.py).

Nothing else ever executes main() — a missing name there ships as a
crashing .exe (real user bug: "NameError: name '_dpi_aware' is not
defined" in the PyInstaller error dialog). These tests execute the entry
module and lint the whole package for undefined names so that class of
regression can never ship again.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestMainEntry(unittest.TestCase):
    def test_module_imports_and_main_callable(self):
        import main as entry
        self.assertTrue(callable(entry.main))

    def test_dpi_aware_defined_and_never_raises(self):
        import main as entry
        fn = getattr(entry, "_dpi_aware", None)
        self.assertTrue(callable(fn), "_dpi_aware missing from main.py")
        fn()  # must be a safe no-op, including off-Windows


class TestNoUndefinedNames(unittest.TestCase):
    def test_pyflakes_undefined_names(self):
        try:
            from pyflakes.api import checkRecursive
            from pyflakes.reporter import Reporter
        except ImportError:
            self.skipTest("pyflakes not installed")
        found = []

        class R(Reporter):  # noqa: N801 - minimal reporter
            def unexpectedError(self, filename, msg):  # noqa: D102
                found.append(f"{filename}: {msg}")

            def syntaxError(self, filename, msg, lineno, offset, text):  # noqa: D102
                found.append(f"{filename}:{lineno}: {msg}")

            def flake(self, message):  # noqa: D102
                text = message.message % message.message_args
                if "undefined name" in text:
                    found.append(f"{message.filename}:{message.lineno}: {text}")

        r = R(sys.stdout, sys.stderr)
        paths = [str(ROOT / "main.py")] + \
            [str(p) for p in sorted((ROOT / "jarvis").rglob("*.py"))]
        checkRecursive(paths, r)
        self.assertEqual(
            found, [],
            "undefined names crash at runtime:\n" + "\n".join(found))


if __name__ == "__main__":
    unittest.main()
