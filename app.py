"""Source-linked sprint planning with explicit review and atomic local publishing."""
from contextlib import asynccontextmanager
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from integrations import IntegrationError, extract_proposals, llm_configured, jira_configured, create_jira_issue, verify_jira_issue

ROOT = Path(__file__).resolve().parent
SAMPLE = """Sprint planning — sample team, fictional discussion
Asha: I will add request validation to the FastAPI endpoint. Due: 2026-11-05
Kabir: I will write SQL tests for the reporting query. Due: 2026-11-06
Action: Document the Docker setup. Owner: Meera
We should discuss the long-term roadmap next month.
Action: Review the Git branching guide. Owner: Rohan
"""
REFERENCES = {
    "fastapi": ("FastAPI request bodies", "https://fastapi.tiangolo.com/tutorial/body/"),
    "sql": ("SQLite SELECT reference", "https://www.sqlite.org/lang_select.html"),
    "docker": ("Docker build concepts", "https://docs.docker.com/build/concepts/overview/"),
    "git": ("Git branching guide", "https://git-scm.com/book/en/v2/Git-Branching-Branches-in-a-Nutshell"),
    "python": ("Python tutorial", "https://docs.python.org/3/tutorial/"),
}


def extract(transcript):
    tasks = []
    for number, original in enumerate(transcript.splitlines(), 1):
        line = original.strip()
        if not line:
            continue
        owner, title = None, None
        speech = re.match(r"^([\w -]{1,45}):\s*(?:I\s+will|I'll)\s+(.+)$", line, re.I)
        action = re.match(r"^(?:action\s*:|todo\s*:|[-*]\s*\[\s*\])\s*(.+)$", line, re.I)
        if speech:
            owner, title = speech.group(1).strip(), speech.group(2)
        elif action:
            title = action.group(1)
        if not title:
            continue
        metadata = list(re.finditer(r"\b(Owner|Due|Priority)\s*:\s*", title, re.I))
        fields = {}
        for index, match in enumerate(metadata):
            end = metadata[index + 1].start() if index + 1 < len(metadata) else len(title)
            fields[match.group(1).lower()] = title[match.end():end].strip(" .;|")
        owner = fields.get("owner", owner)
        due = fields.get("due", "")
        try:
            due = date.fromisoformat(due).isoformat() if due else ""
        except ValueError:
            due = ""  # Preserve the source line; never invent a valid deadline.
        priority = fields.get("priority", "unknown").lower()
        if priority not in {"high", "medium", "low"}:
            priority = "unknown"
        title = title[:metadata[0].start()].strip(" .;|") if metadata else title.strip(" .;|")
        if len(title) < 4:
            continue
        refs = [{"title": text, "url": url} for word, (text, url) in REFERENCES.items() if re.search(r"\b"+word+r"\b", title, re.I)]
        tasks.append({"id": hashlib.sha256(f"{number}:{line}".encode()).hexdigest()[:12], "title": title[:240], "owner": (owner or "")[:60], "due_date": due, "priority": priority, "source_line": number, "source_quote": original, "references": refs, "acceptance": ""})
        if len(tasks) == 12:
            break
    return tasks


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    engine: Literal["explicit", "semantic"] = "explicit"
    transcript: str = Field(min_length=10, max_length=20000)


