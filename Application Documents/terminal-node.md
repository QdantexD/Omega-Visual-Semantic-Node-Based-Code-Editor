# Embedded Terminal Node (EN)

## Description
- The `Terminal` node integrates a console inside the node’s content editor.
- Outside edit mode, the node shows only its title for a clean canvas.

## Available profiles
- `PowerShell` (default on Windows), `CMD`, `Git Bash`.
- Each profile is started with appropriate system settings.

## Basic usage
- Double-click the node to open the content editor.
- In the top bar, choose a profile and use the close button to end the session.
- Type commands in the input and press Enter to run them.
- Use `Ctrl+S` to save the terminal transcription as the node’s content.

## Technical integration
- `core/app/node_content_editor_window.py`: sets `EmbeddedTerminal` as `centralWidget` for `Terminal` nodes.
- `core/graph/node_item.py`: hides internal text in non-edit mode; draws only the title.
- `core/graph/node_view.py`: handles canvas interaction and menus.

## Benefits
- Reduced context switching; per-node execution with profiles.
- Work transcription captured inside the graph.
- Minimal canvas appearance for clarity.

## Limitations & notes
- No full PTY; future improvements possible with ConPTY/pywinpty.
- `Git Bash` requires Git for Windows to be installed.
- Closing the editor or application stops the terminal process.