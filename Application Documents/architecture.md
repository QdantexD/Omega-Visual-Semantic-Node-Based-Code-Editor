# Basic Architecture (EN)

## Key components
- `core/graph/node_item.py`: paints nodes; manages edit/view modes. For `Terminal`, hides internal text outside edit mode.
- `core/graph/node_view.py`: graph view; node interactions and connections; context menus.
- `core/app/node_content_editor_window.py`: node content editor. For `Terminal`, sets `EmbeddedTerminal` as central widget.
- `core/app/blueprint_editor_window.py`: main graph window; editor lifecycle.
- `core/app/editor_window.py`: base editor window framework.
- `core/graph/runtime.py`: runtime execution and logic.
- `core/ui/text_editor.py`: text editor for non-terminal nodes.

## Terminal node edit flow
- On entering edit (double-click): `NodeContentEditorWindow` opens and `EmbeddedTerminal` is instantiated.
- The terminal starts with a default profile (PowerShell) and can be changed via actions in the top bar.
- On save (`Ctrl+S`): the terminal buffer is persisted as the node’s content.
- On exit/close: the terminal process stops; the node shows only the title.

## Painting and clean view
- `node_item.py` disables the `PS ...` overlay and any extra height compensation for terminals in non-edit mode.
- This prevents duplicated text and keeps a minimal aesthetic.

## Context menu and actions
- `node_view.py` and related components enable profile actions and closing the terminal.
- Actions are restricted to nodes of type `Terminal`.

## Extension notes
- ConPTY/pywinpty can be integrated to improve console emulation.
- Additional profiles can be added via actions and specific configurations.