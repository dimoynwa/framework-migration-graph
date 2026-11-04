# Migration Plan: {FRAMEWORK} {FROM} to {TO}
# meta: generated from graph knowledge - do not hand-edit the Rule Ledger
Generated:      {ISO date}
Project:        {absolute PROJECT_ROOT}
Framework:      {FRAMEWORK}
From to To:     {FROM} to {TO}
Research:       inline | ps-migration/{framework}-{from}-to-{to}/research.md
Research-generated: {research artifact Generated timestamp — omit when Research: inline}
Graph snapshot: {knowledge-version id at generation time}

## Preconditions
Complete ALL before starting tasks.
- [ ] Runtime gate: e.g. Java 17 for Boot 3 / Java 21 for Boot 4
- [ ] Namespace boundary: e.g. javax to jakarta applies
- [ ] Co-migration: e.g. Spring Cloud train 2021.x to 2023.x
- [ ] Clean tree: git status clean; branch migration/{FROM}-to-{TO} created

## Scope order (blast radius)
api-surface -> runtime -> config/build -> test

## Rule Ledger
Every matched graph rule, classified by the render table. Source of truth for what each
task in tasks.md derives from.
Columns: RuleID | Scope | EntityMatched | classification | applicability | Render | tasks.md

  {RULE-ID} | {scope} | {entity}
            | {classification} | {applicability} | {TASK|RELEVANCE-INDEX} | {TASK-NNN|(none)}

## Dependency Updates
  {groupId:artifactId} | {current} -> {target} | Paysafe service: {name|none} | {notes}

## OpenRewrite recipes (from build_recipe_plan / search_openrewrite_recipes)
Recipes that back any Executor=openrewrite task.
  {recipe-id} | backs {TASK-NNN, ...} | {full|partial}

## Drift rule
plan.md is a point-in-time snapshot. If execute/clarify re-query the graph and find a
rule changed: file is source of truth for progress/intent; graph is source of truth for
knowledge. On divergence, surface a drift note in tasks.md - never silently re-plan.
