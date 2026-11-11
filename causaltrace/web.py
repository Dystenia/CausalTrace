"""Read-only browser timeline for a local CausalTrace database."""

import argparse
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .analysis import compare
from .db import events


def create_app(database: Path) -> FastAPI:
    uri = f"{database.resolve().as_uri()}?mode=ro"
    templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.get("/")
    def timeline(request: Request, project: str | None = None):
        projects = []
        rows = []
        selected = project
        error = None
        status = 200
        try:
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                projects = [
                    key for (key,) in connection.execute(
                        "SELECT DISTINCT project FROM events ORDER BY project"
                    )
                ]
                if selected is None and projects:
                    selected = projects[0]
                if selected in projects:
                    rows = events(connection, selected)
                elif selected is not None:
                    error = "Project not found in this database."
                    status = 404
            for row in rows:
                if row["kind"] == "test_run":
                    row["counts"] = Counter(case["status"] for case in row["data"]["cases"])
        except (sqlite3.Error, ValueError, KeyError, TypeError):
            error = "Could not read this CausalTrace database. Check the file and try again."
            status = 503

        return templates.TemplateResponse(
            request=request, name="timeline.html", status_code=status,
            context={"projects": projects, "selected": selected, "rows": rows, "error": error},
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/runs/{run_id}")
    def run_detail(request: Request, run_id: int, project: str):
        run = None
        error = None
        status = 200
        try:
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                run = next(iter(events(connection, project, test_run_id=run_id)), None)
            if run is None:
                error = "Test run not found in this project."
                status = 404
        except (sqlite3.Error, ValueError):
            error = "Could not read this CausalTrace database. Check the file and try again."
            status = 503

        return templates.TemplateResponse(
            request=request, name="run.html", status_code=status,
            context={"run": run, "run_id": run_id, "project": project, "error": error},
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/runs/{run_id}/compare")
    def run_compare(request: Request, run_id: int, project: str, test: str):
        failed = previous = None
        changes = []
        error = None
        status = 200
        try:
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                rows = events(connection, project)
        except (sqlite3.Error, ValueError):
            error = "Could not read this CausalTrace database. Check the file and try again."
            status = 503
        else:
            if not any(row["id"] == run_id and row["kind"] == "test_run" for row in rows):
                error = "Test run not found in this project."
                status = 404
            else:
                try:
                    failed, _, previous, changes = compare(rows, run_id, test)
                except ValueError as exc:
                    error = str(exc)
                    status = 422

        return templates.TemplateResponse(
            request=request, name="compare.html", status_code=status,
            context={"run_id": run_id, "project": project, "test": test, "failed": failed,
                     "previous": previous, "changes": changes, "error": error},
            headers={"Cache-Control": "no-store"},
        )

    return app


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path.home() / ".causaltrace.sqlite3")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error(f"Database file not found: {args.db}")
    uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
