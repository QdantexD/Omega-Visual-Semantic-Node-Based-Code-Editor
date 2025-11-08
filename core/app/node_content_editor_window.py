from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets
from ..ui.text_editor import TextEditor, PythonHighlighter
from ..graph.node_item import EmbeddedTerminal
import os


class NodeContentEditorWindow(QtWidgets.QMainWindow):
    """Ventana ligera para editar el contenido de un nodo.

    - Usa `QPlainTextEdit` con fuente monoespaciada.
    - Botones Guardar y Cerrar.
    - Aplica cambios al `NodeItem` y solicita reevaluación del grafo.
    """

    def __init__(self, node_view, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Editor de Nodo")
        self.resize(700, 500)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self._node_view = node_view
        self._node = None
        # Escucha de reevaluación del grafo para sincronizar el editor
        try:
            if hasattr(self._node_view, 'graphEvaluated'):
                self._node_view.graphEvaluated.connect(self._on_graph_evaluated)
        except Exception:
            pass

        # Dos modos: editor clásico y terminal embebido
        self._is_terminal = False
        # Editor central con números de línea y resaltado
        self.editor = TextEditor()
        self.editor.setPlaceholderText("Escribe el contenido del nodo…")
        self.highlighter = PythonHighlighter(self.editor.document())
        # Debounce para evaluación en vivo (solo en modo editor)
        self._live_timer = QtCore.QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(200)
        self._live_timer.timeout.connect(self._evaluate_live)
        try:
            self.editor.textChanged.connect(self._on_text_changed)
        except Exception:
            pass
        # Terminal embebido
        self._terminal_profile = "PowerShell"
        self.term = EmbeddedTerminal()
        # Por defecto, central = editor
        self.setCentralWidget(self.editor)

        # Toolbar
        tb = QtWidgets.QToolBar("Acciones", self)
        tb.setIconSize(QtCore.QSize(18, 18))
        self.addToolBar(QtCore.Qt.TopToolBarArea, tb)
        act_save = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.SP_DialogSaveButton), "Guardar", self)
        act_close = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCloseButton), "Cerrar", self)
        tb.addAction(act_save)
        tb.addAction(act_close)
        # Acciones de perfil para terminal
        self.act_ps = QtGui.QAction("PowerShell", self)
        self.act_bash = QtGui.QAction("Git Bash", self)
        self.act_cmd = QtGui.QAction("Command Prompt", self)
        self.act_stop = QtGui.QAction("Cerrar terminal", self)
        self.act_ps.triggered.connect(lambda: self._open_terminal_with_profile("PowerShell"))
        self.act_bash.triggered.connect(lambda: self._open_terminal_with_profile("Git Bash"))
        self.act_cmd.triggered.connect(lambda: self._open_terminal_with_profile("Command Prompt"))
        self.act_stop.triggered.connect(self._close_terminal)
        # Agrupar en un menú solo visible cuando el nodo es terminal
        self.term_menu = QtWidgets.QMenu("Abrir terminal (perfil)", self)
        self.term_menu.addAction(self.act_ps)
        self.term_menu.addAction(self.act_bash)
        self.term_menu.addAction(self.act_cmd)
        self.term_menu_action = tb.addAction("Abrir terminal (perfil)")
        self.term_menu_action.setMenu(self.term_menu)
        tb.addAction(self.act_stop)
        # Visibilidad inicial (no terminal)
        self._set_terminal_actions_visible(False)

        # Accesos rápidos
        act_save.setShortcut(QtGui.QKeySequence.Save)

        # Conexiones
        act_save.triggered.connect(self._on_save)
        act_close.triggered.connect(self.close)

    def set_node(self, node) -> None:
        """Establece el nodo activo y carga su contenido."""
        self._node = node
        try:
            title = str(getattr(node, 'title', 'Node') or 'Node')
            self.setWindowTitle(f"Editar: {title}")
        except Exception:
            pass
        # Modo según tipo de nodo
        node_type = str(getattr(node, 'node_type', '')).lower()
        self._is_terminal = (node_type == 'terminal')
        self._set_terminal_actions_visible(self._is_terminal)
        if self._is_terminal:
            # Activar terminal embebido como central y arrancar proceso
            self.setCentralWidget(self.term)
            try:
                self.term.start(profile=self._terminal_profile, cwd=os.getcwd())
            except Exception:
                pass
        else:
            # Editor clásico
            self.setCentralWidget(self.editor)
            try:
                if hasattr(node, 'to_plain_text'):
                    text = node.to_plain_text()
                else:
                    text = str(getattr(node, 'content', '') or '')
                self.editor.setPlainText(text)
                # Colocar cursor al final
                cursor = self.editor.textCursor()
                cursor.movePosition(QtGui.QTextCursor.End)
                self.editor.setTextCursor(cursor)
            except Exception:
                pass

    def _on_save(self) -> None:
        if self._node is None:
            return
        if self._is_terminal:
            # Guardar buffer del terminal como contenido del nodo
            try:
                text = self.term.buffer_text()
            except Exception:
                text = ""
        else:
            try:
                text = self.editor.toPlainText()
            except Exception:
                text = ""
        # Aplicar al nodo
        try:
            if hasattr(self._node, 'update_from_text'):
                self._node.update_from_text(text)
            else:
                self._node.content = text
            self._node.update()
        except Exception:
            pass
        # Re-evaluar el grafo
        try:
            if hasattr(self._node_view, 'evaluate_graph'):
                self._node_view.evaluate_graph()
        except Exception:
            pass
        # Feedback
        try:
            self.statusBar().showMessage("Nodo guardado", 1500)
        except Exception:
            pass

    def _on_text_changed(self) -> None:
        if not self._is_terminal:
            try:
                self._live_timer.start()
            except Exception:
                pass

    def _evaluate_live(self) -> None:
        if self._is_terminal:
            return
        try:
            if self._node is not None:
                text = self.editor.toPlainText()
                if hasattr(self._node, 'update_from_text'):
                    self._node.update_from_text(text)
                else:
                    self._node.content = text
                self._node.update()
            if hasattr(self._node_view, 'evaluate_graph'):
                self._node_view.evaluate_graph()
        except Exception:
            pass

    def _on_graph_evaluated(self) -> None:
        """Si el nodo es de tipo Output, sincroniza el texto con sus entradas."""
        try:
            if self._node is None:
                return
            node_type = str(getattr(self._node, 'node_type', '')).lower()
            if node_type not in ('output', 'group_output'):
                return
            parts = []
            for p in (getattr(self._node, 'input_ports', []) or []):
                name = p.get('name', 'input')
                val = (getattr(self._node, 'input_values', {}) or {}).get(name, None)
                if val is None:
                    continue
                if isinstance(val, list):
                    for sv in val:
                        if sv is not None:
                            parts.append(str(sv))
                else:
                    parts.append(str(val))
            text = "\n".join(parts)
            # Fallback: si no hay entradas, mostrar el contenido actual del nodo
            if not text:
                try:
                    text = self._node.to_plain_text()
                except Exception:
                    text = str(getattr(self._node, 'content', '') or '')
            # Actualiza el editor sólo si difiere
            try:
                if text != self.editor.toPlainText():
                    self.editor.blockSignals(True)
                    self.editor.setPlainText(text)
                    self.editor.blockSignals(False)
                    # Cursor al final
                    cur = self.editor.textCursor()
                    cur.movePosition(QtGui.QTextCursor.End)
                    self.editor.setTextCursor(cur)
                    self.statusBar().showMessage("Contenido sincronizado desde entradas", 1200)
            except Exception:
                pass
        except Exception:
            pass

    # Helpers de terminal
    def _set_terminal_actions_visible(self, visible: bool) -> None:
        try:
            self.term_menu_action.setVisible(visible)
            self.act_stop.setVisible(visible)
        except Exception:
            pass

    def _open_terminal_with_profile(self, profile: str) -> None:
        self._terminal_profile = profile or "PowerShell"
        if self._is_terminal:
            try:
                self.term.start(profile=self._terminal_profile, cwd=os.getcwd())
            except Exception:
                pass

    def _close_terminal(self) -> None:
        if self._is_terminal:
            try:
                self.term.stop()
            except Exception:
                pass

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        # Asegurar que el proceso del terminal embebido se detenga
        try:
            self._close_terminal()
        except Exception:
            pass
        return super().closeEvent(event)


__all__ = ["NodeContentEditorWindow"]