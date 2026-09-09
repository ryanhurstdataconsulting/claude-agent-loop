<!-- BEGIN AGENT-LOOP -->
<!-- Managed block, installed by the claude-agent-loop environment. Replaced
     wholesale on re-install from payload/fragments/CLAUDE.starter.md. Edit that
     source, not here; anything added inside these sentinels is overwritten. -->

## Machine-global protocol (framework layer)

This environment's cross-machine protocols are reference-on-demand: the detail lives
in Skills and docs, pulled only when a task needs them, not restated inline every
turn. Resource Loop: `Skill(resource-loop)`. Token and context discipline:
`Skill(token-efficiency)`. Output quality and the grammar gate:
`Skill(prose-style-lint)` plus `tools/prose_grammar_gate.py`. Data visualization:
`Skill(data-visualization)`. Project timelines: `Skill(project-timeline)`. Subagent
routing: `docs/subagent-routing.md`. Run the `environment-bootstrap` skill to author
your machine-specific rules above these sentinels; those numbered rules are
canonical for this machine and are carried into every subagent brief.
<!-- END AGENT-LOOP -->
