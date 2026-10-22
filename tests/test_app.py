import csv, io, os, sqlite3, tempfile, unittest

import app as A
import logic


class Base(unittest.TestCase):
    def setUp(self):  # every test gets its own temporary database
        self.tmp = tempfile.TemporaryDirectory()
        A.app.config.update(DATABASE=os.path.join(self.tmp.name, "test.db"), TESTING=True)
        A.init_db()
        self.c = A.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, who):
        r = self.c.post("/api/quiz", json={"learner": who})
        self.assertEqual(r.status_code, 200)
        return r.get_json()

    def take(self, who, pick=lambda q, right: right):
        d = self.start(who)
        ans = {q["id"]: (A.KEY[q["id"]]["answer"] if pick(q, True) else (A.KEY[q["id"]]["answer"] + 1) % 4) for q in d["questions"]}
        return self.c.post("/api/submit", json={"learner": who, "token": d["token"], "answers": ans}), d, ans

    def attempts(self, who):
        return self.c.get(f"/api/progress?learner={who}").get_json()["attempts"]


class QuestionBank(Base):
    def test_landing_page_loads(self):
        self.assertEqual(self.c.get("/").status_code, 200)

    def test_bank_is_valid(self):
        self.assertEqual(logic.validate_bank(A.QUESTIONS, A.RESOURCES), [])

    def test_quiz_is_balanced_and_hides_answers(self):
        d = self.start("learner1")
        self.assertEqual(len(d["questions"]), 3 * len(logic.TOPICS))
        for q in d["questions"]:
            self.assertEqual(set(q), {"id", "topic", "text", "options"})
        for t in logic.TOPICS:
            self.assertEqual(sum(q["topic"] == t for q in d["questions"]), 3)

    def test_validator_catches_bad_key(self):
        bad = [dict(A.QUESTIONS[0], answer=9)] + A.QUESTIONS[1:]
        self.assertTrue(any("answer index" in p for p in logic.validate_bank(bad, A.RESOURCES)))


class Scoring(Base):
    def test_all_correct_and_all_wrong(self):
        r, _, _ = self.take("allright")
        self.assertEqual((r.get_json()["correct"], r.get_json()["total"]), (24, 24))
        r, _, _ = self.take("allwrong", pick=lambda q, right: False)
        self.assertEqual(r.get_json()["correct"], 0)
        self.assertEqual(r.get_json()["review"][0].keys() >= {"text", "answer", "explanation"}, True)

    def test_topic_scores(self):
        self.take("looper", pick=lambda q, right: q["topic"] == "loop")
        a = self.attempts("looper")[0]
        self.assertEqual(a["t"]["loop"], [3, 3])
        self.assertEqual(a["t"]["var"], [0, 3])
        self.assertEqual(a["s"], 13)  # 3 of 24, rounded half up

    def test_rejects_invalid_input(self):
        d = self.start("badinput")
        qid = d["questions"][0]["id"]
        post = lambda **kw: self.c.post("/api/submit", json={"learner": "badinput", "token": d["token"], **kw})
        self.assertEqual(post(answers={}).status_code, 400)  # empty
        self.assertEqual(post(answers={"NOPE": 0}).status_code, 400)  # unknown id
        full = {q["id"]: 0 for q in d["questions"]}
        self.assertEqual(post(answers={qid: 0}).status_code, 400)  # missing answers
        self.assertEqual(post(answers={**full, qid: 9}).status_code, 400)  # bad index
        self.assertEqual(post(answers={**full, qid: True}).status_code, 400)  # bool is not an index
        self.assertEqual(self.attempts("badinput"), [])

    def test_duplicate_submission_blocked(self):
        r, d, ans = self.take("twice")
        again = self.c.post("/api/submit", json={"learner": "twice", "token": d["token"], "answers": ans})
        self.assertEqual(again.status_code, 409)
        self.assertEqual(len(self.attempts("twice")), 1)

    def test_token_is_tied_to_learner(self):
        d = self.start("owner1")
        ans = {q["id"]: 0 for q in d["questions"]}
        r = self.c.post("/api/submit", json={"learner": "other1", "token": d["token"], "answers": ans})
        self.assertEqual(r.status_code, 404)

    def test_nickname_validation(self):
        for bad in ("", "ab", "has space", "x" * 31, "<script>"):
            self.assertEqual(self.c.post("/api/quiz", json={"learner": bad}).status_code, 400)
        self.assertEqual(self.c.get("/api/progress?learner=").status_code, 400)


