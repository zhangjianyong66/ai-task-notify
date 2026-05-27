import importlib.util
import os
import stat
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("codex-wrapper.py")
SPEC = importlib.util.spec_from_file_location("codex_wrapper", MODULE_PATH)
codex_wrapper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(codex_wrapper)


class CodexWrapperConfigTest(unittest.TestCase):
    def test_default_paths_are_relative_to_user_and_project(self):
        env = {"HOME": "/home/example"}

        self.assertEqual(
            codex_wrapper.get_log_path(env),
            Path("/home/example/.codex/log/codex-tui.log"),
        )
        self.assertEqual(
            codex_wrapper.get_notify_script(env),
            MODULE_PATH.with_name("notify.py").resolve(),
        )

    def test_find_real_codex_skips_wrapper_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            wrapper = root / "bin1" / "codex"
            real = root / "bin2" / "codex"
            wrapper.parent.mkdir()
            real.parent.mkdir()
            wrapper.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            real.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
            real.chmod(real.stat().st_mode | stat.S_IXUSR)

            found = codex_wrapper.find_real_codex(
                {},
                path_env=os.pathsep.join([str(wrapper.parent), str(real.parent)]),
                wrapper_path=wrapper,
            )

        self.assertEqual(found, real.resolve())

    def test_real_codex_env_override_wins(self):
        env = {"CODEX_WRAPPER_REAL_CODEX": "/opt/codex/bin/codex"}

        self.assertEqual(
            codex_wrapper.find_real_codex(env, path_env="", wrapper_path=MODULE_PATH),
            Path("/opt/codex/bin/codex"),
        )


if __name__ == "__main__":
    unittest.main()
