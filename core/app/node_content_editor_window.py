from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets
from ..ui.text_editor import TextEditor, PythonHighlighter


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

        # Editor central con números de línea y resaltado
        self.editor = TextEditor()
        self.editor.setPlaceholderText("Escribe el contenido del nodo…")
        self.highlighter = PythonHighlighter(self.editor.document())
        # Debounce para evaluación en vivo
        self._live_timer = QtCore.QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(200)
        self._live_timer.timeout.connect(self._evaluate_live)
        try:
            self.editor.textChanged.connect(self._on_text_changed)
        except Exception:
            pass
        self.setCentralWidget(self.editor)

        # Toolbar
        tb = QtWidgets.QToolBar("Acciones", self)
        tb.setIconSize(QtCore.QSize(18, 18))
        self.addToolBar(QtCore.Qt.TopToolBarArea, tb)
        act_save = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.SP_DialogSaveButton), "Guardar", self)
        act_close = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCloseButton), "Cerrar", self)
        tb.addAction(act_save)
        tb.addAction(act_close)

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
        try:
            self._live_timer.start()
        except Exception:
            pass

    def _evaluate_live(self) -> None:
        try:
            if self._node is not None:
                # Aplicar texto al nodo para que la evaluación use el contenido actual
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
            if node_type != 'output':
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


__all__ = ["NodeContentEditorWindow"]