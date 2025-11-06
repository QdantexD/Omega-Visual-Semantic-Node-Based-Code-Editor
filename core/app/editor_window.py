from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets
from ..graph.node_item import NodeItem
from .blueprint_editor_window import BlueprintEditorWindow
from .node_content_editor_window import NodeContentEditorWindow
from .output_preview_window import OutputPreviewWindow

# Carga robusta de FileExplorer con rutas absoluta y relativa
def _import_file_explorer():
    try:
        from core.ui.file_explorer import FileExplorer as FE  # type: ignore
        return FE
    except Exception as e_abs:
        try:
            from ..ui.file_explorer import FileExplorer as FE  # type: ignore
            return FE
        except Exception as e_rel:
            print(f"[EditorWindow] Error importando FileExplorer: abs={e_abs} rel={e_rel}")
            return None

FileExplorer = _import_file_explorer()

# Cargar NodeView si existe; de lo contrario usar un placeholder
class _PlaceholderNodeView(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QtWidgets.QLabel(
            "NodeView no disponible. Se usa un panel placeholder.", self
        )
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(lbl)


def _load_node_view(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    try:
        from ..graph.node_view import NodeView  # type: ignore
        w = NodeView(parent=parent)
        return w
    except Exception:
        return _PlaceholderNodeView(parent)


class EditorWindow(QtWidgets.QMainWindow):
    """
    Nueva implementación simplificada y robusta del EditorWindow.

    Objetivos clave:
    - Barra de actividad izquierda con botón de Carpeta.
    - Splitter principal con FileExplorer a la izquierda y el panel de trabajo a la derecha.
    - Asegurar que el Explorer sea visible y refrescado al pulsar el botón Carpeta.
    - Persistir el ancho del sidebar y su estado (colapsado/no colapsado) con QSettings.
    """

    ORGANIZATION = "Codemind-Visual"
    APP_NAME = "Semantic-Node-Editor"

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Editor de Texto y Nodos")
        self.resize(1200, 800)

        # Estado sidebar
        self._sidebar_collapsed: bool = False
        self._sidebar_last_size: int = 90

        # QSettings para persistir UI
        self._settings = QtCore.QSettings(self.ORGANIZATION, self.APP_NAME)

        # UI principal
        central = QtWidgets.QWidget(self)
        root_layout = QtWidgets.QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Barra de actividad global (vertical, izquierda)
        self._activity_bar = self._build_activity_bar()
        root_layout.addWidget(self._activity_bar)

        # Splitter principal: Explorer | Panel de trabajo
        self.outer_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        self.outer_splitter.setChildrenCollapsible(False)
        root_layout.addWidget(self.outer_splitter, 1)

        # Explorer a la izquierda
        self.file_explorer = self._build_file_explorer()
        # Presentación compacta al estilo VS Code (sin rail interno)
        try:
            if hasattr(self.file_explorer, "set_compact_mode"):
                self.file_explorer.set_compact_mode(True)
        except Exception:
            pass
        self.outer_splitter.addWidget(self.file_explorer)

        # Panel de trabajo a la derecha (tabs simples: Editor y NodeView)
        self.work_tabs = QtWidgets.QTabWidget(self)
        self.work_tabs.setDocumentMode(True)
        self.work_tabs.setTabPosition(QtWidgets.QTabWidget.North)
        self.outer_splitter.addWidget(self.work_tabs)

        # Editor de texto básico
        self.text_editor = QtWidgets.QPlainTextEdit(self)
        self.text_editor.setPlaceholderText("Editor de texto")
        self.work_tabs.addTab(self.text_editor, "Editor")

        # NodeView o placeholder dentro de un contenedor con barra inferior propia
        self.node_view = _load_node_view(self)
        self.node_tab = QtWidgets.QWidget(self)
        node_tab_layout = QtWidgets.QVBoxLayout(self.node_tab)
        node_tab_layout.setContentsMargins(0, 0, 0, 0)
        node_tab_layout.setSpacing(0)
        node_tab_layout.addWidget(self.node_view, 1)
        # Construir barra inferior específica del editor de nodos
        self._node_bar_container = self._build_node_bottom_bar()
        node_tab_layout.addWidget(self._node_bar_container, 0)
        self.work_tabs.addTab(self.node_tab, "Nodos")

        # Enfocar el panel de nodos al activar la pestaña para que TAB funcione
        try:
            self.work_tabs.currentChanged.connect(self._on_tab_changed)
        except Exception:
            pass

        # Central widget
        self.setCentralWidget(central)
        try:
            central.setStyleSheet("background: #0f1318;")
        except Exception:
            pass

        # Status bar (global) minimal, sin controles de Nodos
        self._setup_status_bar()
        # Conectar la barra inferior del editor de nodos después de crear NodeView
        QtCore.QTimer.singleShot(0, self._wire_node_bottom_bar)

        # Restaurar estado del sidebar
        self._restore_sidebar_state()

        # Asegurar que el Explorer esté listo al inicio
        QtCore.QTimer.singleShot(0, self._ensure_explorer_ready)

        # Estilos de la barra de actividad y splitter (VS Code-like)
        try:
            self._activity_bar.setStyleSheet(
                """
                QFrame#globalActivityBar { background: #141923; border-right: 1px solid #2a2f39; }
                QToolButton { color: #cbd5e1; padding: 10px 6px; }
                QToolButton:hover { background: #273041; border-radius: 6px; }
                QToolButton:checked { background: #324054; border-radius: 6px; }
                """
            )
            self.outer_splitter.setStyleSheet(
                """
                QSplitter::handle { background: #11151b; width: 3px; }
                QSplitter::handle:hover { background: #1f2430; }
                """
            )
            self.work_tabs.setStyleSheet(
                """
                QTabBar::tab { background: #131820; color: #cbd5e1; padding: 6px 12px; margin-right: 2px; }
                QTabBar::tab:selected { background: #1b2230; }
                QTabBar::tab:hover { background: #1a202a; }
                QTabWidget::pane { border-top: 1px solid #202a36; }
                """
            )
            # Status bar coherente
            self.statusBar().setStyleSheet("background:#0f1318;color:#cbd5e1;")
        except Exception:
            pass

    # -----------------------------
    # Construcción de subcomponentes
    # -----------------------------
    def _build_activity_bar(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame(self)
        bar.setObjectName("globalActivityBar")
        bar.setFixedWidth(48)
        bar.setFrameShape(QtWidgets.QFrame.NoFrame)

        layout = QtWidgets.QVBoxLayout(bar)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(6)

        # Botón carpeta
        self._btn_files = QtWidgets.QToolButton(bar)
        self._btn_files.setCheckable(True)
        self._btn_files.setToolTip("Explorador de carpetas")
        self._btn_files.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
        self._btn_files.setIconSize(QtCore.QSize(24, 24))
        # Usamos toggled para comportamiento de mostrar/ocultar con animación
        self._btn_files.toggled.connect(self._on_files_toggled)

        # Menú contextual del botón
        menu = QtWidgets.QMenu(self._btn_files)
        act_open = menu.addAction("Abrir carpeta...")
        act_open.triggered.connect(self._action_open_folder)
        self._btn_files.setMenu(menu)
        self._btn_files.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)

        layout.addWidget(self._btn_files)
        layout.addStretch(1)
        return bar

    def _build_file_explorer(self) -> QtWidgets.QWidget:
        if FileExplorer is None:
            # Fallback si no se pudo importar: mensaje amigable y botón para reintentar
            container = QtWidgets.QWidget(self)
            v = QtWidgets.QVBoxLayout(container)
            v.setContentsMargins(8, 8, 8, 8)
            v.setSpacing(8)
            lbl = QtWidgets.QLabel("FileExplorer no disponible")
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            lbl.setStyleSheet("color:#cbd5e1;font-size:13px;")
            v.addStretch(1)
            v.addWidget(lbl)
            btn = QtWidgets.QPushButton("Reintentar carga")
            btn.clicked.connect(self._retry_load_explorer)
            btn.setFixedWidth(160)
            btn.setStyleSheet("padding:6px 10px;border-radius:6px;")
            h = QtWidgets.QHBoxLayout()
            h.addStretch(1)
            h.addWidget(btn)
            h.addStretch(1)
            v.addLayout(h)
            v.addStretch(1)
            return container

        try:
            explorer = FileExplorer()
            return explorer
        except Exception as e:
            print(f"[EditorWindow] Error instanciando FileExplorer: {e}")
            container = QtWidgets.QWidget(self)
            v = QtWidgets.QVBoxLayout(container)
            v.setContentsMargins(8, 8, 8, 8)
            v.addStretch(1)
            msg = QtWidgets.QLabel("No se pudo crear el FileExplorer")
            msg.setAlignment(QtCore.Qt.AlignCenter)
            v.addWidget(msg)
            v.addStretch(1)
            return container

    def _retry_load_explorer(self) -> None:
        # Reintentar import e inserción en el splitter
        global FileExplorer
        FileExplorer = _import_file_explorer()
        idx = self.outer_splitter.indexOf(self.file_explorer)
        if idx != -1:
            # Reemplazar el widget en el splitter
            self.outer_splitter.widget(idx).deleteLater()
            self.file_explorer = self._build_file_explorer()
            self.outer_splitter.insertWidget(idx, self.file_explorer)
        self._ensure_explorer_ready()

    def _setup_status_bar(self) -> None:
        sb = self.statusBar()
        try:
            sb.setStyleSheet("background:#0f1318;color:#cbd5e1;")
            sb.showMessage("Listo")
        except Exception:
            pass

    def _build_node_bottom_bar(self) -> QtWidgets.QWidget:
        """Construye la barra inferior específica del editor de nodos."""
        container = QtWidgets.QFrame(self)
        container.setFrameShape(QtWidgets.QFrame.StyledPanel)
        container.setStyleSheet("background:#0f1318;border-top:1px solid #202a36;")

        lay = QtWidgets.QHBoxLayout(container)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(10)

        # Estado: selección y zoom
        self._lbl_sel = QtWidgets.QLabel("Sel: 0", container)
        self._lbl_zoom = QtWidgets.QLabel("Zoom: 100%", container)
        for lbl in (self._lbl_sel, self._lbl_zoom):
            lbl.setStyleSheet("color:#cbd5e1;")
        lay.addWidget(self._lbl_sel)
        lay.addWidget(self._lbl_zoom)

        lay.addStretch(1)

        # Botones de acciones
        def _mk_btn(text: str) -> QtWidgets.QPushButton:
            b = QtWidgets.QPushButton(text, container)
            b.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            b.setMinimumHeight(26)
            b.setStyleSheet(
                """
                QPushButton { background:#1b2230; color:#cbd5e1; border:1px solid #202a36; padding:4px 12px; border-radius:6px; }
                QPushButton:hover { background:#232a3a; }
                QPushButton:pressed { background:#192133; }
                """
            )
            return b

        self._btn_add = _mk_btn("Añadir…")
        self._btn_frame = _mk_btn("Frame")
        self._btn_eval = _mk_btn("Evaluar")
        self._btn_zoom_out = _mk_btn("Zoom −")
        self._btn_zoom_in = _mk_btn("Zoom +")
        self._btn_zoom_reset = _mk_btn("Reset")
        self._btn_layout = _mk_btn("Auto layout")
        self._btn_delete = _mk_btn("Eliminar selección")
        self._btn_blueprint = _mk_btn("Editar en ventana…")
        self._btn_output_preview = _mk_btn("Preview Outputs…")

        lay.addWidget(self._btn_add)
        lay.addWidget(self._btn_frame)
        lay.addWidget(self._btn_eval)
        lay.addSpacing(6)
        lay.addWidget(self._btn_zoom_out)
        lay.addWidget(self._btn_zoom_in)
        lay.addWidget(self._btn_zoom_reset)
        lay.addSpacing(6)
        lay.addWidget(self._btn_layout)
        lay.addWidget(self._btn_delete)
        lay.addWidget(self._btn_blueprint)
        lay.addWidget(self._btn_output_preview)

        return container

    # -----------------------------
    # Acciones de UI
    # -----------------------------
    def _on_files_toggled(self, checked: bool) -> None:
        # Mostrar/ocultar con animación al estilo VS Code
        self._animate_sidebar(expand=checked)
        if checked:
            self._ensure_explorer_ready()

    def _action_open_folder(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Seleccionar carpeta")
        if not path:
            return
        self._set_explorer_root(path)
        self._apply_sidebar(expand=True)
        self._ensure_explorer_ready()

    # -----------------------------
    # Lógica Explorer / Sidebar
    # -----------------------------
    def _ensure_explorer_ready(self) -> None:
        """Garantiza que el Explorer esté visible, con árbol expandido y foco."""
        if not hasattr(self, "file_explorer") or self.file_explorer is None:
            return

        # Forzar visibilidad del contenedor izquierdo (sin animación al inicio)
        self._apply_sidebar(expand=True)

        # Activar sección Folder si existe
        try:
            if hasattr(self.file_explorer, "folder_toggle_btn"):
                self.file_explorer.folder_toggle_btn.setChecked(True)
            if hasattr(self.file_explorer, "set_compact_mode"):
                self.file_explorer.set_compact_mode(True)
        except Exception:
            pass

        # Asegurar raíz válida
        has_root = False
        try:
            # FileExplorer expone root_path
            root_path = getattr(self.file_explorer, "root_path", None)
            has_root = bool(root_path)
        except Exception:
            has_root = False

        if not has_root:
            # Intentar restaurar última carpeta usada
            last_path = self._settings.value("explorer/last_root", "", type=str) or ""
            if last_path:
                self._set_explorer_root(last_path)
            else:
                self._set_explorer_root(QtCore.QDir.homePath())

        # Asegurar foco al árbol si existe
        try:
            tree = getattr(self.file_explorer, "tree", None)
            if tree is not None:
                tree.setVisible(True)
                tree.setFocus()
        except Exception:
            pass

    def _animate_sidebar(self, expand: bool) -> None:
        """Anima el ancho del panel izquierdo para mostrar/ocultar el Explorer."""
        try:
            sizes = self.outer_splitter.sizes()
            total = sum(sizes) if sizes else max(self.width(), 1)
            current_left = sizes[0] if sizes else 0
            target_left = (
                max(90, min(self._sidebar_last_size, total - 100)) if expand else 0
            )

            class _SplitterSizeProxy(QtCore.QObject):
                def __init__(self, splitter: QtWidgets.QSplitter):
                    super().__init__(splitter)
                    self._splitter = splitter
                    self._width = current_left

                def getWidth(self) -> int:
                    return int(self._width)

                def setWidth(self, w: int) -> None:
                    self._width = int(max(0, w))
                    try:
                        sizes = self._splitter.sizes()
                        total = sum(sizes) if sizes else 0
                        left = self._width
                        right = max(100, total - left) if total > 0 else 500
                        self._splitter.setSizes([left, right])
                    except Exception:
                        pass

                width = QtCore.Property(int, getWidth, setWidth)

            proxy = _SplitterSizeProxy(self.outer_splitter)
            anim = QtCore.QPropertyAnimation(proxy, b"width", self)
            anim.setDuration(220)
            anim.setStartValue(current_left)
            anim.setEndValue(target_left)
            anim.setEasingCurve(QtCore.QEasingCurve.InOutCubic)

            # Animación de opacidad del Explorer para un efecto más suave
            try:
                if hasattr(self.file_explorer, "animate_visibility"):
                    self.file_explorer.animate_visibility(expand)
            except Exception:
                pass

            def _finish():
                # Persistir estado y tamaños finales
                self._sidebar_collapsed = not expand
                final_sizes = self.outer_splitter.sizes()
                if final_sizes and final_sizes[0] > 0:
                    self._sidebar_last_size = final_sizes[0]
                self._save_sidebar_state()

            anim.finished.connect(_finish)
            anim.start()
        except Exception:
            # Fallback sin animación
            self._apply_sidebar(expand=expand)

    def _apply_sidebar(self, expand: bool) -> None:
        """Expande/colapsa el panel izquierdo (Explorer) y persiste su tamaño."""
        self._sidebar_collapsed = not expand
        sizes = self.outer_splitter.sizes()
        total = sum(sizes) if sizes else max(self.width(), 1)

        if expand:
            # Usar último ancho conocido, permitiendo panel mucho más estrecho
            left = max(90, min(self._sidebar_last_size, total - 220))
            right = max(200, total - left)
            self.outer_splitter.setSizes([left, right])
        else:
            # Colapsar completamente el panel izquierdo
            self._sidebar_last_size = sizes[0] if sizes else self._sidebar_last_size
            self.outer_splitter.setSizes([0, total])

        self._save_sidebar_state()

    def _set_explorer_root(self, path: str) -> None:
        try:
            if hasattr(self.file_explorer, "set_root"):
                self.file_explorer.set_root(path)
                self._settings.setValue("explorer/last_root", path)
        except Exception:
            pass

    # -----------------------------
    # Persistencia de UI
    # -----------------------------
    def _restore_sidebar_state(self) -> None:
        collapsed = self._settings.value("sidebar/collapsed", False, type=bool)
        last_size = self._settings.value("sidebar/last_size", 140, type=int)
        self._sidebar_collapsed = collapsed
        self._sidebar_last_size = max(90, int(last_size))

        # Ajustar tamaños iniciales
        if self._sidebar_collapsed:
            self.outer_splitter.setSizes([0, self.width()])
            self._btn_files.setChecked(False)
        else:
            left = self._sidebar_last_size
            total = max(self.width(), 1)
            right = max(200, total - left)
            self.outer_splitter.setSizes([left, right])
            self._btn_files.setChecked(True)

    def _save_sidebar_state(self) -> None:
        sizes = self.outer_splitter.sizes()
        if sizes and sizes[0] > 0:
            self._sidebar_last_size = sizes[0]
        self._settings.setValue("sidebar/collapsed", self._sidebar_collapsed)
        self._settings.setValue("sidebar/last_size", self._sidebar_last_size)

    # -----------------------------
    # Eventos de ventana
    # -----------------------------
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self._save_sidebar_state()
        super().closeEvent(event)

    # -----------------------------
    # API esperada por main.py / controlador de nodos
    # -----------------------------

    def _on_tab_changed(self, index: int) -> None:
        """Enfoca el NodeView cuando se activa la pestaña 'Nodos'."""
        try:
            widget = self.work_tabs.widget(index)
            if widget is self.node_tab:
                # Dar foco para que keyPressEvent (TAB) sea capturado
                self.node_view.setFocus()
                # Asegurar que el grafo demo aparezca si la escena está vacía
                try:
                    if hasattr(self.node_view, 'ensure_demo_graph'):
                        self.node_view.ensure_demo_graph()
                except Exception:
                    pass
                # Actualizar estado visible
                self._refresh_node_status_widgets()
        except Exception:
            pass

    def _wire_node_bottom_bar(self) -> None:
        """Conecta señales del NodeView con la barra inferior del editor de nodos."""
        try:
            if not hasattr(self, 'node_view') or self.node_view is None:
                return
            # Actualizar etiquetas en tiempo real
            try:
                self.node_view.zoomChanged.connect(self._on_zoom_changed)
                self.node_view.selectionCountChanged.connect(self._on_selection_count)
                self.node_view.graphEvaluated.connect(self._on_graph_evaluated)
                # Abrir editor de nodo en ventana independiente al hacer doble clic
                if hasattr(self.node_view, 'editNodeRequested'):
                    self.node_view.editNodeRequested.connect(self._on_edit_node_requested)
            except Exception:
                pass
            # Acciones rápidas
            self._btn_add.clicked.connect(self.node_view.open_tab_menu)
            self._btn_frame.clicked.connect(self.node_view.center_on_selected)
            self._btn_eval.clicked.connect(self.node_view.evaluate_graph)
            self._btn_zoom_out.clicked.connect(self.node_view.zoom_out)
            self._btn_zoom_in.clicked.connect(self.node_view.zoom_in)
            self._btn_zoom_reset.clicked.connect(self.node_view.reset_zoom)
            self._btn_layout.clicked.connect(self.node_view.auto_layout_selection)
            self._btn_delete.clicked.connect(self.node_view.delete_selected_nodes)
            self._btn_blueprint.clicked.connect(self._open_blueprint_window)
            self._btn_output_preview.clicked.connect(self._open_output_preview)
            # Primer refresco
            self._refresh_node_status_widgets()
        except Exception:
            pass

    def _on_zoom_changed(self, scale: float) -> None:
        try:
            pct = int(round(scale * 100))
        except Exception:
            pct = 100
        self._lbl_zoom.setText(f"Zoom: {pct}%")

    def _on_selection_count(self, count: int) -> None:
        self._lbl_sel.setText(f"Sel: {int(count)}")

    def _on_graph_evaluated(self) -> None:
        try:
            self.statusBar().showMessage("Grafo evaluado", 1500)
        except Exception:
            pass

    def _refresh_node_status_widgets(self) -> None:
        """Refresca etiquetas de estado con valores actuales de NodeView."""
        try:
            # Simular señales para estado inicial
            selected = len(self.node_view._scene.selectedItems()) if hasattr(self.node_view, '_scene') else 0
            self._on_selection_count(selected)
            scale = float(self.node_view.transform().m11()) if hasattr(self.node_view, 'transform') else 1.0
            self._on_zoom_changed(scale)
        except Exception:
            pass
    def set_node_controller(self, controller: object) -> None:
        """Permite inyectar el controlador de nodos desde main.py."""
        self._node_controller = controller
        # Si el NodeView soporta set_controller, propagarlo
        try:
            if hasattr(self.node_view, "set_controller"):
                self.node_view.set_controller(controller)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _open_blueprint_window(self) -> None:
        """Abre la ventana independiente tipo Blueprint para editar el grafo actual."""
        try:
            initial = {}
            if hasattr(self.node_view, 'export_graph'):
                initial = self.node_view.export_graph()  # type: ignore[attr-defined]
            bp = BlueprintEditorWindow(initial_graph=initial, parent=self)
            # Cuando el usuario guarda en la ventana Blueprint, importar cambios
            bp.graphSaved.connect(lambda data: self._apply_blueprint_changes(data))
            bp.show()
        except Exception:
            pass

    def _apply_blueprint_changes(self, data: dict) -> None:
        try:
            if hasattr(self.node_view, 'import_graph'):
                self.node_view.import_graph(data, clear=True)  # type: ignore[attr-defined]
                # Feedback global
                try:
                    self.statusBar().showMessage("Grafo actualizado desde Blueprint", 1500)
                except Exception:
                    pass
        except Exception:
            pass

    # -----------------------------
    # Editor de Nodo (ventana)
    # -----------------------------
    def _on_edit_node_requested(self, node) -> None:
        try:
            win = NodeContentEditorWindow(self.node_view, parent=self)
            win.set_node(node)
            win.show()
        except Exception:
            pass

    # -----------------------------
    # Preview de Outputs (ventana)
    # -----------------------------
    def _open_output_preview(self) -> None:
        try:
            # Mantener referencia para evitar GC y reutilizar ventana
            if not hasattr(self, '_output_preview_win') or self._output_preview_win is None:
                self._output_preview_win = OutputPreviewWindow(self.node_view, parent=self)
            win = self._output_preview_win
            # Si hay un único nodo seleccionado, crear un Monitor Output autoconectado
            try:
                scene = getattr(self.node_view, '_scene', None)
                selected_nodes = [it for it in (scene.selectedItems() if scene else []) if isinstance(it, NodeItem)]
                if len(selected_nodes) == 1:
                    src = selected_nodes[0]
                    # Posicionar el monitor a la derecha del nodo seleccionado
                    pos = src.scenePos()
                    mon_x = float(pos.x() + 140.0)
                    mon_y = float(pos.y())
                    mon = self.node_view.add_node_with_ports(
                        title="Monitor",
                        x=mon_x,
                        y=mon_y,
                        node_type="output",
                        inputs=[{"name": "input", "kind": "data", "multi": True}],
                        outputs=["output"],
                        content=""
                    )
                    if mon is not None:
                        try:
                            setattr(mon, 'forward_output', True)
                        except Exception:
                            pass
                        # Autoconectar primer OUT del seleccionado al IN del monitor
                        try:
                            start_port = (src.output_ports[0]['name'] if getattr(src, 'output_ports', None) else 'output')
                            end_port = (mon.input_ports[0]['name'] if getattr(mon, 'input_ports', None) else 'input')
                            self.node_view.add_connection(src, mon, start_port=start_port, end_port=end_port)
                        except Exception:
                            pass
                        # Intentar seleccionar y centrar
                        try:
                            mon.setSelected(True)
                            self.node_view.centerOn(mon)
                        except Exception:
                            pass
                        # Enfocar pestaña del monitor en el Preview si existe
                        try:
                            win.refresh_tabs()
                            # Buscar editor asociado al monitor
                            ed = getattr(win, '_editors', {}).get(mon)
                            if ed is not None:
                                for i in range(win.tabs.count()):
                                    if win.tabs.widget(i) is ed:
                                        win.tabs.setCurrentIndex(i)
                                        break
                        except Exception:
                            pass
            except Exception:
                pass
            # Forzar evaluación del grafo para que el Preview tenga datos al abrir
            try:
                self.node_view.evaluate_graph()
            except Exception:
                pass
            # Refrescar contenidos por si hay buffers iniciales
            try:
                win.refresh_tabs()
                win.refresh_contents()
            except Exception:
                pass
            win.show()
            win.raise_()
            win.activateWindow()
        except Exception:
            pass


__all__ = ["EditorWindow"]