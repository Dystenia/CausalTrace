import argparse
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path
from xml.etree.ElementTree import ParseError

from .analysis import compare
from .db import SCHEMA, events
from .imports import import_git, import_tests


def show_run(run):
    print(f"Run {run['id']} | {run['time']} | {run['data']['commit']}")
    print(f"  Report {run['origin']} | SHA-256 {run['fingerprint']}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="causaltrace")
    parser.add_argument("--db", default=str(Path.home() / ".causaltrace.sqlite3"))
    parser.add_argument("--version", action="version", version="CausalTrace 0.2.0")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("import-git", "import-tests", "timeline", "analyze"):
        commands.add_parser(command).add_argument("--project", required=True)
    commands.choices["import-git"].add_argument("--repo", required=True)
    tests = commands.choices["import-tests"]
    for option in ("--report", "--commit", "--finished-at"):
        tests.add_argument(option, required=True)
    analysis = commands.choices["analyze"]
    analysis.add_argument("--run", required=True, type=int)
    analysis.add_argument("--test", required=True, help="classname::name")
    args = parser.parse_args(argv)
    project = args.project.strip()
    if not project:
        parser.error("--project cannot be blank")

    try:
        with closing(sqlite3.connect(args.db)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(SCHEMA)
            if args.command == "import-git":
                count = import_git(connection, project, args.repo)
                print(f"Imported {count} new commit(s).")
            elif args.command == "import-tests":
                count = import_tests(connection, project, args.report, args.commit, args.finished_at)
                print(f"Imported {count} new test run(s).")
            elif args.command == "timeline":
                timeline = events(connection, project)
                if not timeline:
                    print("No events for this project.")
                for event in timeline:
                    data = event["data"]
                    if event["kind"] == "git_commit":
                        print(f"{event['time']} | Git {data['sha']} | {data['subject']}")
                        print(f"  Repository {event['origin']} | imported HEAD {event['fingerprint']}")
                    else:
                        show_run(event)
                        counts = Counter(case["status"] for case in data["cases"])
                        print("  " + ", ".join(f"{count} {status}" for status, count in sorted(counts.items())))
            else:
                failed, failure, previous, changes = compare(
                    events(connection, project), args.run, args.test
                )
                print(f"Observation: {args.test} {failure['status']}")
                show_run(failed)
                if failure["details"]:
                    print(f"  {failure['details']}")
                if previous:
                    print("Last known passing run on the same commit or an ancestor:")
                    show_run(previous)
                    print("Changes between tested commits (oldest timestamp first):")
                    if not changes:
                        print("  Both runs reference the same commit.")
                    for event in changes:
                        data = event["data"]
                        print(f"  {data['sha']} | {data['subject']}")
                        print(f"    Repository {event['origin']} | imported HEAD {event['fingerprint']}")
                        if len(data["parents"]) > 1:
                            print("    Paths relative to the first parent:")
                        for path in data["paths"]:
                            print(f"    {path}")
                else:
                    print("No earlier passing run on the same commit or an ancestor.")
                print("Commit assignments are supplied at import. Confirmed cause: none.")
    except (OSError, sqlite3.Error, ValueError, ParseError) as exc:
        print(f"causaltrace: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
