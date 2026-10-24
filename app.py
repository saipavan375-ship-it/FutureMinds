import csv
import io
import json
import logging
import os
import random
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

import logic

BASE = Path(__file__).parent
QUESTIONS = json.loads((BASE / "data" / "questions.json").read_text(encoding="utf-8"))
RESOURCES = json.loads((BASE / "data" / "resources.json").read_text(encoding="utf-8"))
KEY = {q["id"]: q for q in QUESTIONS}
RES_BY_TOPIC = {}
for _r in RESOURCES:
    RES_BY_TOPIC.setdefault(_r["topic"], {})[_r["type"]] = _r

MODULES_LIST = json.loads((BASE / "data" / "modules.json").read_text(encoding="utf-8"))
MODULES = {m["topic"]: m for m in MODULES_LIST}
ITEMS = {it["id"]: dict(it, topic=m["topic"]) for m in MODULES_LIST for it in m.get("practice", [])}

_problems = logic.validate_bank(QUESTIONS, RESOURCES) + logic.validate_modules(MODULES_LIST)
if _problems:  # fail early so a bad answer key never reaches learners
    raise RuntimeError("Question bank problems: " + "; ".join(_problems))

QUIZ_PER_TOPIC = 3  # questions drawn from each topic, so topic coverage stays balanced
NICK = re.compile(r"[A-Za-z0-9_-]{3,30}")
NICK_MSG = "Use a nickname of 3 to 30 letters, numbers, - or _ (not your real name)."

