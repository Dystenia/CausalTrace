def compare(timeline, run_id, test_id):
    commits = {e["data"]["sha"]: e for e in timeline if e["kind"] == "git_commit"}
    runs = [e for e in timeline if e["kind"] == "test_run"]
    failed = next((e for e in runs if e["id"] == run_id), None)
    if failed is None:
        raise ValueError("Unknown test run for this project.")

    def case(run):
        matches = [
            c for c in run["data"]["cases"]
            if f"{c['classname']}::{c['name']}" == test_id
        ]
        if len(matches) > 1:
            raise ValueError(f"Test ID is ambiguous in run {run['id']}.")
        return matches[0] if matches else None

    failure = case(failed)
    if not failure or failure["status"] not in {"failed", "error"}:
        raise ValueError("The selected test must have failed or errored in this run.")

    def ancestors(sha):
        seen = set()
        pending = [sha]
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            if current not in commits:
                raise ValueError(f"Imported Git history is missing commit {current}.")
            seen.add(current)
            pending.extend(commits[current]["data"]["parents"])
        return seen

    reachable = ancestors(failed["data"]["commit"])
    for run in reversed(runs):
        sha = run["data"]["commit"]
        if run["time"] >= failed["time"] or sha not in reachable:
            continue
        previous = case(run)
        if previous and previous["status"] == "passed":
            changes = reachable - ancestors(sha)
            return failed, failure, run, [
                e for e in timeline
                if e["kind"] == "git_commit" and e["data"]["sha"] in changes
            ]
    return failed, failure, None, []
