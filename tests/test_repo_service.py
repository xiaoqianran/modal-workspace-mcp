import unittest

from modal_workspace_mcp.repo_service import (
    _git_auth_prefix,
    normalize_github_repository,
    validate_git_ref,
    validate_repo_path,
)
from modal_workspace_mcp.workspace_service import validate_workspace_id


class RepoServiceValidationTest(unittest.TestCase):
    def test_normalize_owner_repo(self):
        self.assertEqual(
            normalize_github_repository("openai/openai-python"),
            ("openai/openai-python", "https://github.com/openai/openai-python.git"),
        )

    def test_normalize_https_git_url(self):
        self.assertEqual(
            normalize_github_repository("https://github.com/xiaoqianran/modal-workspace-mcp.git"),
            (
                "xiaoqianran/modal-workspace-mcp",
                "https://github.com/xiaoqianran/modal-workspace-mcp.git",
            ),
        )

    def test_reject_non_github_or_credential_urls(self):
        bad = (
            "https://evil.example/a/b",
            "https://token@github.com/a/b.git",
            "https://github.com/a/b?token=x",
            "https://github.com/a/b#frag",
            "https://github.com/a/b/c",
            "../../etc",
        )
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_github_repository(value)

    def test_git_ref_validation(self):
        valid = (
            "main",
            "feature/realtime-workspace",
            "v0.5.0",
            "30335ab6fbce79e9151fc084111678e1b2be3358",
            "refs/tags/v1.0.0",
        )
        for value in valid:
            with self.subTest(value=value):
                self.assertEqual(validate_git_ref(value), value)

        bad = (
            "-dangerous",
            "a..b",
            "HEAD@{1}",
            "feature:bad",
            "a//b",
            "refs/heads/main.lock",
            "/main",
            "has space",
        )
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_git_ref(value)

    def test_repo_path_must_stay_under_workspace(self):
        self.assertEqual(validate_repo_path(None), "/workspace/repo")
        self.assertEqual(validate_repo_path("/workspace/src/project"), "/workspace/src/project")
        for value in ("/", "/etc/project", "/workspace"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_repo_path(value)

    def test_private_git_auth_never_embeds_token_value(self):
        prefix = _git_auth_prefix(True)
        self.assertIn("$GH_TOKEN", prefix)
        self.assertIn("GIT_ASKPASS", prefix)
        self.assertNotIn("ghp_", prefix)
        self.assertEqual(_git_auth_prefix(False), "")


class WorkspaceValidationTest(unittest.TestCase):
    def test_workspace_id_validation(self):
        good = "ws-" + "a" * 32
        self.assertEqual(validate_workspace_id(good), good)
        for value in ("sb-" + "a" * 32, "ws-short", "ws-" + "g" * 32):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_workspace_id(value)


if __name__ == "__main__":
    unittest.main()