app = Flask(__name__)
app.config["DATABASE"] = str(BASE / "learnwise.db")
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, learner TEXT NOT NULL, taken_at TEXT NOT NULL,
  label TEXT NOT NULL, score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
  topics_json TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS responses(
  id INTEGER PRIMARY KEY AUTOINCREMENT, attempt_id INTEGER NOT NULL REFERENCES attempts(id),
  question_id TEXT NOT NULL, selected INTEGER NOT NULL, is_correct INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS quiz_sessions(
  token TEXT PRIMARY KEY, learner TEXT NOT NULL, question_ids TEXT NOT NULL,
  created_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS task_progress(
  attempt_id INTEGER NOT NULL REFERENCES attempts(id), task_id TEXT NOT NULL,
  completed_at TEXT NOT NULL, PRIMARY KEY(attempt_id, task_id));
CREATE INDEX IF NOT EXISTS idx_attempts_learner ON attempts(learner, taken_at);
CREATE INDEX IF NOT EXISTS idx_responses_attempt ON responses(attempt_id);
CREATE TABLE IF NOT EXISTS xp_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, learner TEXT NOT NULL, event_key TEXT NOT NULL,
  xp INTEGER NOT NULL, label TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(learner, event_key));
CREATE TABLE IF NOT EXISTS badges(
  learner TEXT NOT NULL, badge_id TEXT NOT NULL, earned_at TEXT NOT NULL, PRIMARY KEY(learner, badge_id));
CREATE TABLE IF NOT EXISTS practice_log(
  learner TEXT NOT NULL, item_id TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  solved INTEGER NOT NULL DEFAULT 0, solved_at TEXT, PRIMARY KEY(learner, item_id));
CREATE INDEX IF NOT EXISTS idx_xp_learner ON xp_events(learner, created_at);
"""
DEMO_DATES = ("2026-10-08T09:00:00", "2026-10-12T09:00:00")
DEMO_TOPICS = (
    {"var": [2, 3], "ops": [1, 3], "cond": [1, 3], "loop": [1, 3], "list": [1, 3], "func": [2, 3], "dict": [0, 3], "debug": [1, 3]},
    {"var": [3, 3], "ops": [2, 3], "cond": [2, 3], "loop": [2, 3], "list": [1, 3], "func": [2, 3], "dict": [1, 3], "debug": [2, 3]},
)


@contextmanager
def tx():
    """One connection per use: foreign keys on, commit on success, rollback on error, always closed."""
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    """Safe to run on every start: only adds missing tables, columns and indexes."""
    with tx() as c:
        c.executescript(SCHEMA)
        cols = {r["name"] for r in c.execute("PRAGMA table_info(attempts)")}
        if "is_demo" not in cols:  # migration for databases from the first prototype
            c.execute("ALTER TABLE attempts ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")
            c.execute("UPDATE attempts SET is_demo=1 WHERE taken_at IN (?, ?) "
                      "AND NOT EXISTS (SELECT 1 FROM responses WHERE attempt_id = attempts.id)", DEMO_DATES)


def learner_id(value):
    value = value.strip() if isinstance(value, str) else ""
    return value if NICK.fullmatch(value) else None


def bad(message, code=400):
    return jsonify(error=message), code


def body():
    data = request.get_json(silent=True)  # needs a JSON content type, which blocks plain cross-site form posts
    return data if isinstance(data, dict) else {}


def attempts_for(name):
    with tx() as c:
        rows = c.execute("SELECT id, label, taken_at, topics_json, is_demo FROM attempts "
                         "WHERE learner=? ORDER BY taken_at, id", (name,)).fetchall()
    out = []
    for r in rows:
        t = json.loads(r["topics_json"])
        correct, total = sum(v[0] for v in t.values()), sum(v[1] for v in t.values())
        out.append({"id": r["id"], "d": r["label"], "at": r["taken_at"], "t": t, "demo": bool(r["is_demo"]),
                    "correct": correct, "total": total, "s": logic.percent(correct, total)})
    return out


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def award(c, name, key, xp, label):
    """XP for one real event. The UNIQUE(learner, event_key) rule makes a repeat award impossible."""
    return c.execute("INSERT OR IGNORE INTO xp_events(learner, event_key, xp, label, created_at) VALUES(?,?,?,?,?)",
                     (name, key, xp, label, now_iso())).rowcount == 1


def grant_badges(c, name):
    """Badges come from real records only (never demo attempts). Returns names of newly earned badges."""
    have = {r["badge_id"] for r in c.execute("SELECT badge_id FROM badges WHERE learner=?", (name,))}
    real = []
    for r in c.execute("SELECT topics_json FROM attempts WHERE learner=? AND is_demo=0 ORDER BY taken_at, id", (name,)):
        t = json.loads(r["topics_json"])
        real.append(logic.percent(sum(v[0] for v in t.values()), sum(v[1] for v in t.values())))
    keys = [r["event_key"] for r in c.execute("SELECT event_key FROM xp_events WHERE learner=?", (name,))]
    days = {r["d"] for r in c.execute("SELECT substr(created_at, 1, 10) AS d FROM xp_events WHERE learner=?", (name,))}
    earned = {"first_quiz": len(real) >= 1,
              "personal_best": len(real) >= 2 and real[-1] > max(real[:-1]),
              "first_task": any(k.startswith("task:") for k in keys),
              "first_module": any(k.startswith("module:") for k in keys),
              "three_days": len(days) >= 3}
    new = [b for b, ok in earned.items() if ok and b not in have]
    for b in new:
        c.execute("INSERT OR IGNORE INTO badges(learner, badge_id, earned_at) VALUES(?,?,?)", (name, b, now_iso()))
    return [logic.BADGES[b][0] for b in new]


def task_label(tid):
    if tid == "recheck":
        return "Follow-up quiz"
    k, _, kind = tid.partition("-")
    word = {"lesson": "Review", "example": "Worked example", "challenge": "Challenge"}.get(kind, "Task")
    return f"{word}: {logic.TOPICS.get(k, k)}"


@app.get("/")
def index():
    # Guest-preview data is embedded so the first paint needs no request (and shows only honest zero states).
    boot = {"meta": meta_payload(), "dashboard": dashboard_data(None), "module": module_payload("var", None)}
    return render_template("index.html", boot=boot)


def meta_payload():
    return {"topics": logic.TOPICS, "tips": logic.TIPS, "thresholds": logic.THRESHOLDS, "per_topic": QUIZ_PER_TOPIC}


@app.get("/api/meta")
def meta():
    return jsonify(meta_payload())


@app.post("/api/quiz")
def start_quiz():
    name = learner_id(body().get("learner"))
    if not name:
        return bad(NICK_MSG)
    picked = []
    for topic in logic.TOPICS:
        pool = [q for q in QUESTIONS if q["topic"] == topic]
        picked += random.sample(pool, min(QUIZ_PER_TOPIC, len(pool)))
    random.shuffle(picked)
    token = secrets.token_urlsafe(16)
    with tx() as c:
        c.execute("INSERT INTO quiz_sessions(token, learner, question_ids, created_at) VALUES(?,?,?,?)",
                  (token, name, json.dumps([q["id"] for q in picked]), datetime.now().isoformat(timespec="seconds")))
    public = [{k: q[k] for k in ("id", "topic", "text", "options")} for q in picked]  # never includes the answer
    return jsonify(token=token, questions=public)


@app.post("/api/submit")
def submit():
    data = body()
    name, token, answers = learner_id(data.get("learner")), data.get("token"), data.get("answers")
    if not name:
        return bad(NICK_MSG)
    if not isinstance(token, str) or not isinstance(answers, dict) or not answers:
        return bad("No answers were submitted.")
    with tx() as c:
        s = c.execute("SELECT question_ids, used FROM quiz_sessions WHERE token=? AND learner=?", (token, name)).fetchone()
        if not s:
            return bad("This quiz was not found. Please start a new quiz.", 404)
        if s["used"]:
            return bad("This quiz was already submitted.", 409)
        served = json.loads(s["question_ids"])
        if set(answers) != set(served):
            return bad("Please answer every question before submitting.")
        rows = []
        for qid in served:
            sel, q = answers[qid], KEY[qid]
            if isinstance(sel, bool) or not isinstance(sel, int) or not 0 <= sel < len(q["options"]):
                return bad(f"Invalid answer for {qid}.")
            rows.append((qid, sel, int(sel == q["answer"])))  # correctness is decided here, never in the browser
        if c.execute("UPDATE quiz_sessions SET used=1 WHERE token=? AND used=0", (token,)).rowcount != 1:
            return bad("This quiz was already submitted.", 409)
        topics = logic.score_topics([(KEY[r[0]]["topic"], r[2]) for r in rows])
        correct = sum(r[2] for r in rows)
        now = datetime.now()
        cur = c.execute("INSERT INTO attempts(learner, taken_at, label, score, topics_json, is_demo) VALUES(?,?,?,?,?,0)",
                        (name, now.isoformat(timespec="seconds"), now.strftime("%d %b"),
                         logic.percent(correct, len(rows)), json.dumps(topics)))
        c.executemany("INSERT INTO responses(attempt_id, question_id, selected, is_correct) VALUES(?,?,?,?)",
                      [(cur.lastrowid, *r) for r in rows])
        xp = logic.XP["quiz"] if award(c, name, f"quiz:{cur.lastrowid}", logic.XP["quiz"], "Completed a diagnostic quiz") else 0
        new_badges = grant_badges(c, name)
    app.logger.info("attempt saved: learner=%s attempt=%s correct=%s/%s", name, cur.lastrowid, correct, len(rows))
    review = [{"text": KEY[q]["text"], "yours": KEY[q]["options"][sel], "answer": KEY[q]["options"][KEY[q]["answer"]],
               "explanation": KEY[q]["explanation"], "ok": bool(ok)} for q, sel, ok in rows]
    return jsonify(ok=True, attempt_id=cur.lastrowid, correct=correct, total=len(rows), review=review, xp=xp, badges=new_badges)


@app.get("/api/progress")
def progress():
    name = learner_id(request.args.get("learner"))
    if not name:
        return bad(NICK_MSG)
    with tx() as c:
        log = c.execute("SELECT t.attempt_id, t.task_id, t.completed_at FROM task_progress t "
                        "JOIN attempts a ON a.id = t.attempt_id WHERE a.learner=? ORDER BY t.completed_at DESC", (name,)).fetchall()
    return jsonify(attempts=attempts_for(name), task_log=[dict(r) for r in log])


@app.get("/api/plan")
def plan():
    name = learner_id(request.args.get("learner"))
    if not name:
        return bad(NICK_MSG)
    at = attempts_for(name)
    if not at:
        return jsonify(tasks=[], total_minutes=0)
    a = at[-1]
    tasks = logic.build_plan(a["t"], RES_BY_TOPIC)
    with tx() as c:
        done = {r["task_id"] for r in c.execute("SELECT task_id FROM task_progress WHERE attempt_id=?", (a["id"],))}
    for t in tasks:
        t["completed"] = t["id"] in done
    return jsonify(attempt_id=a["id"], attempt_label=a["d"], demo=a["demo"], tasks=tasks,
                   total_minutes=sum(t["minutes"] for t in tasks))


@app.post("/api/plan/task")
def plan_task():
    data = body()
    name, aid, tid, done = learner_id(data.get("learner")), data.get("attempt_id"), data.get("task_id"), data.get("done")
    if not name:
        return bad(NICK_MSG)
    if not isinstance(done, bool) or not isinstance(tid, str) or isinstance(aid, bool) or not isinstance(aid, int):
        return bad("Invalid task update.")
    at = attempts_for(name)
    if not at or at[-1]["id"] != aid:
        return bad("This plan is out of date. Reload your study plan.", 409)
    if tid not in {t["id"] for t in logic.build_plan(at[-1]["t"], RES_BY_TOPIC)}:
        return bad("Unknown task.", 404)
    xp, new_badges = 0, []
    with tx() as c:
        if done:
            c.execute("INSERT OR IGNORE INTO task_progress(attempt_id, task_id, completed_at) VALUES(?,?,?)", (aid, tid, now_iso()))
            if not at[-1]["demo"] and award(c, name, f"task:{aid}:{tid}", logic.XP["task"], "Completed " + task_label(tid)):
                xp = logic.XP["task"]
            new_badges = grant_badges(c, name)
        else:
            c.execute("DELETE FROM task_progress WHERE attempt_id=? AND task_id=?", (aid, tid))  # XP already earned is kept
    return jsonify(ok=True, xp=xp, badges=new_badges)


@app.post("/api/demo")
def demo():
    """Adds clearly flagged sample attempts, once per learner. Never real evidence."""
    name = learner_id(body().get("learner"))
    if not name:
        return bad(NICK_MSG)
    with tx() as c:
        if c.execute("SELECT 1 FROM attempts WHERE learner=? AND is_demo=1", (name,)).fetchone():
            return jsonify(ok=True, created=False)
        for when, topics in zip(DEMO_DATES, DEMO_TOPICS):
            correct, total = sum(v[0] for v in topics.values()), sum(v[1] for v in topics.values())
            c.execute("INSERT INTO attempts(learner, taken_at, label, score, topics_json, is_demo) VALUES(?,?,?,?,?,1)",
                      (name, when, datetime.fromisoformat(when).strftime("%d %b"), logic.percent(correct, total), json.dumps(topics)))
    return jsonify(ok=True, created=True)


LEARNER_TABLES = ("attempts", "quiz_sessions", "xp_events", "badges", "practice_log")


@app.post("/api/rename")
def rename():
    d = body()
    old, new = learner_id(d.get("learner")), learner_id(d.get("new_name"))
    if not old or not new:
        return bad(NICK_MSG)
    if old == new:
        return jsonify(ok=True, name=new)
    with tx() as c:
        if any(c.execute(f"SELECT 1 FROM {t} WHERE learner=? LIMIT 1", (new,)).fetchone() for t in LEARNER_TABLES):
            return bad("That nickname already has learning history. Please choose a different one.", 409)
        for t in LEARNER_TABLES:
            c.execute(f"UPDATE {t} SET learner=? WHERE learner=?", (new, old))
    return jsonify(ok=True, name=new)


@app.post("/api/reset")
def reset():
    data = body()
    name = learner_id(data.get("learner"))
    if not name:
        return bad(NICK_MSG)
    scope = data.get("scope", "all")  # "demo" removes only sample records; "all" removes everything for this learner
    if scope not in ("all", "demo"):
        return bad("Unknown reset scope.")
    if data.get("confirm") is not True:
        return bad("Please confirm the reset.")
    mine = "SELECT id FROM attempts WHERE learner=?" + (" AND is_demo=1" if scope == "demo" else "")
    with tx() as c:
        c.execute(f"DELETE FROM task_progress WHERE attempt_id IN ({mine})", (name,))
        c.execute(f"DELETE FROM responses WHERE attempt_id IN ({mine})", (name,))
        c.execute(f"DELETE FROM attempts WHERE id IN ({mine})", (name,))
        if scope == "all":
            for table in ("quiz_sessions", "xp_events", "badges", "practice_log"):
                c.execute(f"DELETE FROM {table} WHERE learner=?", (name,))
    return jsonify(ok=True)


def solved_items(c, name):
    return {r["item_id"] for r in c.execute("SELECT item_id FROM practice_log WHERE learner=? AND solved=1", (name,))}


def pending_topics(name):
    """Topics of unfinished plan tasks for the learner's latest attempt (used to flag recommended modules)."""
    at = attempts_for(name)
    if not at:
        return set()
    with tx() as c:
        done = {r["task_id"] for r in c.execute("SELECT task_id FROM task_progress WHERE attempt_id=?", (at[-1]["id"],))}
    return {t["topic"] for t in logic.build_plan(at[-1]["t"], RES_BY_TOPIC) if t["topic"] and t["id"] not in done}


<<<<<<< HEAD
=======
<<<<<<< HEAD
>>>>>>> bafc6c70e4b365c7312d29c5291bc8befb9fd373
@app.get("/api/resources")
def resources():
    """Public learning-resource catalogue; contains curated learning content, never learner records."""
    return jsonify(resources=[{
        "id": r["id"], "topic": r["topic"], "topic_name": logic.TOPICS.get(r["topic"], r["topic"]),
        "type": r["type"], "title": r["title"], "difficulty": r.get("difficulty", "beginner"),
        "minutes": r.get("minutes", 5), "description": r.get("description", ""),
        "url": r.get("url", ""), "content": r.get("content", "")
    } for r in RESOURCES])


<<<<<<< HEAD
=======
=======
>>>>>>> 53e2e8729e4d0cf9dddc96aa4343e28719bfa8a7
>>>>>>> bafc6c70e4b365c7312d29c5291bc8befb9fd373
@app.get("/api/modules")
def modules():
    name = learner_id(request.args.get("learner"))
    if not name:
        return bad(NICK_MSG)
    with tx() as c:
        solved = solved_items(c, name)
    rec, out = pending_topics(name), []
    for t, m in MODULES.items():
        n = sum(i["id"] in solved for i in m["practice"])
        out.append({"topic": t, "title": m["title"], "solved": n, "total": len(m["practice"]), "recommended": t in rec,
                    "status": "Completed" if n == len(m["practice"]) else "In progress" if n else "Not started"})
    return jsonify(modules=out)


def module_payload(topic, name):
    m = MODULES[topic]
    with tx() as c:
        solved = solved_items(c, name)  # name None (guest preview) matches nothing
    items = [{"id": i["id"], "kind": i["kind"], "prompt": i["prompt"], "code": i.get("code", ""), "options": i["options"],
              "solved": i["id"] in solved} for i in m["practice"]]  # answers stay on the server
    return {"topic": topic, "title": m["title"], "explain": m["explain"], "analogy": m["analogy"], "code": m["code"],
            "takeaway": m["takeaway"], "items": items}


def optional_learner():
    """(ok, name): no learner given = anonymous guest preview (name None); a bad nickname is an error."""
    raw = (request.args.get("learner") or "").strip()
    if not raw:
        return True, None
    name = learner_id(raw)
    return bool(name), name


@app.get("/api/modules/<topic>")
def module_detail(topic):
    ok, name = optional_learner()
    if not ok:
        return bad(NICK_MSG)
    if topic not in MODULES:
        return bad("Unknown module.", 404)
    return jsonify(module_payload(topic, name))


@app.post("/api/practice")
def practice():
    d = body()
    name, iid, sel = learner_id(d.get("learner")), d.get("item_id"), d.get("selected")
    if not name:
        return bad(NICK_MSG)
    item = ITEMS.get(iid) if isinstance(iid, str) else None
    if item is None:
        return bad("Unknown practice item.", 404)
    if isinstance(sel, bool) or not isinstance(sel, int) or not 0 <= sel < len(item["options"]):
        return bad("Invalid answer.")
    ok, gained, module_done = sel == item["answer"], 0, False
    with tx() as c:
        c.execute("INSERT OR IGNORE INTO practice_log(learner, item_id) VALUES(?,?)", (name, iid))
        first = c.execute("SELECT attempts FROM practice_log WHERE learner=? AND item_id=?", (name, iid)).fetchone()["attempts"] == 0
        c.execute("UPDATE practice_log SET attempts = attempts + 1, solved = MAX(solved, ?), "
                  "solved_at = CASE WHEN ? = 1 AND solved_at IS NULL THEN ? ELSE solved_at END WHERE learner=? AND item_id=?",
                  (int(ok), int(ok), now_iso(), name, iid))
        if ok and first and award(c, name, "practice:" + iid, logic.XP["practice"], "Solved a practice item first try"):
            gained += logic.XP["practice"]  # only a correct first try earns XP, so retries cannot farm points
        if ok:
            solved = solved_items(c, name)
            module_done = all(i["id"] in solved for i in MODULES[item["topic"]]["practice"])
            if module_done and award(c, name, "module:" + item["topic"], logic.XP["module"], "Completed " + MODULES[item["topic"]]["title"]):
                gained += logic.XP["module"]
        new_badges = grant_badges(c, name)
    return jsonify(correct=ok, explanation=item["explanation"], answer_text=item["options"][item["answer"]],
                   first_try=first, xp=gained, module_done=module_done, badges=new_badges)


def dashboard_data(name):
    at = attempts_for(name)
    latest = at[-1] if at else None
    tasks, week_ago = [], (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    with tx() as c:
        if latest:
            done = {r["task_id"] for r in c.execute("SELECT task_id FROM task_progress WHERE attempt_id=?", (latest["id"],))}
            tasks = logic.build_plan(latest["t"], RES_BY_TOPIC)
            for t in tasks:
                t["completed"] = t["id"] in done
        xp_rows = c.execute("SELECT xp, created_at FROM xp_events WHERE learner=?", (name,)).fetchall()
        badge_rows = {r["badge_id"]: r["earned_at"] for r in c.execute("SELECT badge_id, earned_at FROM badges WHERE learner=?", (name,))}
        prac = {r["item_id"]: r for r in c.execute("SELECT item_id, attempts, solved_at FROM practice_log WHERE learner=?", (name,))}
        task_rows = c.execute("SELECT t.task_id, t.completed_at FROM task_progress t JOIN attempts a ON a.id = t.attempt_id "
                              "WHERE a.learner=?", (name,)).fetchall()
    topics = []
    for k, label in logic.TOPICS.items():
        t = latest["t"].get(k) if latest else None
        topics.append({"k": k, "name": label, "n": t[1] if t else 0, "correct": t[0] if t else 0,
                       "pct": logic.percent(*t) if t else None, "status": logic.status(*t) if t else "Not assessed"})
    needs = [x["name"] for x in topics if x["pct"] is not None and x["pct"] < logic.THRESHOLDS["strong"]]
    nxt = {"kind": "quiz", "title": "Take the diagnostic quiz",
           "why": "It shows which topics need practice, so your plan is based on your own answers."}
    if latest:
        pending = [t for t in tasks if not t["completed"]]
        if pending:
            t = pending[0]
            started = bool(t["topic"]) and any(prac.get(i["id"]) and prac[i["id"]]["attempts"] for i in MODULES[t["topic"]]["practice"])
            nxt = {"kind": "task", "topic": t["topic"], "title": t["title"], "why": t["reason"], "minutes": t["minutes"],
                   "difficulty": (t["resource"] or {}).get("difficulty", "easy"), "outcome": t["goal"], "started": started}
        else:
            nxt = {"kind": "retake", "title": "Retake the assessment",
                   "why": "You finished your plan. A new attempt shows whether your scores changed."}
    solved = {i for i, p in prac.items() if p["solved_at"]}
    rec = {t["topic"] for t in tasks if t["topic"] and not t["completed"]}
    mods = [{"topic": tp, "title": m["title"], "total": len(m["practice"]), "recommended": tp in rec,
             "solved": sum(i["id"] in solved for i in m["practice"])} for tp, m in MODULES.items()]
    featured = nxt.get("topic") or next((m["topic"] for m in mods if m["solved"] < m["total"]), "var")
    per_day = {}
    for r in xp_rows:
        per_day[r["created_at"][:10]] = per_day.get(r["created_at"][:10], 0) + 1
    today = date.today()
    activity = [{"d": (today - timedelta(days=i)).isoformat(), "label": (today - timedelta(days=i)).strftime("%a"),
                 "count": per_day.get((today - timedelta(days=i)).isoformat(), 0)} for i in range(6, -1, -1)]
    total_xp = sum(r["xp"] for r in xp_rows)
    lv = logic.level_info(total_xp)
    days = {r["created_at"][:10] for r in xp_rows}
    real = [a["s"] for a in at if not a["demo"]]
    timeline = [{"t": a["at"], "text": f"Completed an assessment: {a['s']}% ({a['correct']} of {a['total']})" + (" (demo data)" if a["demo"] else "")} for a in at]
    timeline += [{"t": r["completed_at"], "text": "Completed study task: " + task_label(r["task_id"])} for r in task_rows]
    timeline += [{"t": p["solved_at"], "text": "Solved a practice item: " + MODULES[ITEMS[i]["topic"]]["title"]} for i, p in prac.items() if p["solved_at"] and i in ITEMS]
    timeline += [{"t": when, "text": "Earned badge: " + logic.BADGES[b][0]} for b, when in badge_rows.items()]
    timeline.sort(key=lambda x: x["t"], reverse=True)
    return {"latest": latest and {k: latest[k] for k in ("s", "correct", "total", "demo", "d")}, "topics": topics, "needs": needs,
            "attempts": len(at), "change": latest["s"] - at[0]["s"] if len(at) > 1 else None,
            "mixed": bool(latest) and at[0]["demo"] != latest["demo"], "best": max(real) if real else None,
            "tasks": [{k: t[k] for k in ("id", "day", "topic", "title", "minutes", "completed")} for t in tasks],
            "tasks_done": sum(t["completed"] for t in tasks), "tasks_total": len(tasks), "next": nxt,
            "xp": total_xp, **lv, "streak": logic.streak(days, date.today()), "active_days": len(days),
            "weekly": {"count": sum(r["created_at"] >= week_ago for r in xp_rows), "goal": logic.WEEKLY_GOAL},
            "badges": [{"id": b, "name": n, "desc": ds, "earned": badge_rows.get(b)} for b, (n, ds) in logic.BADGES.items()],
            "timeline": timeline[:8], "modules": mods, "featured": featured, "activity": activity,
            "starter": {"topic": "var", "title": "Starter lesson: " + MODULES["var"]["title"], "minutes": RES_BY_TOPIC["var"]["lesson"]["minutes"],
                        "why": "A short first lesson you can try right now, no quiz needed.", "goal": "Solve both practice items in one module this week."}}


@app.get("/api/dashboard")
def dashboard():
    ok, name = optional_learner()
    return jsonify(dashboard_data(name)) if ok else bad(NICK_MSG)


@app.get("/export.csv")
def export():
    """Real attempts only (demo records excluded). Localhost only, or set LEARNWISE_EXPORT_KEY and pass ?key=."""
    secret = os.environ.get("LEARNWISE_EXPORT_KEY")
    allowed = (secrets.compare_digest(request.args.get("key", ""), secret) if secret
               else request.remote_addr in ("127.0.0.1", "::1"))
    if not allowed:
        return bad("Export is not available.", 403)
    sql = ("SELECT a.learner, a.id AS attempt_id, a.taken_at, r.question_id, r.selected, r.is_correct "
           "FROM responses r JOIN attempts a ON a.id = r.attempt_id WHERE a.is_demo = 0")
    args = ()
    if learner_id(request.args.get("learner")):
        sql, args = sql + " AND a.learner = ?", (request.args["learner"].strip(),)
    with tx() as c:
        rows = c.execute(sql + " ORDER BY a.id, r.id", args).fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["learner", "attempt_id", "taken_at", "question_id", "topic", "difficulty", "selected", "is_correct"])
    for r in rows:
        q = KEY.get(r["question_id"], {})
        w.writerow([r["learner"], r["attempt_id"], r["taken_at"], r["question_id"], q.get("topic"),
                    q.get("difficulty"), r["selected"], r["is_correct"]])
    return Response(out.getvalue(), mimetype="text/csv")


for _code, _msg in ((404, "Not found."), (405, "That action is not allowed."), (413, "Request too large.")):
    app.register_error_handler(_code, lambda e, m=_msg, c=_code: (jsonify(error=m), c))


@app.errorhandler(sqlite3.Error)
@app.errorhandler(500)
def server_error(e):
    """Log the real error on the server; show the learner only a friendly message."""
    err = getattr(e, "original_exception", None) or e
    app.logger.error("Unhandled error: %r", err, exc_info=err if isinstance(err, BaseException) else None)
    return jsonify(error="Something went wrong on the server. Please try again."), 500

init_db()

if __name__ == "__main__":
    app.run(debug=True)  # debug mode is for local development only
