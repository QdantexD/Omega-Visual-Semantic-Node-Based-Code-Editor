from __future__ import annotations

from typing import Dict, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ..ui.text_editor import TextEditor
from ..graph.node_item import NodeItem


class OutputPreviewWindow(QtWidgets.QMainWindow):
    """Ventana de preview en vivo para todos los nodos de tipo Output.

    - Crea pestañas por cada nodo Output presente en la escena.
    - Se actualiza automáticamente cuando el grafo se evalúa.
    - Muestra los valores que llegan al/los puertos de entrada del Output.
    """

    def __init__(self, node_view, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Preview de Outputs")
        self.resize(800, 500)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        self._node_view = node_view

        # Tabs por cada nodo Output
        self.tabs = QtWidgets.QTabWidget(self)
        self.setCentralWidget(self.tabs)

        # Mapa: nodo -> editor
        self._editors: Dict[NodeItem, TextEditor] = {}

        # Timer de refresco en vivo (fallback por si alguna señal no llega)
        self._live_timer = QtCore.QTimer(self)
        self._live_timer.setInterval(200)
        self._live_timer.timeout.connect(self.refresh_contents)
        try:
            self._live_timer.start()
        except Exception:
            pass

        # Actualización inicial y conexión a señales
        self.refresh_tabs()
        try:
            self._node_view.graphEvaluated.connect(self.refresh_tabs)
            self._node_view.graphEvaluated.connect(self.refresh_contents)
        except Exception:
            pass

    def _collect_outputs(self) -> list:
        try:
            scene = getattr(self._node_view, "_scene", None)
            items = list(scene.items()) if scene else []
            return [it for it in items if isinstance(it, NodeItem) and str(getattr(it, 'node_type', '')).lower() == 'output']
        except Exception:
            return []

    def refresh_tabs(self) -> None:
        """Sincroniza las pestañas con los nodos Output presentes."""
        outputs = self._collect_outputs()
        existing_nodes = set(self._editors.keys())
        desired_nodes = set(outputs)

        # Eliminar pestañas de nodos que ya no existen
        for removed in existing_nodes - desired_nodes:
            editor = self._editors.pop(removed, None)
            if editor is not None:
                # Buscar y quitar la pestaña correspondiente
                for i in range(self.tabs.count()):
                    if self.tabs.widget(i) is editor:
                        self.tabs.removeTab(i)
                        break

        # Agregar pestañas nuevas
        for node in desired_nodes - existing_nodes:
            editor = TextEditor()
            editor.setReadOnly(True)
            editor.setPlaceholderText("Esperando evaluación del grafo…")
            self._editors[node] = editor
            title = str(getattr(node, 'title', 'Output') or 'Output')
            self.tabs.addTab(editor, title)

        # Actualizar títulos por si cambian
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            node = next((n for n, ed in self._editors.items() if ed is w), None)
            if node is not None:
                self.tabs.setTabText(i, str(getattr(node, 'title', 'Output') or 'Output'))

        # Rellenar contenidos actuales
        self.refresh_contents()

    def closeEvent(self, event) -> None:
        """Detiene el refresco en vivo al cerrar la ventana."""
        try:
            if hasattr(self, '_live_timer') and self._live_timer is not None:
                self._live_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)

    def refresh_contents(self) -> None:
        """Actualiza el texto de TODAS las pestañas de outputs en tiempo real.

        - Ya no requiere selección: siempre refleja los valores actuales
          que llegan a cada nodo Output.
        - Mantiene fallback al contenido del nodo cuando no hay entradas.
        """
        for node, editor in list(self._editors.items()):
            try:
                parts = []
                for p in (getattr(node, 'input_ports', []) or []):
                    name = p.get('name', 'input')
                    val = (getattr(node, 'input_values', {}) or {}).get(name, None)
                    if val is None:
                        continue
                    if isinstance(val, list):
                        for sv in val:
                            if sv is not None:
                                parts.append(str(sv))
                    else:
                        parts.append(str(val))
                text = "\n".join(parts)
                # Fallback: si no hay entradas, usar el contenido actual del nodo
                if not text:
                    try:
                        text = node.to_plain_text()
                    except Exception:
                        text = str(getattr(node, 'content', '') or '')
                # Mostrar placeholder solo si está vacío y no hay nada que mostrar
                if not text:
                    editor.setPlaceholderText("Sin datos de entrada…")
                editor.setPlainText(text)
                # Desplazar al final para ver cambios recientes
                cur = editor.textCursor()
                cur.movePosition(QtGui.QTextCursor.End)
                editor.setTextCursor(cur)
            except Exception:
                pass


__all__ = ["OutputPreviewWindow"]