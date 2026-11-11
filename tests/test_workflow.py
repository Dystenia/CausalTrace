import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "repo space"
        self.repo.mkdir()
        self.db = self.root / "events.sqlite"
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "CausalTrace Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.base = self.commit("basis.txt")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True).strip()

    def commit(self, name):
        (self.repo / name).write_text("test", encoding="utf-8")
        self.git("add", "--", name)
        self.git("commit", "-qm", name)
        return self.git("rev-parse", "HEAD")

    def cli(self, command, *args, project="demo", status=0):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "causaltrace", "--db", str(self.db),
             command, "--project", project, *args],
            capture_output=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, status, result.stderr)
        return result.stdout if status == 0 else result.stderr

    def git_import(self, project="demo"):
        return self.cli("import-git", "--repo", str(self.repo), project=project)

    def report(self, sha, day, xml, status=0):
        path = self.root / "junit.xml"
        path.write_text(xml, encoding="utf-8")
        return self.cli("import-tests", "--report", str(path), "--commit", sha,
                        "--finished-at", f"2026-01-{day:02d}T10:00:00Z", status=status)

    def run_id(self):
        with closing(sqlite3.connect(self.db)) as db:
            return str(db.execute("SELECT max(id) FROM events WHERE kind='test_run'").fetchone()[0])

    def analyze(self):
        return self.cli("analyze", "--run", self.run_id(), "--test", "config::loads")

    def test_merge_and_divergent_pass(self):
        self.git("switch", "-qc", "unrelated")
        unrelated = self.commit("unrelated.txt")
        self.git_import()
        self.git("switch", "-q", "main")
        self.git("switch", "-qc", "feature")
        feature = self.commit("größere Änderung.txt")
        self.git("switch", "-q", "main")
        self.git("merge", "--no-ff", "-qm", "Merge feature", "feature")
        head = self.git("rev-parse", "HEAD")
        (self.repo / "untouched.txt").write_text("untracked", encoding="utf-8")
        before = self.git("status", "--porcelain")
        self.assertIn("2 new commit", self.git_import())
        self.assertIn("0 new commit", self.git_import())
        self.assertEqual(before, self.git("status", "--porcelain"))
        self.assertEqual(head, self.git("rev-parse", "HEAD"))
        self.report(self.base, 1, PASS)
        self.report(unrelated, 2, PASS)
        self.report(head, 3, FAIL)
        self.assertIn("0 new test run", self.report(head, 3, FAIL))
        self.assertIn("1 failed", self.cli("timeline"))
        output = self.analyze()
        for value in (self.base, feature, head, "größere Änderung.txt",
                      "first parent", "broken", "Confirmed cause: none."):
            self.assertIn(value, output)
        self.assertNotIn(unrelated, output)
        self.assertEqual(output, self.analyze())
        self.assertIn("No events", self.cli("timeline", project="other"))
        self.assertIn("3 new commit", self.git_import(project="other"))
        self.assertNotIn("Run ", self.cli("timeline", project="other"))

    def test_missing_baseline_and_same_commit(self):
        self.git_import()
        self.report(self.base, 2, FAIL)
        self.assertIn("No earlier passing run", self.analyze())
        self.report(self.base, 1, PASS)
        output = self.cli("analyze", "--run", "2", "--test", "config::loads")
        self.assertIn("Both runs reference the same commit.", output)

    def test_invalid_import_leaves_no_test_events(self):
        self.git_import()
        self.report(self.base, 1, "<broken", status=1)
        self.report("0" * 40, 1, PASS, status=1)
        self.report(self.base, 1, '<!DOCTYPE testsuite><testsuite/>', status=1)
        self.assertNotIn("Run ", self.cli("timeline"))
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(1, db.execute("SELECT count(*) FROM sources").fetchone()[0])

    def test_junit_outcomes_and_ambiguity(self):
        self.git_import()
        self.report(self.base, 1, """<testsuites><testsuite>
            <testcase classname="config" name="loads"><error/></testcase>
            <testcase classname="config" name="loads"><skipped/></testcase>
        </testsuite></testsuites>""")
        self.assertIn("1 error, 1 skipped", self.cli("timeline"))
        self.assertIn("ambiguous", self.cli("analyze", "--run", self.run_id(),
                                           "--test", "config::loads", status=1))


PASS = '<testsuite><testcase classname="config" name="loads"/></testsuite>'
FAIL = ('<testsuite><testcase classname="config" name="loads">'
        '<failure message="broken"/></testcase></testsuite>')
