from __future__ import annotations

from typing import Optional, Dict, Any

from PySide6 import QtCore, QtGui, QtWidgets


def _load_node_view(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    try:
        from ..graph.node_view import NodeView  # type: ignore
        return NodeView(parent=parent)
    except Exception:
        w = QtWidgets.QWidget(parent)
        v = QtWidgets.QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        lbl = QtWidgets.QLabel("NodeView no disponible", w)
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(lbl)
        return w


class BlueprintEditorWindow(QtWidgets.QMainWindow):
    """
    Ventana independiente estilo Blueprint para editar el grafo.
    - Contiene su propio NodeView.
    - Botón Guardar emite el grafo serializado para aplicarlo en el editor principal.
    """

    graphSaved = QtCore.Signal(dict)

    def __init__(self, initial_graph: Optional[Dict[str, Any]] = None, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Blueprint Editor")
        self.resize(900, 600)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

        central = QtWidgets.QWidget(self)
        v = QtWidgets.QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.setCentralWidget(central)

        # Toolbar simple
        tb = QtWidgets.QToolBar("Acciones", self)
        tb.setIconSize(QtCore.QSize(18, 18))
        self.addToolBar(QtCore.Qt.TopToolBarArea, tb)
        act_save = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.SP_DialogSaveButton), "Guardar", self)
        act_close = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCloseButton), "Cerrar", self)
        tb.addAction(act_save)
        tb.addAction(act_close)

        # NodeView local
        self.node_view = _load_node_view(self)
        v.addWidget(self.node_view)

        # Importar grafo inicial si se proporciona
        try:
            if (initial_graph is not None
                and hasattr(self.node_view, 'import_graph')):
                self.node_view.import_graph(initial_graph, clear=True)
            else:
                # Fallback: asegurar grafo demo
                if hasattr(self.node_view, 'ensure_demo_graph'):
                    self.node_view.ensure_demo_graph()
        except Exception:
            pass

        # Conexiones
        act_save.triggered.connect(self._on_save)
        act_close.triggered.connect(self.close)

    def _on_save(self) -> None:
        try:
            if hasattr(self.node_view, 'export_graph'):
                data = self.node_view.export_graph()  # type: ignore[attr-defined]
            else:
                data = {}
            self.graphSaved.emit(data)
            # Feedback visual
            try:
                self.statusBar().showMessage("Cambios guardados", 1500)
            except Exception:
                pass
        except Exception:
            pass


__all__ = ["BlueprintEditorWindow"]