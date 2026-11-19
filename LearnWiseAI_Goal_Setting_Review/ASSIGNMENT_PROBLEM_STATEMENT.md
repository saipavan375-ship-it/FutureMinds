# Student Goal Setting and Review Tool

## Official Problem Statement

Setting clear academic and personal goals helps students improve self-discipline, monitor progress, and achieve long-term success. However, students often struggle to track their objectives and evaluate their achievements systematically. A structured goal management system is required to record personal and academic goals, monitor progress over time, evaluate goal completion, document challenges faced during execution, and generate self-assessment reports that encourage continuous personal and academic development.

## How LearnWise AI addresses the problem

1. **Record goals:** Create academic or personal goals with a description and target deadline.
2. **Plan execution:** Add smaller action steps and check them off as they are completed.
3. **Monitor progress:** Save dated progress percentages and notes over time.
4. **Document challenges:** Record obstacles and possible responses while reviewing a goal.
5. **Evaluate completion:** Keep each goal marked ongoing, completed, or abandoned.
6. **Generate self-assessment:** Review total goals, average progress, completed goals, action-step completion, recent reflections, and recorded challenges. The report can be printed or saved as a PDF from the browser.

## Implementation note

The prototype stores goal records in a local SQLite database and separates them by learner nickname. Its report uses recorded information and transparent calculations. It does not claim to use a trained machine-learning model.
