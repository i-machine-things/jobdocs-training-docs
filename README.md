# jobdocs-training-docs

An external JobDocs plugin for creating and browsing training guides. Organises guides by category, tracks metadata, and stores associated files (PDFs, Word docs, images) in a structured folder layout.

## Features

- Create training guides with auto-generated guide numbers (`TG001`, `TG002`, …)
- Attach any files to a guide via drag-and-drop or file picker
- Browse all guides in a searchable, category-grouped tree
- Open guide folders or individual files directly from the plugin

## Requirements

- JobDocs with external plugin support
- No additional Python packages required

## Setup

1. Clone or copy this folder alongside `JobDocs/` (sibling directory):
   ```text
   H:\Jobdocs\
   ├── JobDocs\
   └── jobdocs-training-docs\
   ```
2. In JobDocs Settings, set **Plugins Folder** to the parent directory (`H:\Jobdocs\`).
3. Restart JobDocs — the **Training Docs** tab appears automatically.
4. In the plugin's **Training Guides Folder** bar, click **Browse** and select (or create) the folder where guides will be stored.

## Usage

### Create Guide tab

1. Enter a guide number or click **Auto** to generate the next `TG###`.
2. Fill in Title (required), Category, Revision, and Description.
3. Add files via **Add Files…** or drag-and-drop onto the list.
4. Click **Create Guide** — a numbered folder is created and files are copied in.

### Browse Guides tab

- Type in the search box to filter by title or category, then press **Search**.
- Click a guide in the tree to see its files in the right panel.
- Use **Open Folder** or **Open File** to open items in the system file manager.

## Guide Folder Layout

Each guide is stored as a subfolder under the configured training directory:

```text
Training Guides/
└── TG001_Onboarding/
    ├── training_meta.json   # Guide metadata
    ├── onboarding.pdf
    └── checklist.docx
```

`training_meta.json` contains: guide number, title, category, revision, description, created timestamp, and file list.

## Plugin Structure

```text
jobdocs-training-docs/
├── __init__.py
├── module.py          # TrainingDocsModule(BaseModule)
├── requirements.txt
├── ui/
│   └── training_tab.ui
└── .claude/
    ├── CLAUDE.md
    ├── S&P.md
    ├── settings.json
    └── hooks/
        └── pre_commit_sp_check.py
```

## Development

This plugin is forked from [jobdocs-plugin-template](../jobdocs-plugin-template).
Changes to shared template files (`.claude/CLAUDE.md`, `.claude/S&P.md` structure,
`settings.json`, `hooks/`, `README.md` structure) must be PR'd back to the template
repo before or alongside merging here.

See `.claude/CLAUDE.md` for the full branching, commit, and review workflow.

> **Note:** The pre-commit S&P hook (`.claude/hooks/pre_commit_sp_check.py`) is triggered
> via Claude Code's `PreToolUse` hook, not by a standard `git commit` hook. It runs when
> Claude Code executes a `git commit` bash command. Plain `git commit` from a terminal
> bypasses it by design — the check is Claude-only.
