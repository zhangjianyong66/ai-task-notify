import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

import setup_config


class Args:
    non_interactive = True
    migrate = False
    dry_run = False


class UninstallArgs:
    non_interactive = True
    dry_run = False


class SetupConfigTest(unittest.TestCase):
    def make_fixture(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        repo = root / "repo"
        home = root / "home"
        bin_dir = home / "bin"
        repo.mkdir()
        bin_dir.mkdir(parents=True)
        for name in ("setup.sh", "notify.py", "codex-hook.py", "codex-wrapper.py"):
            (repo / name).write_text("#!/bin/sh\n", encoding="utf-8")
        codex = bin_dir / "codex"
        codex.write_text("#!/bin/sh\nprintf 'codex 0.145.0\\n'\n", encoding="utf-8")
        codex.chmod(0o755)
        (repo / ".env").write_text("# keep\nNOTIFY_CHANNELS=wecom\nWECOM_WEBHOOK_URL=https://example.invalid/hook\nUNKNOWN=value\n", encoding="utf-8")
        env = {"HOME": str(home), "PATH": str(bin_dir), "CODEX_HOME": str(home / "codex"), "XDG_STATE_HOME": str(home / "state")}
        return temp, repo, env

    def test_paths_honor_home_codex_home_and_state(self):
        temp, repo, env = self.make_fixture()
        self.addCleanup(temp.cleanup)
        paths = setup_config.resolve_paths(repo, env)
        self.assertEqual(paths.codex_home, Path(env["CODEX_HOME"]).resolve())
        self.assertEqual(paths.state_dir, Path(env["XDG_STATE_HOME"]).resolve() / "ai-task-notify")

    def test_missing_fields_only_reports_names(self):
        missing = setup_config.missing_notification_fields({"NOTIFY_CHANNELS": "email", "SMTP_HOST": "smtp"})
        self.assertIn("SMTP_USER", missing)
        self.assertNotIn("smtp", missing)

    def test_process_environment_values_are_not_copied_to_dotenv(self):
        temp, repo, env = self.make_fixture()
        self.addCleanup(temp.cleanup)
        env["WECOM_WEBHOOK_URL"] = "https://process-only.invalid/secret"
        paths = setup_config.resolve_paths(repo, env)
        self.assertEqual(setup_config.install(paths, Args(), env), 0)
        self.assertNotIn("process-only.invalid", paths.env_file.read_text(encoding="utf-8"))

    def test_toml_and_hooks_edits_preserve_unrelated_content_and_are_idempotent(self):
        original = "# comment\nmodel = \"gpt\"\nnotify = [\"old\"]\n"
        edited = setup_config.edit_config_toml(original, Path("/repo/notify.py"), Path("/home/.codex/log"))
        self.assertIn('model = "gpt"', edited)
        self.assertEqual(edited, setup_config.edit_config_toml(edited, Path("/repo/notify.py"), Path("/home/.codex/log")))
        hooks = setup_config.merge_hooks('{"hooks":{"UserPromptSubmit":[{"hooks":[]}]}}', Path("/repo/codex-hook.py"))
        data = json.loads(hooks)
        self.assertIn("UserPromptSubmit", data["hooks"])
        self.assertEqual(hooks, setup_config.merge_hooks(hooks, Path("/repo/codex-hook.py")))

    def test_new_toml_keys_are_inserted_before_first_table(self):
        edited = setup_config.edit_config_toml(
            '[projects."/repo"]\ntrust_level = "trusted"\n',
            Path("/repo/notify.py"),
            Path("/home/.codex/log"),
        )
        self.assertLess(edited.index("notify ="), edited.index("[projects."))
        self.assertLess(edited.index("log_dir ="), edited.index("[projects."))

    def test_install_check_uninstall_lifecycle_and_env_preservation(self):
        temp, repo, env = self.make_fixture()
        self.addCleanup(temp.cleanup)
        paths = setup_config.resolve_paths(repo, env)
        self.assertEqual(setup_config.install(paths, Args(), env), 0)
        self.assertEqual(stat.S_IMODE(paths.env_file.stat().st_mode), 0o600)
        self.assertEqual(setup_config.install(paths, Args(), env), 0)
        self.assertEqual(setup_config.check(paths, env), 0)
        self.assertEqual(setup_config.uninstall(paths, UninstallArgs()), 0)
        self.assertTrue(paths.env_file.exists())
        self.assertFalse(paths.state_file.exists())

    def test_dry_run_does_not_create_state_or_targets(self):
        temp, repo, env = self.make_fixture()
        self.addCleanup(temp.cleanup)
        paths = setup_config.resolve_paths(repo, env)
        dry = Args()
        dry.dry_run = True
        self.assertEqual(setup_config.install(paths, dry, env), 0)
        self.assertFalse(paths.state_file.exists())
        self.assertFalse(paths.config.exists())
        self.assertFalse(paths.hooks.exists())

    def test_uninstall_preserves_user_modified_managed_file_and_returns_failure(self):
        temp, repo, env = self.make_fixture()
        self.addCleanup(temp.cleanup)
        paths = setup_config.resolve_paths(repo, env)
        self.assertEqual(setup_config.install(paths, Args(), env), 0)
        paths.bashrc.write_text(paths.bashrc.read_text(encoding="utf-8") + "# user change\n", encoding="utf-8")
        self.assertEqual(setup_config.uninstall(paths, UninstallArgs()), 1)
        self.assertTrue(paths.bashrc.exists())

    def test_uninstall_restores_first_preexisting_files(self):
        temp, repo, env = self.make_fixture()
        self.addCleanup(temp.cleanup)
        paths = setup_config.resolve_paths(repo, env)
        paths.codex_home.mkdir(parents=True)
        original_config = 'model = "gpt"\n'
        original_hooks = '{"hooks":{"Stop":[]}}\n'
        original_bashrc = "# user bashrc\n"
        paths.config.write_text(original_config, encoding="utf-8")
        paths.hooks.write_text(original_hooks, encoding="utf-8")
        paths.bashrc.write_text(original_bashrc, encoding="utf-8")
        self.assertEqual(setup_config.install(paths, Args(), env), 0)
        self.assertEqual(setup_config.uninstall(paths, UninstallArgs()), 0)
        self.assertEqual(paths.config.read_text(encoding="utf-8"), original_config)
        self.assertEqual(paths.hooks.read_text(encoding="utf-8"), original_hooks)
        self.assertEqual(paths.bashrc.read_text(encoding="utf-8"), original_bashrc)


if __name__ == "__main__":
    unittest.main()
