# LearnWise AI by FutureMinds

Personalized Python learning: diagnostic quiz, interactive learning modules, a persistent study plan, rewards, and a progress dashboard.
Built for INOVATORS 2026 (EdTech + AI/ML). A learning-support prototype, not a grading tool.

## What it does
Nickname -> **Dashboard** (next best step) -> **Assessments** (24-question quiz, 3 per topic) -> results with explanations -> **Learn** (module + practice) -> **My Study Plan** (saved tasks) -> retake -> **My Progress**.
- **Dashboard:** welcome and goal, four overview cards, "Continue learning", topic mastery estimates, weekly plan by day, recent activity, rewards. Every number comes from the database; new learners see empty states.
- **Learn:** 8 modules (explanation, analogy, syntax-highlighted example, 2 practice items: predict the output, find the bug, instant constructive feedback, key takeaway). Practice items are fixed multiple choice. No user code is ever executed.
- **Rewards (optional, can be hidden):** XP, levels, 5 badges, weekly goal, streak. XP is saved in the database and awarded once per real event: finished real quiz +30, study task +10, correct first-try practice +10, module finished +20. Demo data never earns XP. Missing a day costs nothing.

## First visit and returning visitors
- A first-time visitor sees the real dashboard immediately (its empty-state values are embedded in the page, so there is no loading screen) with a **welcome overlay** on top: type a nickname and press "Start My Learning Journey". The overlay closes and the dashboard becomes personal. Nothing is made up: a new learner sees 0%, "No quiz yet", an empty activity chart, a first goal and a starter lesson.
- **Skip for now** (or Esc) continues as a guest with a private random id such as `guest-3fa91c`, so every feature works and progress is saved. Later, the profile menu (top right) lets a guest or anyone **change nickname**: all of that learner's records move to the new name. It refuses if the new name already has history, so two learners are never merged.
- A returning visitor (saved nickname on this device) goes straight to their dashboard. "Switch learner" in the profile menu shows the overlay again.

<<<<<<< HEAD
=======
<<<<<<< HEAD
## 3D animated visual design
- The dashboard now opens with an animated 3D learning orb, orbiting rings, floating learning icons and a glowing “learning universe” banner.
- Navigation and inline icons have subtle 3D levitation and hover depth; dashboard cards respond to desktop pointer movement with a restrained tilt.
- Animations respect the operating system’s reduced-motion setting, and the layout adapts to phones with smaller orbit elements. These effects are CSS-based and do not require Three.js, a GPU library, or an internet connection.

=======
>>>>>>> bafc6c70e4b365c7312d29c5291bc8befb9fd373
>>>>>>> 9af3b78287195db6e0e4f9ae498749008cb512fe
## Cinematic scroll dashboard
The Dashboard is the first thing every visitor sees. It is a six-scene story: **Dashboard**, **Your journey**, **Skills**, **Practice**, **Achievements**, **Next step**. Scrolling shrinks the dashboard back (with a slight tilt) while the next scene zooms in from behind it. Everything shown is real data: progress rings (modules completed, latest quiz score), a 7-day activity chart, the learning path, mastery bars, XP, streak and badges. New learners see empty states, never invented numbers. The practice challenge in scene 4 uses the same modules and server-checked answers as the Learn page.
- **How it works:** one tall container with a sticky stage; `static/story.js` turns scroll position into scale, opacity, tilt and shift using transforms only, with `requestAnimationFrame`, light smoothing, and shrink-to-fit so panels are never clipped. The page never traps scrolling.
- **Three modes:** *cinematic* on screens at least 900x520 (the full zoom-out / zoom-in); *lite* on phones, tablets and short screens (the page flows normally and each panel gently scales and fades in as it rises into view, so text is never shrunk); *plain* when "reduce motion" is on, when you pick "Use simple view" in the profile menu, or if `story.js` fails to load.
- **Orientation:** dots on the right (cinematic mode) and a thin scroll-progress line under the header. Metrics such as XP, level and streak have hover/focus tooltips.
- **Keyboard and screen readers:** the dots on the right jump between scenes; scenes that are not in view are `inert`, so Tab only reaches what you can see.

