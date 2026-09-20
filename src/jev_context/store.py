from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from pathlib import Path
from .util import canonical, digest, redact, require_text

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, session TEXT NOT NULL, harness TEXT NOT NULL,
 origin TEXT NOT NULL, content TEXT NOT NULL, safe_content TEXT NOT NULL, sha256 TEXT NOT NULL,
 metadata TEXT NOT NULL, created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS source_scope ON sources(workspace, created DESC);
CREATE TABLE IF NOT EXISTS features(source_id TEXT PRIMARY KEY, data TEXT NOT NULL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pins(workspace TEXT NOT NULL, source_id TEXT NOT NULL, PRIMARY KEY(workspace,source_id));
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, workspace TEXT NOT NULL, session TEXT NOT NULL,
 harness TEXT NOT NULL, kind TEXT NOT NULL, source_id TEXT, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots(workspace TEXT NOT NULL, session TEXT NOT NULL, harness TEXT NOT NULL,
 fingerprint TEXT NOT NULL, messages TEXT NOT NULL, created REAL NOT NULL,
 PRIMARY KEY(workspace,session,harness));
CREATE TABLE IF NOT EXISTS prune_plans(id TEXT PRIMARY KEY, workspace TEXT NOT NULL, session TEXT NOT NULL,
 harness TEXT NOT NULL, fingerprint TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS views(workspace TEXT NOT NULL, session TEXT NOT NULL, harness TEXT NOT NULL,
 excluded TEXT NOT NULL, generation INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(workspace,session,harness));
CREATE TABLE IF NOT EXISTS links(workspace TEXT NOT NULL, source TEXT NOT NULL, relation TEXT NOT NULL,
 target TEXT NOT NULL, PRIMARY KEY(workspace,source,relation,target));
"""


class Store:
    def __init__(self, home: Path):
        self.home = home
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = home / "memory.sqlite3"
        if path.is_symlink():
            raise ValueError("Refusing symlinked memory database")
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript(SCHEMA)
        self.fts = True
        try:
            self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS source_fts USING fts5(id UNINDEXED, workspace UNINDEXED, text)")
        except sqlite3.OperationalError:
            self.fts = False
        self.db.commit()
        if os.name != "nt":
            os.chmod(path, 0o600)
            for sidecar in (Path(str(path) + "-wal"), Path(str(path) + "-shm")):
                if sidecar.exists():
                    os.chmod(sidecar, 0o600)

    def close(self):
        self.db.close()

    def capture(self, workspace: str, content: str, *, session: str = "manual", harness: str = "manual",
                origin: str = "capture", metadata: dict | None = None) -> dict:
        require_text(content, "content")
        meta = metadata or {}
        sha = digest(content)
        ident = "src_" + digest(canonical([workspace, session, harness, origin, sha]))
        safe = redact(content)
        now = time.time()
        with self.db:
            cur = self.db.execute("INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?,?,?,?)", (
                ident, workspace, session, harness, origin, content, safe, sha, canonical(meta), now))
            if cur.rowcount and self.fts:
                self.db.execute("INSERT INTO source_fts(id,workspace,text) VALUES(?,?,?)", (ident, workspace, safe))
        return {"ref": ident, "sha256": sha, "characters": len(content), "duplicate": cur.rowcount == 0}

    def get(self, workspace: str, ident: str) -> dict:
        row = self.db.execute("SELECT * FROM sources WHERE workspace=? AND id=?", (workspace, ident)).fetchone()
        if row is None:
            raise KeyError("Source not found in this workspace")
        data = dict(row)
        if digest(data["content"]) != data["sha256"]:
            raise ValueError("Source integrity check failed")
        return data

    def candidates(self, workspace: str, query: str, limit: int = 40) -> list[dict]:
        words = re.findall(r"[\w]+", query, re.UNICODE)[:24]
        rows = []
        if words and self.fts:
            match = " OR ".join('"' + word.replace('"', '""') + '"' for word in words)
            rows = self.db.execute("""SELECT s.*, bm25(source_fts) AS rank FROM source_fts
                JOIN sources s ON s.id=source_fts.id WHERE source_fts MATCH ? AND s.workspace=?
                ORDER BY rank LIMIT ?""", (match, workspace, limit)).fetchall()
        elif words:
            recent = self.db.execute("SELECT *, 0 AS rank FROM sources WHERE workspace=? ORDER BY created DESC LIMIT 1000", (workspace,)).fetchall()
            rows = sorted((r for r in recent if any(w.lower() in r["safe_content"].lower() for w in words)),
                          key=lambda r: -sum(r["safe_content"].lower().count(w.lower()) for w in words))[:limit]
        else:
            rows = self.db.execute("SELECT *,0 AS rank FROM sources WHERE workspace=? ORDER BY created DESC LIMIT ?", (workspace, limit)).fetchall()
        result = [dict(r) for r in rows]
        existing = {r["id"] for r in result}
        pins = self.db.execute("SELECT s.*, 0 AS rank FROM sources s JOIN pins p ON s.id=p.source_id WHERE p.workspace=? AND s.workspace=?", (workspace,workspace)).fetchall()
        for row in pins:
            if row["id"] not in existing:
                result.append(dict(row))
        pinned = {r["id"] for r in pins}
        for row in result:
            row["pinned"] = row["id"] in pinned
        return result

    def routed_candidates(self, workspace: str, query: str) -> list[dict]:
        """Union lexical, cached typed roles, pins, and one-hop explicit relations.

        Routing weights are heuristics, not calibrated probabilities. This does not
        run a network call or infer causal edges from prose.
        """
        rows = self.candidates(workspace, query)
        words = set(re.findall(r"\w+", query.lower()))
        role_terms = {
            "constraint": {"constraint", "constraints", "requirement", "requirements", "must"},
            "decision": {"decision", "decisions", "rationale", "why", "chose"},
            "failure": {"failure", "failed", "error", "errors", "bug", "broken"},
            "attempt": {"attempt", "attempts", "tried", "previous", "solution"},
            "result": {"result", "results", "test", "tests", "benchmark", "outcome"},
        }
        roles = [role for role, terms in role_terms.items() if words & terms]
        features = {}
        # Bounded scan for the alpha implementation. A larger deployment needs a typed index.
        cached = self.db.execute("""SELECT s.*,f.data FROM sources s JOIN features f ON f.source_id=s.id
            WHERE s.workspace=? ORDER BY s.created DESC LIMIT 500""", (workspace,)).fetchall()
        typed = []
        for source in cached:
            try:
                feature = json.loads(source["data"])
                if feature.get("question_version") != "semantic-memory-v1": continue
                if feature.get("source_sha256") != source["sha256"]: continue
                distribution = feature["answers"]["kind"]["probabilities"]
                score = max((float(distribution.get(role, 0)) for role in roles), default=0.)
                features[source["id"]] = (score, distribution)
                if score >= .35:
                    typed.append((score, dict(source)))
            except (KeyError, TypeError, ValueError):
                continue
        existing = {r["id"] for r in rows}
        for _, source in sorted(typed, key=lambda t:-t[0])[:16]:
            if source["id"] not in existing:
                source["pinned"] = False
                rows.append(source); existing.add(source["id"])
        seeds = [r["id"] for r in rows[:12]]
        if seeds:
            placeholders = ",".join("?" for _ in seeds)
            neighbors = self.db.execute(f"""SELECT s.* FROM sources s WHERE s.workspace=? AND s.id IN (
                SELECT target FROM links WHERE workspace=? AND source IN ({placeholders})
                UNION SELECT source FROM links WHERE workspace=? AND target IN ({placeholders})
            ) ORDER BY s.created DESC LIMIT 16""", [workspace,workspace,*seeds,workspace,*seeds]).fetchall()
            for neighbor in neighbors:
                if neighbor["id"] not in existing:
                    row = dict(neighbor); row.update(pinned=False, linked=True)
                    rows.append(row); existing.add(row["id"])
        for row in rows:
            score, distribution = features.get(row["id"], (0.,None))
            row["typed_routing_score"] = score
            row["kind_distribution"] = distribution
        return rows

    def pin(self, workspace: str, ident: str, enabled: bool = True) -> dict:
        self.get(workspace, ident)
        with self.db:
            if enabled:
                self.db.execute("INSERT OR IGNORE INTO pins VALUES(?,?)", (workspace, ident))
            else:
                self.db.execute("DELETE FROM pins WHERE workspace=? AND source_id=?", (workspace, ident))
        return {"ref": ident, "pinned": enabled}

    def stats(self, workspace: str) -> dict:
        row = self.db.execute("SELECT count(*) AS sources,coalesce(sum(length(content)),0) AS characters FROM sources WHERE workspace=?", (workspace,)).fetchone()
        sessions = self.db.execute("SELECT session,harness,count(*) AS sources,max(created) AS last_seen FROM sources WHERE workspace=? GROUP BY session,harness ORDER BY last_seen DESC LIMIT 20", (workspace,)).fetchall()
        return {**dict(row), "fts5": self.fts, "sessions": [dict(r) for r in sessions]}

    def feature(self, ident: str) -> dict | None:
        row = self.db.execute("SELECT data FROM features WHERE source_id=?", (ident,)).fetchone()
        return json.loads(row[0]) if row else None

    def put_feature(self, ident: str, data: dict):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO features VALUES(?,?,?)", (ident, canonical(data), time.time()))
