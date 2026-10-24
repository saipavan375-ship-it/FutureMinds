"""Scoring and recommendation rules.
Everything here is a rule or a calculation. There is no trained ML model."""

from datetime import date, timedelta

# Initial product rules, NOT scientifically validated measures of ability.
# Tune them after reviewing question quality and real learner results.
THRESHOLDS = {"needs_practice": 50, "strong": 80, "min_evidence": 3, "max_topics": 3}

TOPICS = {
    "var": "Variables and data types",
    "ops": "Operators and expressions",
    "cond": "Conditionals",
    "loop": "Loops and range()",
    "list": "Strings and lists",
    "func": "Functions and return values",
    "dict": "Dictionaries and sets",
    "debug": "Debugging and problem solving",
}

TIPS = {
    "var": "Review how values and types work, with one example of each type.",
    "ops": "Review operator order and the difference between /, // and %.",
    "cond": "Review if/elif/else flow and when each branch runs.",
    "loop": "Review for-loops and range() boundaries with worked examples.",
    "list": "Review indexing, slicing and common string and list methods.",
    "func": "Review def, parameters, defaults and return values.",
    "dict": "Review dictionary keys and values, and what makes set items unique.",
    "debug": "Review common error names and how to trace values with print().",
}
DIFFICULTIES = ("easy", "medium", "hard")


def percent(correct, total):
    """Raw topic or overall percentage, rounded half up. The only score shown to learners."""
    return int(100 * correct / total + 0.5) if total else 0


def status(correct, total):
    if total == 0:
        return "Not assessed"
    p = percent(correct, total)
    if p < THRESHOLDS["needs_practice"]:
        return "Needs practice"
    return "Developing" if p < THRESHOLDS["strong"] else "Strong"


def score_topics(pairs):
    """[(topic, is_correct)] -> {topic: [correct, total]} for attempted topics only."""
    result = {}
    for topic, ok in pairs:
        item = result.setdefault(topic, [0, 0])
        item[0] += int(ok)
        item[1] += 1
    return result


def priority(correct, total):
    """Calculation used ONLY to rank topics. It shrinks toward 50% when few questions
    were answered, so 1/1 does not outrank 8/10. Lower value = more attention needed."""
    return (correct + 1) / (total + 2)


# Direct prerequisites. Used only to order the study plan (foundations first).
PREREQS = {"ops": ("var",), "cond": ("ops",), "loop": ("cond",), "list": ("var",), "func": ("cond", "loop"), "dict": ("list",)}


def depth(topic):
    return 1 + max((depth(p) for p in PREREQS.get(topic, ())), default=-1)


def build_plan(topics, library):
    """Rule-based plan from one attempt. library = {topic: {"lesson": res, "example": res}}.
    Topics are chosen by lowest priority(), then ordered so prerequisites come first.
    Each topic gets one study day; the follow-up quiz is the last day."""
    th = THRESHOLDS
    ranked = sorted(((k, c, n) for k, (c, n) in topics.items() if n and k in TOPICS),
                    key=lambda x: priority(x[1], x[2]))
    need = [x for x in ranked if percent(x[1], x[2]) < th["strong"]][: th["max_topics"]]
    need.sort(key=lambda x: (depth(x[0]), priority(x[1], x[2])))
    tasks = []
    for day, (k, c, n) in enumerate(need, start=1):
        p, name = percent(c, n), TOPICS[k]
        reason = f"You answered {c} of {n} questions on {name.lower()} correctly ({p}%)."
        if n < th["min_evidence"]:
            reason += " That is too few questions for a reliable estimate, so treat it as a first signal."
        dependents = [TOPICS[d] for d, _, _ in need if k in PREREQS.get(d, ())]
        if dependents:
            reason += f" It is a prerequisite for {', '.join(dependents).lower()}, so it comes first."
        action = ("Review the basics, then study a worked example." if p < th["needs_practice"]
                  else "Study a worked example, then revisit the lesson for gaps.")
        base = {"topic": k, "topic_name": name, "score": p, "evidence": n, "reason": reason, "action": action, "day": day,
                "goal": f"Score at least {th['strong']}% on {name.lower()} in your next attempt (now {p}%)."}
        tasks.append({**base, "id": f"{k}-lesson", "kind": "lesson", "title": f"Review: {name}",
                      "minutes": library[k]["lesson"]["minutes"], "resource": library[k]["lesson"],
                      "follow_up": "Next, read the worked example."})
        tasks.append({**base, "id": f"{k}-example", "kind": "example", "title": f"Worked example: {name}",
                      "minutes": library[k]["example"]["minutes"], "resource": library[k]["example"],
                      "follow_up": "Then retake the quiz to check progress."})
    if not need and ranked:
        k, c, n = ranked[0]
        name = TOPICS[k]
        tasks.append({"id": f"{k}-challenge", "kind": "challenge", "topic": k, "topic_name": name,
                      "score": percent(c, n), "evidence": n, "title": f"Challenge: {name}", "day": 1,
                      "minutes": library[k]["example"]["minutes"], "resource": library[k]["example"],
                      "action": "Try changing the example to solve a harder problem.",
                      "goal": f"Stay at {th['strong']}% or higher on {name.lower()} after the harder task.",
                      "reason": f"All assessed topics are strong. {name} is your lowest at {percent(c, n)}%, so stretch it.",
                      "follow_up": "Then retake the quiz to check retention."})
    if tasks:
        tasks.append({"id": "recheck", "kind": "check", "topic": None, "topic_name": None, "score": None,
                      "evidence": None, "title": "Follow-up: retake the diagnostic quiz", "minutes": 10,
                      "day": max(t["day"] for t in tasks) + 1, "resource": None,
                      "action": "Take a new attempt after studying.",
                      "goal": "Finish the tasks above, then try to beat your last score.",
                      "reason": "A new attempt shows whether the plan helped. Higher scores are a good sign, not proof.",
                      "follow_up": "Compare attempts on the Progress page."})
    return tasks


