---
name: generate-qwen-from-codebase
description: Generate a comprehensive QWEN.md by iteratively exploring a codebase — start with README, then deep-dive into configs, source, tests, and business context
source: auto-skill
extracted_at: '2026-06-08T15:24:47.150Z'
---

# How to generate a comprehensive QWEN.md from a codebase

## Overview

When asked to generate or regenerate `QWEN.md` for a project, follow this systematic, iterative exploration procedure. Do **not** read all files upfront — let findings guide what to read next.

## Procedure

### Step 1 — Initial exploration
1. List the top-level directory to get a high-level view.
2. Read the README (any variant: `README.md`, `README.txt`). This is the single best starting point.
3. Note the project type early — code project (has `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `Makefile`, `src/` etc.) vs non-code project (docs, research, notes).

### Step 2 — Read key config files (the "identity" files)
Read at least these to understand the tech stack, dependencies, and build system:
- Build config: `pyproject.toml` / `package.json` / `go.mod` / `Cargo.toml` / `pom.xml` / `build.gradle`
- Environment template: `.env.example` / `.env.sample`
- Docker: `docker-compose.yml`, `Dockerfile` (if present)
- Test config: `pytest.ini`, `jest.config.js`, etc.
- Code quality: `ruff.toml`, `.eslintrc`, `.golangci.yml`, etc.

### Step 3 — Deep-dive into source code (guided by discoveries)
Read **up to ~15 files** total, choosing the order based on what you learn. Priority:
1. **Entry point** — `main.py`, `app.py`, `index.tsx`, `cmd/main.go` etc.
2. **Config/settings module** — where env vars are loaded and settings defined.
3. **Core models/schemas** — to understand the data model and domain.
4. **Key service files** — to understand business logic patterns.
5. **Router/controller files** — to understand API surface or UI structure.
6. **Background task infra** — Celery config, sidekiq, cron jobs, etc.
7. **CI/CD** — `.github/workflows/`, `.gitlab-ci.yml`, etc.

If the project has a `state/`, `docs/`, `backlog/`, or `marketing/` directory, read those too — they often contain critical business context (ICP, pricing, roadmap, constraints).

### Step 4 — Cover testing and infrastructure
- Read `locustfile.py`, benchmark files (if present)
- Check `tests/` directory to understand test approach and coverage
- Read `Dockerfile` variants (dev, prod, ml-specific etc.)

### Step 5 — Synthesize into QWEN.md

Write `QWEN.md` with the following sections (tailor sections to project type):

#### For code projects:
- **Project Overview** — purpose, main technologies, architecture style (monolith, monorepo, microservices)
- **Tech Stack** — language, framework, ORM, broker, database, external APIs, ML stack, testing
- **Building & Running** — exact commands for venv/setup, dev server, tests, linter, docker, load testing
- **Project Structure** — annotated tree of directories with descriptions of what each contains
- **Architecture & Key Design Decisions** — layering, auth strategy, DB approach (migrations vs auto-create), background jobs, external integrations, business rules/constraints
- **Development Conventions** — formatting rules, typing requirements, import style, component patterns for frontend, Docker patterns
- **Important constraints** — human-gates, approval queues, rate limits, security restrictions

#### For non-code projects:
- **Directory Overview** — what is this directory for?
- **Key Files** — list important files with brief descriptions
- **Usage** — how the contents are intended to be used

### Formatting rules for QWEN.md
- Use proper Markdown headings (##, ###, ####)
- Use tables for structured data (schedule, comparison)
- Use code blocks with language tags for commands, configs
- Keep it comprehensive but readable — not a dump of every file's content
- Link to relevant files/folders where helpful

## Rationale for this approach

**Why iterative deep-dive instead of reading everything?** — The project's true structure and conventions only become apparent after reading a few files. Reading everything upfront wastes time and misses the forest for the trees. Let each discovery decide the next file.

**Why include business context?** — QWEN.md is not just a technical reference; future AI agents reading it need to understand constraints (human-gate billing, approval queues, rate limits) to act safely.

**Why ~15 files and not fewer?** — Fewer files risks missing critical details (e.g., Celery schedule, test patterns, Docker profile). More files risks information overload. 15 is a good heuristic for a mid-size project.
