# Panels & Windows (EN)

## Main Window (Editor)
- Node canvas (blueprint) with zoom and pan.
- Bottom bar with view controls.
- Access to panels: inspector, realtime variables, code map.

## NodeContentEditorWindow (Node Content Editor)
- Shows the editor associated with the selected node.
- For `Terminal` nodes, embeds `EmbeddedTerminal` as the `centralWidget`.
- Actions: choose terminal profile, close terminal, save (`Ctrl+S`).

## BlueprintEditorWindow
- Hosts graph display and editing logic.
- Manages global shortcuts and view actions.

## RealtimeVariablesPanel
- Observe and update variables and state during runtime.

## CodeEditorWindow & TextEditor
- For non-terminal nodes: classic text/code editing.
- Supports tab-completion and standard editor shortcuts.

## Node Inspector
- Node properties: type, name, metadata.
- Access via UI for quick adjustments.