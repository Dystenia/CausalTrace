# CausalTrace

CausalTrace is a local tool for investigating software regressions. It brings Git history and test results into a timeline so you can see what changed between a passing test run and a later failure.

For example, if a configuration test passes on one commit and fails on a descendant commit, CausalTrace will show the intervening commits and changed files as leads for investigation. The timeline alone cannot establish which change caused the failure.

## Planned for v0.1

- Import local Git history and JUnit XML test reports.
- Store events in SQLite and show a timeline for each project.
- Compare a failing test with its last known passing run on the same commit or an ancestor commit.

The first version is planned as a Python command-line tool. Imports will read from the source repository and test reports without modifying them.
