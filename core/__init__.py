"""
Fachada del paquete `core`.

Reexporta las clases y utilidades más usadas para permitir imports cómodos, por ejemplo:

    from core import EditorWindow, NodeView, GraphRuntime

Esto evita tener que navegar por subpaquetes como `core.graph` o `core.app`.
"""

# --- Graph (nodos y conexiones) ---
from .graph.node_view import NodeView
from .graph.node_item import NodeItem
from .graph.connection_item import ConnectionItem
from .graph.node_model import NodeModel
from .graph.runtime import GraphRuntime
from .graph.connection_logic import PassthroughLogic, ListAccumLogic

# --- App (ventanas principales) ---
from .app.editor_window import EditorWindow
from .app.node_view_adapter import MyNodeGraphController

# --- UI (widgets auxiliares) ---
from .ui.file_explorer import FileExplorer
from .ui.text_editor import TextEditor, PythonHighlighter
from .ui.node_inspector import NodeInspector

__all__ = [
    # Graph
    "NodeView",
    "NodeItem",
    "ConnectionItem",
    "NodeModel",
    "GraphRuntime",
    "PassthroughLogic",
    "ListAccumLogic",
    # App
    "EditorWindow",
    "MyNodeGraphController",
    # UI
    "FileExplorer",
    "TextEditor",
    "PythonHighlighter",
    "NodeInspector",
]