## What is rules, calculations, and ML
- **Rules:** status bands (below 50% Needs practice, 50-79% Developing, 80%+ Strong), prerequisite ordering, plan building, next-step choice, badges. Thresholds are in `logic.py` and are starting rules, not validated measures of ability.
- **Calculations:** topic score = correct / asked; topics are ranked with a cautious estimate `(correct+1)/(asked+2)`; streaks and XP totals.
- **Machine learning:** none yet. Needs real attempts first: aim for 30+ learners with 2+ attempts. Export them from `/export.csv`. Planned: predict whether a learner answers a topic question correctly using earlier attempts only, compared with a "previous topic score" baseline, with a learner-aware split. Never train on demo data.

## Setup (Windows, VS Code, no script activation needed)
1. VS Code: File > Open Folder > this folder. Terminal > New Terminal.
2. `py -m venv .venv`
3. `.venv\Scripts\python.exe -m pip install -r requirements.txt`
4. `.venv\Scripts\python.exe app.py`
5. Open http://127.0.0.1:5000

Tests: `.venv\Scripts\python.exe -m unittest discover -s tests -v` (temporary database, 49 tests).
Optional browser-like test (needs Node.js): run the app on port 5055 (`.venv\Scripts\python.exe -c "import app; app.app.run(port=5055)"`), then `npm install jsdom` and `node tests/ui_smoke.js`. It uses a simulated browser, not a real one.
macOS/Linux: use `python3` and `.venv/bin/python`.

## Folder structure
- `app.py` routes, SQLite, validation, rewards, export
- `logic.py` scoring, thresholds, plan rules, rewards rules, validators
- `data/questions.json` 48 quiz questions (easy/medium/hard), answer keys stay on the server
- `data/modules.json` 8 learning modules and 16 practice items
- `data/resources.json` 16 resources (lesson summary + official tutorial link, worked example)
- `templates/index.html` the single-page app and dark futuristic theme (no external fonts or libraries)
- `static/story.js` the scroll animation engine (about 150 lines, no dependencies)
- `tests/test_app.py` 49 automated tests; `tests/engine_test.js` scroll-animation maths (7 tests, `node tests/engine_test.js`); `tests/ui_smoke.js` optional journey and scroll-wiring test

## Data and privacy
- Use nicknames, not real names. A nickname is NOT a password: anyone who types the same nickname sees its data, and anyone who knows a nickname could rename it. Private history endpoints (`progress`, `plan`, `practice`, ...) always require a valid nickname; only the empty guest preview works without one. Changing the nickname discards a quiz in progress.
- Data is stored in `learnwise.db` on your computer. Delete the file to reset everything.
- Demo history is flagged, loaded once per learner, excluded from export and rewards. Progress page: "Remove demo data only" keeps real attempts; "Delete all my attempts" also removes that nickname's XP, badges and practice records.
- Export: http://127.0.0.1:5000/export.csv (real answer-level data, this computer only). To allow other machines set `LEARNWISE_EXPORT_KEY` (see `.env.example`) and use `?key=`. Add `?learner=nickname` for one learner.
- Answer positions were rebalanced (each of A-D is correct equally often). In an older `learnwise.db`, the stored `selected` position no longer matches the new option order; `is_correct` stays valid.
- Security is prototype-level (no login). Run it on localhost. A real deployment needs accounts, authorization, HTTPS and a privacy review.

