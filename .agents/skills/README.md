# Custom Agent Skills

This directory (`.agents/skills/`) contains custom skills available to AI agents working in this workspace.

## Skill Structure
Each skill should be placed in its own subfolder containing a `SKILL.md` file:

```
.agents/skills/
└── my-custom-skill/
    ├── SKILL.md
    └── (optional scripts, templates, or reference files)
```

### `SKILL.md` Example Format

```yaml
---
name: my-custom-skill
description: Brief description of when to use this skill
---

# Instructions
Detailed steps and guidelines for executing this skill...
```
