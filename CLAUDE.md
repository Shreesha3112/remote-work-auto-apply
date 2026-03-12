# CLAUDE.md — Project Instructions

## 1. Always Commit & Push After Changes

After any file modification (code, config, docs, YAML), commit and push immediately:

```bash
git add <files>
git commit -m "<descriptive message>"
git push origin main
```

- Use descriptive commit messages that explain *why*, not just *what*
- Never leave the working tree dirty at the end of a task

## 2. Use uv for All Python Operations

**Never use** `pip install`, `pip uninstall`, or bare `python <file>`.

| Task | Command |
|------|---------|
| Add a dependency | Add to `[project.dependencies]` in `pyproject.toml`, then `uv sync` |
| Remove a dependency | Remove from `pyproject.toml`, then `uv sync` |
| Run the app | `uv run run.py` |
| Run tests | `uv run pytest` |
| Run any script | `uv run <script>` |

uv manages `.venv/` automatically via `uv sync`.

## 3. Git Worktrees for Parallel Independent Tasks

When 2+ independent tasks arrive in one session, use a worktree per task:

```bash
# Create a worktree with its own branch
git worktree add .worktrees/<task-name> -b <task-name>

# Open a parallel Claude Code session in each worktree
# After completion, merge back to main and push
git checkout main
git merge <task-name>
git push origin main
git worktree remove .worktrees/<task-name>
```

Only use worktrees for tasks with no shared file dependencies.
