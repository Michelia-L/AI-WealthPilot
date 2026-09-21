"""Fast, dependency-free regression tests for CI routing."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ci_scope import ALL_JOBS, changed_paths, event_jobs, main, select_jobs


class ScopeTests(unittest.TestCase):
    def test_changed_path_matrix(self):
        cases = [
            (["README.md", "AGENTS.md", "docs/authorization.md"], set()),
            (["web/AGENTS.md", "web/README.md"], set()),
            (["guide/index.md", "mkdocs.yml"], {"docs"}),
            (["web/src/app/page.tsx"], {"web", "e2e"}),
            (["web/package-lock.json"], {"web", "e2e"}),
            (["api/routes/ips.py"], {"python", "e2e"}),
            (["src/agents/prompt.md"], {"python", "e2e"}),
            (["tests/test_api.py"], {"python", "e2e"}),
            (["validation/portfolio/evaluator.py"], {"python", "e2e"}),
            (["docs/ips_reference/cme_fallback.json"], {"python", "e2e"}),
            (["docs/ips_reference/ips_example_moderate.md"], {"python", "e2e"}),
            (["web/src/app/page.tsx", "api/main.py"], {"python", "web", "e2e"}),
            (["guide/index.md", "api/main.py"], {"docs", "python", "e2e"}),
            (["requirements.txt"], ALL_JOBS),
            (["requirements-dev.txt"], ALL_JOBS),
            (["pyproject.toml"], ALL_JOBS),
            ([".github/workflows/ci.yml"], ALL_JOBS),
            ([".github/scripts/ci_scope.py"], ALL_JOBS),
            (["new-directory/example.md"], ALL_JOBS),
            ([], ALL_JOBS),
        ]
        for paths, expected in cases:
            with self.subTest(paths=paths):
                self.assertEqual(select_jobs(paths), expected)

    def test_main_manual_and_missing_refs_run_everything(self):
        for event, base, head in [
            ("push", "base", "head"),
            ("workflow_dispatch", "", ""),
            ("pull_request", "", "head"),
            ("pull_request", "base", ""),
        ]:
            with self.subTest(event=event, base=base, head=head):
                self.assertEqual(event_jobs(event, base, head), ALL_JOBS)

    def test_diff_failure_runs_everything(self):
        with patch(
            "ci_scope.changed_paths",
            side_effect=subprocess.CalledProcessError(1, "git"),
        ):
            self.assertEqual(event_jobs("pull_request", "base", "head"), ALL_JOBS)

    def test_outputs_include_explicit_false_values(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            with (
                patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}),
                patch("ci_scope.event_jobs", return_value=frozenset({"docs"})),
            ):
                main()
            self.assertEqual(
                output.read_text(), "docs=true\ne2e=false\npython=false\nweb=false\n"
            )

    def test_git_diff_uses_pr_merge_base_and_both_sides_of_rename(self):
        with tempfile.TemporaryDirectory() as directory:

            def git(*args):
                return subprocess.check_output(
                    ["git", "-C", directory, *args], text=True
                ).strip()

            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            root = Path(directory)
            (root / "src").mkdir()
            (root / "src/original.py").write_text("original\n")
            (root / "src/deleted.py").write_text("deleted\n")
            git("add", ".")
            git("commit", "-qm", "base")
            initial = git("rev-parse", "HEAD")
            # The base branch advances independently; its changes aren't PR changes.
            (root / "unrelated-root-file").write_text("base branch only\n")
            git("add", ".")
            git("commit", "-qm", "base advances")
            base = git("rev-parse", "HEAD")
            git("checkout", "-q", "--detach", initial)
            (root / "docs").mkdir()
            (root / "src/original.py").rename(root / "docs/renamed file\nexample.md")
            (root / "src/deleted.py").unlink()
            git("add", "-A")
            git("commit", "-qm", "move and delete")
            head = git("rev-parse", "HEAD")
            # Use the actual diff implementation against the isolated repository.
            run = subprocess.run
            with patch(
                "ci_scope.subprocess.run",
                side_effect=lambda *args, **kwargs: run(*args, cwd=directory, **kwargs),
            ):
                paths = changed_paths(base, head)
                jobs = event_jobs("pull_request", base, head)
            self.assertCountEqual(
                paths,
                ["src/original.py", "src/deleted.py", "docs/renamed file\nexample.md"],
            )
            self.assertEqual(jobs, {"python", "e2e"})


if __name__ == "__main__":
    unittest.main()