class Recommendations(Base):
    def test_unassessed_topic_is_not_zero(self):
        self.assertEqual(logic.status(0, 0), "Not assessed")
        plan = logic.build_plan({"loop": [1, 3]}, A.RES_BY_TOPIC)
        self.assertTrue(all(t["topic"] in ("loop", None) for t in plan))

    def test_plan_matches_results_and_resources_exist(self):
        topics = {"loop": [3, 3], "var": [0, 3], "dict": [1, 3], "func": [2, 3]}
        plan = logic.build_plan(topics, A.RES_BY_TOPIC)
        topics_in_plan = [t["topic"] for t in plan if t["kind"] == "lesson"]
        self.assertEqual(topics_in_plan, ["var", "dict", "func"])  # lowest first, strong topic excluded
        for t in plan:
            if t["resource"]:
                self.assertIn(t["resource"]["id"], {r["id"] for r in A.RESOURCES})
        self.assertIn("0 of 3", plan[0]["reason"])

    def test_challenge_when_all_strong(self):
        plan = logic.build_plan({"loop": [3, 3], "var": [3, 3]}, A.RES_BY_TOPIC)
        self.assertEqual(plan[0]["kind"], "challenge")

    def test_task_completion_persists_and_resets_with_new_attempt(self):
        self.take("planner", pick=lambda q, right: False)
        p = self.c.get("/api/plan?learner=planner").get_json()
        tid = p["tasks"][0]["id"]
        post = lambda **kw: self.c.post("/api/plan/task", json={"learner": "planner", **kw})
        self.assertEqual(post(attempt_id=p["attempt_id"], task_id=tid, done=True).status_code, 200)
        self.assertTrue(self.c.get("/api/plan?learner=planner").get_json()["tasks"][0]["completed"])
        self.assertEqual(post(attempt_id=p["attempt_id"], task_id="nope", done=True).status_code, 404)
        self.take("planner", pick=lambda q, right: False)
        p2 = self.c.get("/api/plan?learner=planner").get_json()
        self.assertFalse(p2["tasks"][0]["completed"])
        self.assertEqual(post(attempt_id=p["attempt_id"], task_id=tid, done=True).status_code, 409)  # stale plan


