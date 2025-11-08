# Quick Start (EN)

## Requirements
- Windows with Python 3.10+.
- Dependencies: `pip install -r requirements.txt`.
- Optional: Git Bash installed to enable the `Git Bash` terminal profile.

## Launch the app
- Run `main.py` to open the main editor.
- Open or create a blueprint (node graph).

## Create and use a Terminal node
- Add a node and set its type to `Terminal`.
- Double-click the node to open its content editor (secondary window).
- Use the top bar to choose a profile: PowerShell, CMD, or Git Bash.
- Type commands and press Enter to execute.
- Use `Ctrl+S` to save the terminal transcription into the node’s content.
- Use the “Close embedded terminal” action to stop the terminal process.

## Basic workflow
- Create nodes (variables, functions, terminal, etc.) and connect inputs/outputs.
- Right-click a node to open its context menu.
- Zoom and pan the canvas to organize your graph.
- Save the project from the main window and the content editor.

## Key concepts
- Outside of edit mode, `Terminal` nodes show only the title for a clean view.
- In edit mode, `NodeContentEditorWindow` embeds the terminal as the central widget.
- On save, the terminal’s text transcription is persisted in the node.