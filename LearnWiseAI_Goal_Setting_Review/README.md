# Student Goal Setting and Review Tool

A Flask + SQLite web prototype for recording academic and personal goals, tracking progress, documenting challenges, and generating self-assessment reports. It uses learner nicknames as the only identity, plain JavaScript in the browser, and no trained ML model or heavy dependencies.

## Official problem statement

**Student Goal Setting and Review Tool**

Setting clear academic and personal goals helps students improve self-discipline, monitor progress, and achieve long-term success. However, students often struggle to track their objectives and evaluate their achievements systematically. A structured goal management system is required to record personal and academic goals, monitor progress over time, evaluate goal completion, document challenges faced during execution, and generate self-assessment reports that encourage continuous personal and academic development.

## Features

- Create academic or personal goals with a description, deadline, and action steps.
- Server-side validation for goal data and rejection of deadlines before today.
- Update goal title, description, category, and deadline; add/remove action steps; delete a goal and its related records.
- Record progress (0–100%), achievements/reflections, challenges and responses, status, and satisfaction (1–5).
- Protect completed/abandoned goals from review until the learner explicitly reopens them. Completed reviews are recorded at 100%.
- Mark ongoing goals past their deadline as overdue.
- Self-assessment report with completion rate, overdue count, satisfaction average, academic/personal breakdown, actual challenge/response text, and per-goal progress-over-time SVG charts.
- Print or save the report as PDF using the browser print dialog.
- Feedback is saved locally to SQLite.

## Setup (Windows / PowerShell)

From the folder containing `app.py` and `requirements.txt`:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000.

Run automated tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Main routes

- `GET /api/goals?learner=<nickname>` — goals and related steps/logs/challenges.
- `POST /api/goals` — create a goal.
- `PUT /api/goals/<id>` — edit goal details.
- `DELETE /api/goals/<id>` — delete a goal and dependent records.
- `POST /api/goals/<id>/review` — save a review.
- `POST /api/goals/<id>/reopen` — explicitly reopen a closed goal.
- `POST /api/goals/<id>/step` — toggle a step.
- `POST /api/goals/<id>/steps` and `DELETE /api/goals/<id>/steps/<step_id>` — add/remove steps.
- `GET /api/reports?learner=<nickname>` — report calculations and per-goal history.
- `POST /api/feedback` — save feedback.

## Data and limitations

Data is stored in `learnwise.db` beside `app.py`. Nicknames are not passwords: anyone who knows a nickname can access that learner's records. This is a local classroom prototype, not a secure multi-user deployment. Report calculations are deterministic summaries of recorded data, not validated psychological measures. The chart is inline SVG and has no external dependency. The original quiz and learning assets remain in the repository but are hidden from the main navigation; the goal workflow is the primary user experience.