class EditedTask(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    id: str = Field(max_length=20)
    title: str = Field(min_length=4, max_length=240)
    owner: str = Field(default="", max_length=60)
    due_date: str = Field(default="", max_length=10, pattern=r"^$|^\d{4}-\d{2}-\d{2}$")
    acceptance: str = Field(default="", max_length=600)
    priority: Literal["unknown", "high", "medium", "low"] = "unknown"

    @field_validator("due_date")
    @classmethod
    def valid_calendar_date(cls, value):
        if value:
            date.fromisoformat(value)
        return value


class Decision(BaseModel):
    version: int = Field(ge=1)
    decision: Literal["approve", "reject"]
    tasks: list[EditedTask] = Field(min_length=1, max_length=12)


class Publish(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=100)


class JiraPublish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    confirm_external_write: Literal[True]


class JiraReconcile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1, max_length=20)
    issue_key: str = Field(pattern=r"^[A-Z][A-Z0-9_]*-\d+$")


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PATCH", "PUT"}:
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 50000:
                return await JSONResponse({"detail": "Request exceeds 50 KB"}, status_code=413)(scope, receive, send)
            if not message.get("more_body", False):
                break
        sent = False
        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        return await self.app(scope, replay, send)


def create_app(db_path=None):
    @asynccontextmanager
    async def lifespan(application):
        path = Path(db_path or os.getenv("SPRINT_DB", "/tmp/sprint-ledger.sqlite"))
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.executescript("CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, owner TEXT, state TEXT, version INTEGER, transcript TEXT, tasks TEXT); CREATE TABLE IF NOT EXISTS issues(id INTEGER PRIMARY KEY AUTOINCREMENT, plan TEXT, task_id TEXT, title TEXT, owner TEXT, due_date TEXT, acceptance TEXT, priority TEXT DEFAULT 'unknown', UNIQUE(plan, task_id)); CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, plan TEXT, action TEXT, details TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP); CREATE TABLE IF NOT EXISTS publishes(plan TEXT, key TEXT, UNIQUE(plan,key));")
        db.execute("CREATE TABLE IF NOT EXISTS jira_exports(plan TEXT, task_id TEXT, state TEXT, issue_key TEXT, issue_url TEXT, marker TEXT, PRIMARY KEY(plan,task_id))")
        db.commit()
        if "priority" not in {column[1] for column in db.execute("PRAGMA table_info(issues)")}:
            db.execute("ALTER TABLE issues ADD COLUMN priority TEXT DEFAULT 'unknown'")
            db.commit()
        application.state.db, application.state.lock = db, threading.RLock()
        yield
        db.close()
    app = FastAPI(title="Sprint Ledger", lifespan=lifespan)
    app.add_middleware(BodyLimit)
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method == "POST" and origin and urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Cross-origin changes are refused"}, status_code=403)
        token = request.cookies.get("sprint_session", "")
        fresh = not re.fullmatch(r"[a-f0-9]{48}", token)
        if fresh:
            token = secrets.token_hex(24)
        request.state.owner = hashlib.sha256(token.encode()).hexdigest()
        response = await call_next(request)
        if fresh:
            response.set_cookie("sprint_session", token, httponly=True, samesite="strict", secure=os.getenv("COOKIE_SECURE")=="true", max_age=86400)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    def get_plan(identifier, owner):
        row = app.state.db.execute("SELECT * FROM plans WHERE id=? AND owner=?", (identifier, owner)).fetchone()
        if row is None:
            raise HTTPException(404, "Plan not found in this browser session")
        result = dict(row)
        result["tasks"] = json.loads(result["tasks"])
        result["events"] = [dict(event) for event in app.state.db.execute("SELECT action,details,created FROM events WHERE plan=? ORDER BY id", (identifier,))]
        result["issues"] = [dict(issue) for issue in app.state.db.execute("SELECT * FROM issues WHERE plan=? ORDER BY id", (identifier,))]
        result["jira_exports"] = [dict(item) for item in app.state.db.execute("SELECT task_id,state,issue_key,issue_url,marker FROM jira_exports WHERE plan=?", (identifier,))]
        result.pop("owner")
        return result

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT / "static/index.html")

    @app.get("/healthz")
    def health():
        return {"status":"ok", "engine":"explicit-action-parser.v1", "llm_enabled":llm_configured(), "external_writes":jira_configured(), "jira_requires_publish_token":True}

    @app.get("/api/sample")
    def sample():
        return {"transcript":SAMPLE}

    @app.post("/api/plans", status_code=201)
    def create(payload: Draft, request: Request):
        try:
            tasks = extract_proposals(payload.transcript) if payload.engine == "semantic" else extract(payload.transcript)
            for task in tasks:
                EditedTask.model_validate(task)
        except (IntegrationError, ValueError) as error:
            raise HTTPException(502 if llm_configured() else 503, "AI extraction failed or is unconfigured; no draft saved") from error
        if not tasks:
            raise HTTPException(422, "No explicit actions recognized. Use 'Action: … Owner: …' or 'Name: I will …'. Nothing was invented.")
        identifier = secrets.token_hex(12)
        with app.state.lock, app.state.db:
            if app.state.db.execute("SELECT COUNT(*) FROM plans WHERE owner=?",(request.state.owner,)).fetchone()[0] >= 20:
                raise HTTPException(429,"This demo session has reached its 20-plan limit")
            app.state.db.execute("INSERT INTO plans VALUES(?,?,'draft',1,?,?)",(identifier,request.state.owner,payload.transcript,json.dumps(tasks)))
            app.state.db.execute("INSERT INTO events(plan,action,details) VALUES(?,'draft_created',?)",(identifier,f"{len(tasks)} {payload.engine} action proposals; human review required"))
            return get_plan(identifier,request.state.owner)

    @app.get("/api/plans/{identifier}")
    def get(identifier: str, request: Request):
        with app.state.lock:
            return get_plan(identifier,request.state.owner)

    @app.post("/api/plans/{identifier}/review")
    def review(identifier: str, payload: Decision, request: Request):
        with app.state.lock, app.state.db:
            plan = get_plan(identifier,request.state.owner)
            if plan["version"] != payload.version or plan["state"] != "draft":
                raise HTTPException(409,"This draft has already changed. Reload it before reviewing.")
            old = {task["id"]:task for task in plan["tasks"]}
            if len({task.id for task in payload.tasks}) != len(payload.tasks) or any(task.id not in old for task in payload.tasks):
                raise HTTPException(422,"Task identities must be unique and belong to this draft")
            tasks = [{**old[task.id],**task.model_dump()} for task in payload.tasks]
            state = "approved" if payload.decision=="approve" else "rejected"
            changed = app.state.db.execute("UPDATE plans SET state=?,version=version+1,tasks=? WHERE id=? AND version=? AND state='draft'",(state,json.dumps(tasks),identifier,payload.version))
            if changed.rowcount != 1:
                raise HTTPException(409,"This draft changed during review. Reload it before deciding.")
            app.state.db.execute("INSERT INTO events(plan,action,details) VALUES(?,?,?)",(identifier,state,"Human browser-session decision; reviewer identity is not authenticated"))
            return get_plan(identifier,request.state.owner)

    @app.post("/api/plans/{identifier}/publish")
    def publish(identifier: str, payload: Publish, request: Request):
        with app.state.lock:
            db = app.state.db
            try:
                db.execute("BEGIN IMMEDIATE")
                plan = get_plan(identifier,request.state.owner)
                if plan["state"] not in {"approved","published"}:
                    raise HTTPException(409,"Approve this draft before creating local issues")
                if plan["state"] == "approved":
                    for task in plan["tasks"]:
                        db.execute("INSERT OR IGNORE INTO issues(plan,task_id,title,owner,due_date,acceptance,priority) VALUES(?,?,?,?,?,?,?)",(identifier,task["id"],task["title"],task["owner"],task["due_date"],task["acceptance"],task.get("priority", "unknown")))
                    db.execute("UPDATE plans SET state='published',version=version+1 WHERE id=?",(identifier,))
                    db.execute("INSERT INTO events(plan,action,details) VALUES(?,'published','Created local issues only; no Jira or email action')",(identifier,))
                db.execute("INSERT OR IGNORE INTO publishes VALUES(?,?)",(identifier,payload.idempotency_key))
                db.commit()
            except Exception:
                db.rollback()
                raise
            return get_plan(identifier,request.state.owner)
    @app.post("/api/plans/{identifier}/publish/jira")
    def publish_jira(identifier: str, payload: JiraPublish, request: Request):
        token = request.headers.get("x-publish-token", "")
        configured_token = os.getenv("SPRINT_JIRA_PUBLISH_TOKEN", "")
        if not jira_configured():
            raise HTTPException(503, "Jira publishing is not configured")
        if not configured_token or not secrets.compare_digest(token, configured_token):
            raise HTTPException(403, "A server-authorized publish token is required")
        with app.state.lock:
            db = app.state.db
            plan = get_plan(identifier, request.state.owner)
            if plan["state"] not in {"approved", "published"} or plan["version"] != payload.expected_version:
                raise HTTPException(409, "Approve this exact plan version before Jira publishing")
            for task in plan["tasks"]:
                saved = db.execute("SELECT * FROM jira_exports WHERE plan=? AND task_id=?", (identifier, task["id"])).fetchone()
                if saved and saved["state"] == "created":
                    continue
                if saved:
                    raise HTTPException(409, "An earlier Jira outcome is uncertain. Reconcile the export marker manually before proceeding.")
                marker = "sprint-ledger-" + hashlib.sha256(f"{identifier}:{task['id']}".encode()).hexdigest()[:24]
                # Commit intent before external I/O: crash/timeout must never silently trigger a duplicate POST.
                db.execute("INSERT INTO jira_exports VALUES(?,?,'inflight',NULL,NULL,?)", (identifier, task["id"], marker))
                db.commit()
                try:
                    issue = create_jira_issue(task, marker)
                except IntegrationError as error:
                    db.execute("UPDATE jira_exports SET state='uncertain' WHERE plan=? AND task_id=?", (identifier, task["id"]))
                    db.commit()
                    raise HTTPException(502, str(error)) from error
                db.execute("UPDATE jira_exports SET state='created',issue_key=?,issue_url=? WHERE plan=? AND task_id=?", (issue["key"], issue["url"], identifier, task["id"]))
                db.commit()
            db.execute("INSERT INTO events(plan,action,details) VALUES(?,'jira_exported','Created Jira issues after explicit token-authorized approval')", (identifier,))
            db.commit()
            return get_plan(identifier, request.state.owner)

    @app.post("/api/plans/{identifier}/reconcile/jira")
    def reconcile_jira(identifier: str, payload: JiraReconcile, request: Request):
        token = request.headers.get("x-publish-token", "")
        if not jira_configured():
            raise HTTPException(503, "Jira publishing is not configured")
        if not secrets.compare_digest(token, os.environ["SPRINT_JIRA_PUBLISH_TOKEN"]):
            raise HTTPException(403, "A server-authorized publish token is required")
        with app.state.lock:
            get_plan(identifier, request.state.owner)
            row = app.state.db.execute("SELECT * FROM jira_exports WHERE plan=? AND task_id=?", (identifier, payload.task_id)).fetchone()
            if not row or row["state"] not in {"inflight", "uncertain"}:
                raise HTTPException(409, "Only an uncertain export can be reconciled")
            try:
                issue = verify_jira_issue(payload.issue_key, row["marker"])
            except IntegrationError as error:
                raise HTTPException(502, str(error)) from error
            with app.state.db:
                app.state.db.execute("UPDATE jira_exports SET state='created',issue_key=?,issue_url=? WHERE plan=? AND task_id=?", (issue["key"], issue["url"], identifier, payload.task_id))
                app.state.db.execute("INSERT INTO events(plan,action,details) VALUES(?,'jira_reconciled',?)", (identifier, "Verified exact export marker on " + issue["key"]))
            return get_plan(identifier, request.state.owner)

    return app


app = create_app()