class Storage(Base):
    def test_histories_are_separate(self):
        self.take("alice1"); self.take("alice1"); self.take("bobby1")
        self.assertEqual(len(self.attempts("alice1")), 2)
        self.assertEqual(len(self.attempts("bobby1")), 1)

    def test_demo_labeled_and_not_duplicated(self):
        for _ in range(3):
            self.c.post("/api/demo", json={"learner": "demo1"})
        at = self.attempts("demo1")
        self.assertEqual(len(at), 2)
        self.assertTrue(all(a["demo"] for a in at))
        self.take("demo1")
        self.assertFalse(self.attempts("demo1")[-1]["demo"])

    def test_export_columns_and_excludes_demo(self):
        self.c.post("/api/demo", json={"learner": "demo1"})
        self.take("real1")
        rows = list(csv.DictReader(io.StringIO(self.c.get("/export.csv").data.decode())))
        self.assertEqual(list(rows[0]), ["learner", "attempt_id", "taken_at", "question_id", "topic", "difficulty", "selected", "is_correct"])
        self.assertEqual(len(rows), 24)
        self.assertEqual({r["learner"] for r in rows}, {"real1"})
        self.assertEqual(self.c.get("/export.csv", environ_overrides={"REMOTE_ADDR": "10.0.0.5"}).status_code, 403)

    def test_reset_only_affects_selected_learner(self):
        self.take("keep1"); self.take("drop1")
        self.assertEqual(self.c.post("/api/reset", json={"learner": "drop1"}).status_code, 400)  # needs confirm
        self.assertEqual(self.c.post("/api/reset", json={"learner": "drop1", "confirm": True}).status_code, 200)
        self.assertEqual(self.attempts("drop1"), [])
        self.assertEqual(len(self.attempts("keep1")), 1)

    def test_fresh_database(self):
        self.assertEqual(self.attempts("newbie")  , [])
        self.assertEqual(self.c.get("/api/plan?learner=newbie").get_json()["tasks"], [])

    def test_migration_keeps_old_attempts(self):
        path = os.path.join(self.tmp.name, "old.db")
        con = sqlite3.connect(path)
        con.executescript("CREATE TABLE attempts(id INTEGER PRIMARY KEY AUTOINCREMENT, learner TEXT NOT NULL, taken_at TEXT NOT NULL, label TEXT NOT NULL, score INTEGER NOT NULL, topics_json TEXT NOT NULL);"
                          "INSERT INTO attempts(learner, taken_at, label, score, topics_json) VALUES('old1','2026-10-14T10:00:00','14 Oct',67,'{\"var\": [2, 3]}');")
        con.commit(); con.close()
        A.app.config["DATABASE"] = path
        A.init_db()
        a = self.attempts("old1")
        self.assertEqual((len(a), a[0]["demo"]), (1, False))

    def test_errors_are_json(self):
        r = self.c.get("/api/missing")
        self.assertEqual((r.status_code, "error" in r.get_json()), (404, True))


class Extras(Base):
    def test_bank_size_and_resource_links(self):
        self.assertGreaterEqual(len(A.QUESTIONS), 40)
        self.assertTrue(all(q.get("resource_id") in {r["id"] for r in A.RESOURCES} for q in A.QUESTIONS))

    def test_demo_only_reset_keeps_real_attempts(self):
        self.c.post("/api/demo", json={"learner": "mixed1"})
        self.take("mixed1")
        self.assertEqual(self.c.post("/api/reset", json={"learner": "mixed1", "scope": "demo"}).status_code, 400)  # needs confirm
        self.assertEqual(self.c.post("/api/reset", json={"learner": "mixed1", "scope": "bogus", "confirm": True}).status_code, 400)
        self.assertEqual(self.c.post("/api/reset", json={"learner": "mixed1", "scope": "demo", "confirm": True}).status_code, 200)
        at = self.attempts("mixed1")
        self.assertEqual((len(at), at[0]["demo"]), (1, False))

    def test_review_covers_every_question(self):
        r, _, _ = self.take("reviewer", pick=lambda q, right: q["topic"] == "var")
        review = r.get_json()["review"]
        self.assertEqual((len(review), sum(x["ok"] for x in review)), (24, 3))


class Round3(Base):
    def test_all_difficulty_levels_and_balance(self):
        self.assertEqual({q["difficulty"] for q in A.QUESTIONS}, {"easy", "medium", "hard"})
        self.assertGreaterEqual(len(A.QUESTIONS), 48)

    def test_prerequisite_comes_first_with_goal_and_day(self):
        plan = logic.build_plan({"loop": [0, 3], "cond": [1, 3]}, A.RES_BY_TOPIC)
        lessons = [t for t in plan if t["kind"] == "lesson"]
        self.assertEqual([t["topic"] for t in lessons], ["cond", "loop"])  # cond is a prerequisite of loop
        self.assertIn("prerequisite for loops", lessons[0]["reason"])
        self.assertEqual([t["day"] for t in plan], [1, 1, 2, 2, 3])
        self.assertTrue(all(t["goal"] and t["reason"] and t["minutes"] for t in plan))

    def test_progress_includes_task_log(self):
        self.take("logger1", pick=lambda q, right: False)
        p = self.c.get("/api/plan?learner=logger1").get_json()
        self.c.post("/api/plan/task", json={"learner": "logger1", "attempt_id": p["attempt_id"], "task_id": p["tasks"][0]["id"], "done": True})
        log = self.c.get("/api/progress?learner=logger1").get_json()["task_log"]
        self.assertEqual([x["task_id"] for x in log], [p["tasks"][0]["id"]])
        self.assertEqual(self.c.get("/api/progress?learner=other11").get_json()["task_log"], [])

    def test_database_errors_are_friendly_and_logged(self):
        original = A.attempts_for
        A.attempts_for = lambda name: (_ for _ in ()).throw(sqlite3.OperationalError("secret path detail"))
        try:
            with self.assertLogs(A.app.logger, level="ERROR"):
                r = self.c.get("/api/progress?learner=abcd")
        finally:
            A.attempts_for = original
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("secret", r.get_data(as_text=True))


