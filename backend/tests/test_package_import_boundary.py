"""CLI/package imports must not initialize the application or persistent state."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

BACKEND = Path(__file__).resolve().parents[1]
GUARD = '''
import sys

# On Windows, Python 3.11 discovers OS metadata via the read-only `ver`
# command. Populate this stdlib cache before guarding application imports.
if sys.platform == "win32":
    import platform
    platform.uname()

def reject_external_effects(event, args):
    if event in ("socket.connect", "socket.bind", "subprocess.Popen", "os.system"):
        raise AssertionError("Unexpected external effect: " + event)

sys.addaudithook(reject_external_effects)
'''
BLOCK_APP = '''
import importlib.abc
class BlockApplication(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "hydra.app":
            raise AssertionError("Application imported before it was requested")
sys.meta_path.insert(0, BlockApplication())
'''


class PackageImportBoundaryTests(unittest.TestCase):
    def run_python(self, program, *, block_app=True, expected=0, no_state=True):
        with tempfile.TemporaryDirectory(prefix="hydralab import ") as temporary:
            root = Path(temporary)
            env = {
                "PATH": os.defpath,
                "HOME": temporary,
                "USERPROFILE": temporary,
                "APPDATA": str(root / "roaming"),
                "LOCALAPPDATA": str(root / "local"),
                "HYDRA_HOME": str(root / "hydra"),
                "HYDRALAB_APP_DATA_ROOT": str(root / "app-data"),
                "HYDRALAB_PROJECT_ROOT": str(root / "project"),
                "HYDRALAB_SECRET_STORE": "memory",
                "XDG_CONFIG_HOME": str(root / "config"),
                "XDG_DATA_HOME": str(root / "data"),
                "XDG_CACHE_HOME": str(root / "cache"),
                "PYTHONPATH": str(BACKEND),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            # Python and its Windows runtime need these noncredential system paths.
            for name in ("SYSTEMROOT", "WINDIR"):
                if name in os.environ:
                    env[name] = os.environ[name]
            result = subprocess.run(
                [sys.executable, "-c", GUARD + (BLOCK_APP if block_app else "") + textwrap.dedent(program)],
                cwd=root, env=env, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
            if no_state:
                self.assertEqual(list(root.rglob("*")), [], "Import/help created persistent state")
            return result

    def test_subprocess_guard_remains_active(self):
        self.run_python('''
            import subprocess
            try:
                subprocess.run([sys.executable, "-c", "raise SystemExit(99)"])
            except AssertionError as error:
                assert "subprocess.Popen" in str(error)
            else:
                raise AssertionError("Application subprocess guard was bypassed")
        ''')

    def test_package_import_does_not_load_application(self):
        self.run_python('import hydra; assert "hydra.app" not in sys.modules')

    def test_unknown_attribute_does_not_load_application(self):
        self.run_python('''
            import hydra
            try:
                hydra.not_an_export
            except AttributeError as error:
                assert "not_an_export" in str(error)
            else:
                raise AssertionError("missing AttributeError")
        ''')

    def test_export_is_discoverable_without_loading_application(self):
        self.run_python('import hydra; assert "create_app" in dir(hydra); assert hydra.__all__ == ["create_app"]')

    def test_runtime_submodule_does_not_load_application(self):
        self.run_python('import hydra.storage.runtime; assert "hydra.app" not in sys.modules')

    def test_module_help_does_not_load_application(self):
        result = self.run_python('import runpy; sys.argv=["hydralab", "--help"]; runpy.run_module("hydra.serve", run_name="__main__")')
        self.assertIn("--app-data-root", result.stdout)

    def test_console_entry_help_does_not_load_application(self):
        result = self.run_python('from hydra.serve import main; sys.argv=["hydralab", "--help"]; main()')
        self.assertIn("--project-root", result.stdout)

    def test_invalid_arguments_do_not_load_application(self):
        result = self.run_python('from hydra.serve import main; sys.argv=["hydralab", "--not-an-option"]; main()', expected=2)
        self.assertIn("unrecognized arguments", result.stderr)

    def test_actual_help_leaves_disposable_state_empty(self):
        self.run_python('import runpy; sys.argv=["hydralab", "--help"]; runpy.run_module("hydra.serve", run_name="__main__")', block_app=False)

    def test_requested_export_preserves_actual_function_identity(self):
        self.run_python('''
            import hydra
            from hydra import create_app
            from hydra.app import create_app as actual
            assert create_app is actual is hydra.create_app
            assert hydra.create_app is hydra.create_app
        ''', block_app=False, no_state=False)

    def test_star_import_preserves_public_export(self):
        self.run_python('''
            from hydra import *
            from hydra.app import create_app as actual
            assert create_app is actual
        ''', block_app=False, no_state=False)


if __name__ == "__main__":
    unittest.main()
