# CausalTrace

CausalTrace is a local Python command-line tool for investigating software regressions.
Version 0.1 imports Git history and JUnit XML into SQLite, shows a project timeline,
and lists changes between a failing test and an earlier passing run on the same
commit or an ancestor commit.

## Try it on Windows

Run these PowerShell commands from the extracted project directory with Python
3.10 or newer and Git on your PATH. Running as a module needs no package installation.

```powershell
python -m causaltrace --version
python -m unittest discover -s tests -v
python -m causaltrace import-git --project demo --repo 'C:\Projects\demo'
python -m causaltrace import-tests --project demo --report 'C:\Reports\report.xml' --commit FULL_COMMIT_HASH --finished-at '2026-11-11T08:00:00+01:00'
python -m causaltrace timeline --project demo
python -m causaltrace analyze --project demo --run 12 --test 'tests.test_config::test_load'
```

Supply your own repository, report, full commit hash, and test completion time.
Import the earlier passing report in the same way. Use the failing run ID from
the timeline and the JUnit testcase's `classname::name` for the comparison.
You can put `--db PATH` before the subcommand to choose a database. The default
is `.causaltrace.sqlite3` in your home directory. Use `python -m pip install .`
if you want the optional installed `causaltrace` entry point.

## Scope

Git imports the history reachable from the current HEAD. To include another
branch, import it from a checkout whose HEAD points to that branch. Shallow
repositories are unsupported. Merge paths are relative to the first parent.
JUnit input is UTF-8 XML up to 16 MiB. The report hash identifies its contents.
The commit and completion time are supplied by the caller.

The CLI reads the input repository and reports. It stores data in its own
SQLite database, scoped by project key. It lists candidate changes with source
references. The comparison cannot establish a cause and does not verify
whether the test ran against a clean checkout.