def validate_bank(questions, resources):
    """Return a list of problems with the question bank and resource library (empty = OK)."""
    problems, seen = [], set()
    res_ids = {r.get("id") for r in resources}
    for q in questions:
        qid = q.get("id", "?")
        if qid in seen:
            problems.append(f"duplicate id {qid}")
        seen.add(qid)
        for f in ("id", "topic", "difficulty", "text", "options", "answer", "explanation"):
            if f not in q or q[f] in ("", None, []):
                problems.append(f"{qid}: missing {f}")
        if q.get("topic") not in TOPICS:
            problems.append(f"{qid}: unknown topic")
        if q.get("difficulty") not in DIFFICULTIES:
            problems.append(f"{qid}: bad difficulty")
        opts, a = q.get("options") or [], q.get("answer")
        if len(opts) != 4 or len(set(opts)) != 4:
            problems.append(f"{qid}: need 4 distinct options")
        if isinstance(a, bool) or not isinstance(a, int) or not 0 <= a < len(opts):
            problems.append(f"{qid}: answer index out of range")
        if q.get("resource_id") and q["resource_id"] not in res_ids:
            problems.append(f"{qid}: unknown resource_id")
    for t in TOPICS:
        if sum(q.get("topic") == t for q in questions) < 3:
            problems.append(f"topic {t}: fewer than 3 questions")
    kinds = {(r.get("topic"), r.get("type")) for r in resources}
    for t in TOPICS:
        for kind in ("lesson", "example"):
            if (t, kind) not in kinds:
                problems.append(f"topic {t}: missing {kind} resource")
    ids = [r.get("id") for r in resources]
    if len(ids) != len(set(ids)):
        problems.append("duplicate resource id")
    return problems


# ---- Rewards. XP is awarded once per real event (see app.py award()); demo data never earns XP. ----
XP = {"quiz": 30, "task": 10, "practice": 10, "module": 20}  # practice XP only for a correct FIRST try
XP_PER_LEVEL = 100
WEEKLY_GOAL = 3  # learning activities per week
BADGES = {
    "first_quiz": ("First assessment", "Complete your first real diagnostic quiz."),
    "first_task": ("First study task", "Complete a task in your study plan."),
    "first_module": ("Module complete", "Solve every practice item in a learning module."),
    "personal_best": ("New personal best", "Score higher than all your earlier real assessments."),
    "three_days": ("Three active days", "Learn on 3 different days."),
}


def level_info(xp):
    return {"level": xp // XP_PER_LEVEL + 1, "into": xp % XP_PER_LEVEL, "per_level": XP_PER_LEVEL}


def streak(days, today):
    """Consecutive active days ending today or yesterday. Based only on dated activity records."""
    active = {date.fromisoformat(d) for d in days}
    cur = today if today in active else today - timedelta(days=1)
    n = 0
    while cur in active:
        n += 1
        cur -= timedelta(days=1)
    return n


def validate_modules(modules):
    problems, seen = [], set()
    have = [m.get("topic") for m in modules]
    for t in TOPICS:
        if t not in have:
            problems.append(f"module for {t} missing")
    for m in modules:
        t = m.get("topic")
        for f in ("title", "explain", "analogy", "code", "takeaway"):
            if not m.get(f):
                problems.append(f"{t}: missing {f}")
        if len(m.get("practice") or []) < 2:
            problems.append(f"{t}: needs at least 2 practice items")
        for it in m.get("practice") or []:
            iid, opts, a = it.get("id", "?"), it.get("options") or [], it.get("answer")
            if iid in seen:
                problems.append(f"duplicate item id {iid}")
            seen.add(iid)
            if it.get("kind") not in ("output", "bug"):
                problems.append(f"{iid}: bad kind")
            if not it.get("prompt") or not it.get("explanation"):
                problems.append(f"{iid}: missing prompt or explanation")
            if len(opts) != 4 or len(set(opts)) != 4:
                problems.append(f"{iid}: need 4 distinct options")
            if isinstance(a, bool) or not isinstance(a, int) or not 0 <= a < len(opts):
                problems.append(f"{iid}: answer index out of range")
    return problems
