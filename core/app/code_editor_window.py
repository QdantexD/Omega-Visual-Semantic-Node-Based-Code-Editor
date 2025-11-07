from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets
from ..ui.text_editor import TextEditor, PythonHighlighter


class CodeEditorWindow(QtWidgets.QMainWindow):
    """Ventana independiente para un editor de código clásico.

    - Usa TextEditor con números de línea y estilo oscuro.
    - Toolbar con Nuevo, Abrir, Guardar y Guardar como.
    - Muestra mensajes en la barra de estado.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Editor de Código")
        self.resize(820, 560)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

        # Editor central
        self.editor = TextEditor()
        self.editor.setPlaceholderText("Escribe tu código aquí…")
        # Resaltado Python por defecto (no limita otros lenguajes)
        try:
            self._highlighter = PythonHighlighter(self.editor.document())
        except Exception:
            self._highlighter = None
        self.setCentralWidget(self.editor)

        # Estado archivo actual
        self._current_path: Optional[str] = None

        # Toolbar
        tb = QtWidgets.QToolBar("Archivo", self)
        tb.setIconSize(QtCore.QSize(18, 18))
        self.addToolBar(QtCore.Qt.TopToolBarArea, tb)

        act_new = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon), "Nuevo", self)
        act_open = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.SP_DirOpenIcon), "Abrir…", self)
        act_save = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.SP_DialogSaveButton), "Guardar", self)
        act_save_as = QtGui.QAction("Guardar como…", self)
        act_close = QtGui.QAction(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCloseButton), "Cerrar", self)

        tb.addAction(act_new)
        tb.addAction(act_open)
        tb.addAction(act_save)
        tb.addAction(act_save_as)
        tb.addSeparator()
        tb.addAction(act_close)

        # Conexiones
        act_new.triggered.connect(self._new_file)
        act_open.triggered.connect(self._open_file)
        act_save.triggered.connect(self._save_file)
        act_save_as.triggered.connect(self._save_file_as)
        act_close.triggered.connect(self.close)

        # Atajos
        act_save.setShortcut(QtGui.QKeySequence.Save)
        act_open.setShortcut(QtGui.QKeySequence.Open)

        # Barra de estado
        try:
            self.statusBar().setStyleSheet("background:#0f1318;color:#cbd5e1;")
        except Exception:
            pass

    # ---- Acciones de archivo ----
    def _new_file(self) -> None:
        try:
            self.editor.clear()
            self._current_path = None
            self.setWindowTitle("Editor de Código")
            self.statusBar().showMessage("Nuevo archivo", 1200)
        except Exception:
            pass

    def _open_file(self) -> None:
        try:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Abrir archivo", "", "Todos (*.*);;Código (*.py *.txt)")
            if not path:
                return
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                self.editor.setPlainText(f.read())
            self._current_path = path
            self.setWindowTitle(f"Editor de Código — {QtCore.QFileInfo(path).fileName()}")
            self.statusBar().showMessage("Archivo abierto", 1200)
        except Exception:
            try:
                self.statusBar().showMessage("No se pudo abrir el archivo", 1500)
            except Exception:
                pass

    def _save_file(self) -> None:
        try:
            if not self._current_path:
                return self._save_file_as()
            text = self.editor.toPlainText()
            with open(self._current_path, "w", encoding="utf-8", errors="ignore") as f:
                f.write(text)
            self.statusBar().showMessage("Guardado", 1200)
        except Exception:
            try:
                self.statusBar().showMessage("Error al guardar", 1500)
            except Exception:
                pass

    def _save_file_as(self) -> None:
        try:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Guardar como", "", "Todos (*.*);;Código (*.py *.txt)")
            if not path:
                return
            text = self.editor.toPlainText()
            with open(path, "w", encoding="utf-8", errors="ignore") as f:
                f.write(text)
            self._current_path = path
            self.setWindowTitle(f"Editor de Código — {QtCore.QFileInfo(path).fileName()}")
            self.statusBar().showMessage("Guardado", 1200)
        except Exception:
            try:
                self.statusBar().showMessage("Error al guardar", 1500)
            except Exception:
                pass


__all__ = ["CodeEditorWindow"]