## Status
<<<<<<< HEAD
- Latest finishing pass: added a dedicated Resources navigation page and `/api/resources` catalogue. Students can filter the 16 curated resources by topic, read offline notes, open official external documentation when available, or jump directly into topic practice.
- Complete: dashboard redesign, 6-item navigation including a topic-filtered resource library, learning modules with practice and feedback, rewards with idempotent XP and badges, weekly plan with saved task completion, prerequisite-aware recommendations, results with strengths and next lessons, demo flag, migration, export, logging, tests.
=======
<<<<<<< HEAD
- Latest visual pass: added the 3D animated learning-universe banner, orbiting orb, floating icons, subtle 3D icon motion and pointer-responsive cards.
- Latest finishing pass: added a dedicated Resources navigation page and `/api/resources` catalogue. Students can filter the 16 curated resources by topic, read offline notes, open official external documentation when available, or jump directly into topic practice.
- Complete: dashboard redesign, 6-item navigation including a topic-filtered resource library, learning modules with practice and feedback, rewards with idempotent XP and badges, weekly plan with saved task completion, prerequisite-aware recommendations, results with strengths and next lessons, demo flag, migration, export, logging, tests.
=======
<<<<<<< HEAD
- Latest finishing pass: added a dedicated Resources navigation page and `/api/resources` catalogue. Students can filter the 16 curated resources by topic, read offline notes, open official external documentation when available, or jump directly into topic practice.
- Complete: dashboard redesign, 6-item navigation including a topic-filtered resource library, learning modules with practice and feedback, rewards with idempotent XP and badges, weekly plan with saved task completion, prerequisite-aware recommendations, results with strengths and next lessons, demo flag, migration, export, logging, tests.
=======
- Complete: dashboard redesign, 5-item navigation, learning modules with practice and feedback, rewards with idempotent XP and badges, weekly plan with saved task completion, prerequisite-aware recommendations, results with strengths and next lessons, demo flag, migration, export, logging, tests.
>>>>>>> 53e2e8729e4d0cf9dddc96aa4343e28719bfa8a7
>>>>>>> bafc6c70e4b365c7312d29c5291bc8befb9fd373
>>>>>>> 9af3b78287195db6e0e4f9ae498749008cb512fe
- Partial: the scroll effect was tested by unit-testing its maths and by a simulated browser (jsdom) with simulated scroll positions, never in a real browser, so check smoothness, spacing and clipping on your own laptop and phone before presenting; the app is now dark-theme only (no light mode); navigation labels are Dashboard, Learn & Practice, Assessments, My Study Plan and My Progress; there is no celebration animation beyond toast messages; practice formats are predict-the-output and find-the-bug only (no fill-in-the-code); the learning content covers the 8 core topics (not tuples, exceptions, files, OOP); layout was checked in a simulated browser and by computed colour contrast, not on real devices or with a screen reader; docs.python.org links: controlflow.html was found in a search, datastructures.html only through a mirrored copy, introduction.html only for an older Python version, errors.html not confirmed. Open all four before the demo (offline summaries always shown).
- Not implemented: ML model, grounded study assistant, teacher view, login, leaderboards (deliberately omitted).

## Demo script (3-5 min)
1. Open the site in a private window: the dashboard appears at once with the welcome overlay. Enter `judge1`: honest empty states, starter lesson, no ML claims. (For a fuller dashboard, take the quiz first or use a nickname that has history.)
2. Assessments: take the quiz (answer some wrong), review screen, submit. Show +XP toast.
3. Dashboard again: scroll slowly. The dashboard zooms back while Your journey, Skills, Practice and Achievements zoom in (the dots jump between scenes; Simple view turns the effect off). Results page: explanations, "What this suggests". Dashboard: real score, topics to improve, Continue learning.
4. Learn: open the recommended module, answer a wrong option (constructive feedback), then the right one.
5. My Study Plan: tick a task, refresh the page, it stays ticked. Dashboard shows it done.
6. Optional: "Load demo history" on a different nickname to show the progress chart (labelled demo).
7. Architecture: browser -> Flask -> SQLite; answers never reach the browser before submission.

## Troubleshooting
- "Cannot reach the server": app.py is not running.
- Port busy: close the other terminal running app.py.
- Pip errors: check internet, rerun step 3.