class Round4(Base):
    def dash(self, who):
        return self.c.get(f"/api/dashboard?learner={who}").get_json()

    def solve(self, who, item_id, right=True):
        a = A.ITEMS[item_id]["answer"]
        return self.c.post("/api/practice", json={"learner": who, "item_id": item_id, "selected": a if right else (a + 1) % 4})

    def test_answer_positions_are_balanced(self):
        for name, rows in (("quiz", A.QUESTIONS), ("practice", list(A.ITEMS.values()))):
            for pos in range(4):
                share = sum(r["answer"] == pos for r in rows) / len(rows)
                self.assertTrue(0.15 <= share <= 0.35, f"{name}: option {pos} is correct {share:.0%} of the time")

    def test_modules_are_valid_and_hide_answers(self):
        self.assertEqual(logic.validate_modules(A.MODULES_LIST), [])
        bad = [dict(A.MODULES_LIST[0], practice=[dict(A.MODULES_LIST[0]["practice"][0], answer=7)] * 2)] + A.MODULES_LIST[1:]
        self.assertTrue(logic.validate_modules(bad))
        r = self.c.get("/api/modules/loop?learner=reader1").get_json()
        self.assertEqual(len(r["items"]), 2)
        for it in r["items"]:
            self.assertNotIn("answer", it)
            self.assertNotIn("explanation", it)
        self.assertEqual(self.c.get("/api/modules/nope?learner=reader1").status_code, 404)
        self.assertEqual(self.c.get("/api/modules/loop?learner=x").status_code, 400)

    def test_empty_dashboard_has_no_invented_data(self):
        d = self.dash("newbie1")
        self.assertIsNone(d["latest"])
        self.assertEqual((d["next"]["kind"], d["xp"], d["tasks_total"], d["timeline"], d["best"], d["streak"]), ("quiz", 0, 0, [], None, 0))
        self.assertTrue(all(t["status"] == "Not assessed" and t["pct"] is None for t in d["topics"]))
        self.assertTrue(all(b["earned"] is None for b in d["badges"]))

    def test_dashboard_matches_stored_attempt(self):
        self.take("dashy1", pick=lambda q, right: q["topic"] in ("loop", "var"))
        d = self.dash("dashy1")
        a = self.attempts("dashy1")[0]
        self.assertEqual((d["latest"]["s"], d["latest"]["correct"]), (a["s"], 6))
        by = {t["k"]: t for t in d["topics"]}
        self.assertEqual((by["loop"]["pct"], by["loop"]["status"], by["dict"]["pct"], by["dict"]["status"]), (100, "Strong", 0, "Needs practice"))
        self.assertEqual(len(d["needs"]), 6)
        self.assertEqual(d["next"]["kind"], "task")
        self.assertEqual(d["xp"], logic.XP["quiz"])
        self.assertEqual([b["id"] for b in d["badges"] if b["earned"]], ["first_quiz"])
        self.assertIn("Completed an assessment", d["timeline"][0]["text"])

    def test_xp_for_quiz_and_tasks_is_awarded_once(self):
        self.take("xp1", pick=lambda q, right: False)
        p = self.c.get("/api/plan?learner=xp1").get_json()
        post = lambda done: self.c.post("/api/plan/task", json={"learner": "xp1", "attempt_id": p["attempt_id"], "task_id": p["tasks"][0]["id"], "done": done}).get_json()
        self.assertEqual(post(True)["xp"], logic.XP["task"])
        post(False)
        self.assertEqual(post(True)["xp"], 0)  # ticking again earns nothing
        self.assertEqual(self.dash("xp1")["xp"], logic.XP["quiz"] + logic.XP["task"])
        rows = self.c.get("/api/dashboard?learner=xp1").get_json()
        self.assertIn("first_task", [b["id"] for b in rows["badges"] if b["earned"]])

    def test_demo_data_never_earns_rewards(self):
        self.c.post("/api/demo", json={"learner": "demo2"})
        p = self.c.get("/api/plan?learner=demo2").get_json()
        r = self.c.post("/api/plan/task", json={"learner": "demo2", "attempt_id": p["attempt_id"], "task_id": p["tasks"][0]["id"], "done": True})
        self.assertEqual(r.get_json()["xp"], 0)
        d = self.dash("demo2")
        self.assertEqual((d["xp"], d["best"], [b for b in d["badges"] if b["earned"]]), (0, None, []))
        self.assertTrue(d["latest"]["demo"])

    def test_practice_xp_rules(self):
        iid = "PRAC_LOOP_1"
        self.assertEqual(self.c.post("/api/practice", json={"learner": "prac1", "item_id": "nope", "selected": 0}).status_code, 404)
        for bad in (9, True, "1", -1):
            self.assertEqual(self.c.post("/api/practice", json={"learner": "prac1", "item_id": iid, "selected": bad}).status_code, 400)
        r = self.solve("prac1", iid, right=False).get_json()
        self.assertEqual((r["correct"], r["xp"]), (False, 0))
        self.assertTrue(r["answer_text"] and r["explanation"])
        self.assertEqual(self.solve("prac1", iid).get_json()["xp"], 0)  # solved on a retry: no XP
        self.assertEqual(self.solve("prac1", iid).get_json()["xp"], 0)  # repeats never add XP
        self.assertEqual(self.dash("prac1")["xp"], 0)
        r = self.solve("prac1", "PRAC_LOOP_2").get_json()  # first try correct: +10, module finished: +20
        self.assertEqual((r["xp"], r["module_done"]), (logic.XP["practice"] + logic.XP["module"], True))
        self.assertEqual(self.solve("prac1", "PRAC_LOOP_2").get_json()["xp"], 0)
        d = self.dash("prac1")
        self.assertEqual(d["xp"], 30)
        self.assertIn("first_module", [b["id"] for b in d["badges"] if b["earned"]])
        mods = {m["topic"]: m for m in self.c.get("/api/modules?learner=prac1").get_json()["modules"]}
        self.assertEqual((mods["loop"]["status"], mods["var"]["status"]), ("Completed", "Not started"))

    def test_personal_best_badge_and_recommended_modules(self):
        self.take("best1", pick=lambda q, right: False)
        self.take("best1")
        self.assertIn("personal_best", [b["id"] for b in self.dash("best1")["badges"] if b["earned"]])
        self.assertEqual(self.dash("best1")["best"], 100)
        self.take("rec1", pick=lambda q, right: q["topic"] != "dict")
        mods = {m["topic"]: m for m in self.c.get("/api/modules?learner=rec1").get_json()["modules"]}
        self.assertTrue(mods["dict"]["recommended"])
        self.assertFalse(mods["loop"]["recommended"])

    def test_rewards_are_private_per_learner_and_reset_cleanly(self):
        self.take("priv1"); self.solve("priv1", "PRAC_VAR_1")
        self.assertEqual(self.dash("other2")["xp"], 0)
        self.take("priv2")
        self.c.post("/api/reset", json={"learner": "priv1", "confirm": True})
        d1, d2 = self.dash("priv1"), self.dash("priv2")
        self.assertEqual((d1["xp"], d1["attempts"], d1["timeline"]), (0, 0, []))
        self.assertEqual(d2["xp"], logic.XP["quiz"])

    def test_streak_is_based_on_dated_activity(self):
        from datetime import date
        today = date(2026, 10, 18)
        self.assertEqual(logic.streak([], today), 0)
        self.assertEqual(logic.streak(["2026-10-18", "2026-10-17", "2026-10-16"], today), 3)
        self.assertEqual(logic.streak(["2026-10-17", "2026-10-16"], today), 2)  # today not done yet
        self.assertEqual(logic.streak(["2026-10-14"], today), 0)  # a gap resets the count, with no penalty
        self.assertEqual(logic.level_info(250), {"level": 3, "into": 50, "per_level": 100})

    def test_full_journey_survives_a_restart(self):
        r, _, _ = self.take("journey1", pick=lambda q, right: q["topic"] != "func")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.dash("journey1")["next"]["topic"], "func")
        self.solve("journey1", "PRAC_FUNC_1")
        p = self.c.get("/api/plan?learner=journey1").get_json()
        self.c.post("/api/plan/task", json={"learner": "journey1", "attempt_id": p["attempt_id"], "task_id": p["tasks"][0]["id"], "done": True})
        fresh = A.app.test_client()  # new client, same database file = application restart
        d = fresh.get("/api/dashboard?learner=journey1").get_json()
        self.assertEqual((d["tasks_done"], d["xp"]), (1, logic.XP["quiz"] + logic.XP["practice"] + logic.XP["task"]))
        self.assertEqual(d["next"]["title"], p["tasks"][1]["title"])
        self.assertTrue(any("Solved a practice item" in x["text"] for x in d["timeline"]))

    def test_dashboard_errors_are_friendly(self):
        self.assertEqual(self.c.get("/api/dashboard?learner=a").status_code, 400)  # blank = guest preview, a bad name is rejected
        original = A.attempts_for
        A.attempts_for = lambda name: (_ for _ in ()).throw(sqlite3.OperationalError("secret path detail"))
        try:
            with self.assertLogs(A.app.logger, level="ERROR"):
                r = self.c.get("/api/dashboard?learner=abcd")
        finally:
            A.attempts_for = original
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("secret", r.get_data(as_text=True))


