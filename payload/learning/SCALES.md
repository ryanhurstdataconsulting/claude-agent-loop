# Task Outcome Scales
<!-- Format: | scale-id | levels best>worst | applies-to | description | ·
     one scale per line · budget 40 rows -->
<!-- Lint after ANY edit: python3 ~/.claude/tools/lint_scales.py -->
<!-- Self-scored after a task (SKILL v2 SCORE step, P3); HEURISTICS.md rules
     read against these levels. Extend with
     `score_task.py --new-scale id --levels "a>b>c"` rather than hand-editing
     a row out of order. -->

## Core (framework seed)
| outcome | great>good>bad>horrible | any task | Subjective self-score of how the task's result turned out |
| ui | pretty>ok>ugly | any UI/report/deliverable-producing task | Subjective self-score of the visual or presentation quality produced |
| rework | none>minor>major | any task | How much the user had to redo or correct after delivery |
| evidence | proven>partial>asserted | any task | How well the outcome claim is backed by verifiable evidence |

## Extended (learned on this machine)
