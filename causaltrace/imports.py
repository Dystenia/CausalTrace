import hashlib
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from .db import save, utc


def import_git(connection, project, path):
    repo = str(Path(path).resolve(strict=True))

    def git(*args):
        env = {
            key: value for key, value in os.environ.items()
            if not key.upper().startswith("GIT_")
        }
        env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1",
                   GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
        result = subprocess.run(
            ["git", "-C", repo, *args], capture_output=True, env=env,
        )
        if result.returncode:
            raise ValueError(result.stderr.decode("utf-8", "replace").strip()
                             or "Git command failed.")
        return result.stdout

    head = git("rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    if git("rev-parse", "--is-shallow-repository").strip() == b"true":
        raise ValueError("A complete Git history is required. Shallow repositories are unsupported.")
    raw = git("log", "--no-notes", "--no-show-signature", "--encoding=UTF-8",
              "-z", "--format=%H%x00%P%x00%cI%x00%s", head, "--")
    fields = raw.decode("utf-8", "replace").split("\0")[:-1]
    records = []
    for index in range(0, len(fields), 4):
        sha, parent_list, time, subject = fields[index:index + 4]
        parents = parent_list.split()
        args = (parents[0], sha) if parents else ("--root", sha)
        paths = git("diff-tree", "--no-commit-id", "--no-renames", "--no-ext-diff",
                    "--name-only", "-r", "-z", *args, "--")
        records.append((sha, utc(time), {
            "sha": sha, "parents": parents, "subject": subject,
            "paths": [path.decode("utf-8", "backslashreplace")
                      for path in paths.split(b"\0") if path],
        }))
    return save(connection, project, "git_commit", repo, head, records)


def import_tests(connection, project, path, commit, finished_at):
    commit = commit.lower()
    if not connection.execute(
        "SELECT 1 FROM events WHERE project=? AND kind='git_commit' AND event_key=?",
        (project, commit),
    ).fetchone():
        raise ValueError("Import the Git history first and provide a known full commit hash.")
    report = Path(path).resolve(strict=True)
    # Bound the input and reject DTD/entity declarations before parsing UTF-8 XML.
    with report.open("rb") as stream:
        raw = stream.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("JUnit report exceeds 16 MiB.")
    xml = raw.decode("utf-8-sig")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", xml, re.IGNORECASE) or "\0" in xml:
        raise ValueError("JUnit reports must be UTF-8 XML without DTD or entity declarations.")
    root = ET.fromstring(xml)
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("Expected a JUnit testsuite or testsuites element.")
    cases = []
    for case in root.iter("testcase"):
        name = case.get("name")
        if not name:
            raise ValueError("JUnit testcase is missing its name.")
        status, details = "passed", ""
        for tag, outcome in (("error", "error"), ("failure", "failed"), ("skipped", "skipped")):
            marker = case.find(tag)
            if marker is not None:
                status = outcome
                details = "\n".join(filter(None, (marker.get("message"), "".join(marker.itertext()).strip())))
                break
        cases.append(dict(classname=case.get("classname", ""), name=name,
                          status=status, details=details))
    time = utc(finished_at)
    fingerprint = hashlib.sha256(raw).hexdigest()
    key = f"{fingerprint}:{commit}:{time}"
    return save(connection, project, "test_run", str(report), fingerprint,
                [(key, time, dict(commit=commit, cases=cases))])