class Round5(Base):
    def dash(self, who):
        return self.c.get(f"/api/dashboard?learner={who}").get_json()

    def test_new_dashboard_fields_for_empty_learner(self):
        d = self.dash("empty11")
        self.assertEqual(len(d["activity"]), 7)
        self.assertTrue(all(a["count"] == 0 for a in d["activity"]))
        self.assertEqual((len(d["modules"]), d["featured"]), (8, "var"))
        self.assertTrue(all(m["solved"] == 0 for m in d["modules"]))

    def test_activity_and_modules_come_from_real_records(self):
        from datetime import date
        self.take("real11", pick=lambda q, right: q["topic"] != "list")
        for item in ("PRAC_LIST_1", "PRAC_LIST_2"):
            self.c.post("/api/practice", json={"learner": "real11", "item_id": item, "selected": A.ITEMS[item]["answer"]})
        d = self.dash("real11")
        self.assertEqual(d["activity"][-1]["d"], date.today().isoformat())
        self.assertEqual(d["activity"][-1]["count"], 4)  # quiz + 2 first-try practice items + module
        self.assertEqual(sum(a["count"] for a in d["activity"][:-1]), 0)
        mods = {m["topic"]: m for m in d["modules"]}
        self.assertEqual((mods["list"]["solved"], mods["var"]["solved"]), (2, 0))
        self.assertEqual(d["featured"], d["next"]["topic"])

    def test_demo_learner_has_no_activity_or_modules_progress(self):
        self.c.post("/api/demo", json={"learner": "demo33"})
        d = self.dash("demo33")
        self.assertEqual(sum(a["count"] for a in d["activity"]), 0)
        self.assertTrue(d["latest"]["demo"])

    def test_story_engine_is_served(self):
        r = self.c.get("/static/story.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"sceneState", r.data)


class Round6(Base):
    def test_landing_page_embeds_an_honest_guest_dashboard(self):
        import json, re
        r = self.c.get("/")
        m = re.search(rb"window\.__BOOT=(.*?);\s*</script>", r.data, re.S)
        self.assertTrue(m, "boot data missing")
        boot = json.loads(m.group(1))
        d = boot["dashboard"]
        self.assertEqual((d["latest"], d["xp"], d["tasks_total"], d["next"]["kind"], d["streak"]), (None, 0, 0, "quiz", 0))
        self.assertTrue(all(t["status"] == "Not assessed" for t in d["topics"]))
        self.assertEqual(len(boot["meta"]["topics"]), 8)
        self.assertEqual(d["starter"]["topic"], "var")
        for it in boot["module"]["items"]:
            self.assertNotIn("answer", it)

    def test_guest_preview_endpoints_need_no_learner_but_reject_bad_ones(self):
        self.assertEqual(self.c.get("/api/dashboard").status_code, 200)
        self.assertEqual(self.c.get("/api/dashboard?learner=").status_code, 200)
        self.assertEqual(self.c.get("/api/dashboard?learner=a").status_code, 400)
        self.assertEqual(self.c.get("/api/modules/var").status_code, 200)
        self.assertEqual(self.c.get("/api/modules/var?learner=%3Cb%3E").status_code, 400)
        self.assertEqual(self.c.get("/api/progress").status_code, 400)  # private history still needs a nickname
        self.assertEqual(self.c.get("/api/plan?learner=").status_code, 400)

    def test_guest_preview_never_shows_another_learners_data(self):
        self.take("someone1")
        d = self.c.get("/api/dashboard").get_json()
        self.assertEqual((d["latest"], d["xp"], d["timeline"]), (None, 0, []))
        self.assertTrue(all(m["solved"] == 0 for m in d["modules"]))

    def test_rename_moves_all_of_one_learners_records(self):
        self.take("guest-a1b2c3")
        self.c.post("/api/practice", json={"learner": "guest-a1b2c3", "item_id": "PRAC_VAR_1", "selected": A.ITEMS["PRAC_VAR_1"]["answer"]})
        self.take("bystander1")
        before = self.c.get("/api/dashboard?learner=guest-a1b2c3").get_json()
        r = self.c.post("/api/rename", json={"learner": "guest-a1b2c3", "new_name": "Asha_K"})
        self.assertEqual((r.status_code, r.get_json()["name"]), (200, "Asha_K"))
        after = self.c.get("/api/dashboard?learner=Asha_K").get_json()
        for k in ("xp", "attempts", "tasks_total"):
            self.assertEqual(after[k], before[k])
        self.assertEqual(after["latest"]["s"], before["latest"]["s"])
        self.assertEqual(self.c.get("/api/dashboard?learner=guest-a1b2c3").get_json()["attempts"], 0)
        self.assertEqual(len(self.attempts("bystander1")), 1)

    def test_rename_refuses_to_merge_or_accept_bad_names(self):
        self.take("owner11"); self.take("taken11")
        self.assertEqual(self.c.post("/api/rename", json={"learner": "owner11", "new_name": "taken11"}).status_code, 409)
        self.assertEqual(len(self.attempts("owner11")), 1)
        self.assertEqual(len(self.attempts("taken11")), 1)
        for bad in ("", "ab", "has space", "<x>"):
            self.assertEqual(self.c.post("/api/rename", json={"learner": "owner11", "new_name": bad}).status_code, 400)
        self.assertEqual(self.c.post("/api/rename", json={"learner": "x", "new_name": "valid_one"}).status_code, 400)
        self.assertEqual(self.c.post("/api/rename", json={"learner": "owner11", "new_name": "owner11"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
