from PySide6.QtWidgets import (
    QWidget, QTreeView, QVBoxLayout, QFileSystemModel, QMenu, QLineEdit, QLabel,
    QHBoxLayout, QToolButton, QFrame, QComboBox, QPushButton, QCheckBox
)
from PySide6.QtCore import QDir, Signal, Qt, QSize, QPropertyAnimation, QEasingCurve, QSortFilterProxyModel
from PySide6.QtGui import QIcon, QGraphicsOpacityEffect
import os

class SimpleSortFilterProxy(QSortFilterProxyModel):
    """
    Proxy para ordenar/filtrar con opción de carpetas primero.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.folders_first = True

    def set_folders_first(self, enable: bool):
        self.folders_first = bool(enable)
        # Reordenar inmediatamente
        self.invalidate()

    def lessThan(self, left, right):
        try:
            src = self.sourceModel()
            if src and self.folders_first:
                left_is_dir = False
                right_is_dir = False
                try:
                    left_is_dir = src.isDir(left)
                except Exception:
                    pass
                try:
                    right_is_dir = src.isDir(right)
                except Exception:
                    pass
                if left_is_dir != right_is_dir:
                    # Carpetas antes que archivos
                    return left_is_dir and not right_is_dir
        except Exception:
            pass
        # Fallback al comportamiento por defecto
        return super().lessThan(left, right)

class FileExplorer(QWidget):
    """
    Explorador de archivos avanzado, estilo Visual Studio Code.
    Soporta:
    - Filtros dinámicos por extensión o nombre
    - Iconos por tipo de archivo
    - Menú contextual para abrir, renombrar y eliminar
    - Señal para abrir archivos en un editor externo o pestañas internas
    """
    file_opened = Signal(str)
    compact_requested = Signal(bool)

    def __init__(self, root_path=None):
        super().__init__()

        self.root_path = root_path or QDir.currentPath()
        self._rail_width = 48
        self._expanded_width = 240
        self._compact = False

        # Layout principal: barra de íconos (izquierda) + contenido (derecha)
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setLayout(root_layout)

        # Barra de íconos interna (se puede ocultar si se usa una externa)
        self.rail = QFrame()
        self.rail.setFixedWidth(self._rail_width)
        self.rail.setObjectName("ExplorerRail")
        rail_layout = QVBoxLayout(self.rail)
        rail_layout.setContentsMargins(6, 8, 6, 8)
        rail_layout.setSpacing(10)

        def mk_btn(icon_name: str, tooltip: str) -> QToolButton:
            btn = QToolButton()
            icon = QIcon.fromTheme(icon_name)
            if not icon.isNull():
                btn.setIcon(icon)
            btn.setToolTip(tooltip)
            btn.setIconSize(QSize(20, 20))
            btn.setAutoRaise(True)
            btn.setCheckable(False)
            btn.setCursor(Qt.PointingHandCursor)
            return btn

        self.btn_files = mk_btn("folder", "Archivos")
        self.btn_search = mk_btn("system-search", "Buscar")
        self.btn_graph = mk_btn("preferences-system", "Grafo")
        self.btn_eye = mk_btn("view-visible", "Vista")
        self.btn_bug = mk_btn("bug", "Depurar")
        self.btn_wallet = mk_btn("wallet", "Finanzas")
        self.btn_grid = mk_btn("view-grid", "Cuadrícula")
        self.btn_lab = mk_btn("applications-science", "Laboratorio")
        self.btn_server = mk_btn("server", "Servidor")
        self.btn_db = mk_btn("database", "Datos")

        for btn in (self.btn_files, self.btn_search, self.btn_graph, self.btn_eye, self.btn_bug,
                    self.btn_wallet, self.btn_grid, self.btn_lab, self.btn_server, self.btn_db):
            rail_layout.addWidget(btn)
        rail_layout.addStretch(1)

        # Nota: el botón de carpeta no alterna el modo compacto;
        # el colapso/expansión se gestiona desde la barra de herramientas.

        root_layout.addWidget(self.rail)

        # Contenido del explorador
        self.content = QFrame()
        self.content.setObjectName("ExplorerContent")
        self.layout = QVBoxLayout(self.content)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(6)
        root_layout.addWidget(self.content)
        # Efecto de opacidad para animación de aparición/desaparición
        try:
            self._opacity_effect = QGraphicsOpacityEffect(self.content)
            self._opacity_effect.setOpacity(1.0)
            self.content.setGraphicsEffect(self._opacity_effect)
        except Exception:
            self._opacity_effect = None

        # Título "Explorer" como en VS Code
        self.title_label = QLabel("Explorer")
        self.layout.addWidget(self.title_label)

        # Sección cabecera "Folder" con colapsable y menú
        section_header = QFrame()
        section_header_layout = QHBoxLayout(section_header)
        section_header_layout.setContentsMargins(0, 0, 0, 0)
        section_header_layout.setSpacing(6)

        self.folder_toggle_btn = QToolButton()
        self.folder_toggle_btn.setCheckable(True)
        self.folder_toggle_btn.setChecked(True)  # visible por defecto
        # Fallback de iconos para expandir/colapsar
        try:
            icon_down = QIcon.fromTheme("pan-down-symbolic")
            icon_right = QIcon.fromTheme("pan-end-symbolic")
            if icon_down.isNull() or icon_right.isNull():
                raise RuntimeError("no icons")
            self.folder_toggle_btn.setIcon(icon_down)
        except Exception:
            # Usar texto unicode como fallback
            self.folder_toggle_btn.setText("▾")
        self.folder_toggle_btn.setToolTip("Mostrar/Ocultar carpeta")
        self.folder_toggle_btn.setAutoRaise(True)
        self.folder_toggle_btn.setIconSize(QSize(16, 16))

        folder_label = QLabel("Folder")
        section_header_layout.addWidget(self.folder_toggle_btn)
        section_header_layout.addWidget(folder_label)
        section_header_layout.addStretch(1)

        # Botón de menú "…" para acciones de carpeta
        self.folder_menu_btn = QToolButton()
        try:
            more_icon = QIcon.fromTheme("open-menu-symbolic")
            if more_icon.isNull():
                raise RuntimeError("no more icon")
            self.folder_menu_btn.setIcon(more_icon)
        except Exception:
            self.folder_menu_btn.setText("…")
        self.folder_menu_btn.setToolTip("Opciones de carpeta")
        self.folder_menu_btn.setAutoRaise(True)
        self.folder_menu_btn.setIconSize(QSize(16, 16))
        section_header_layout.addWidget(self.folder_menu_btn)

        self.layout.addWidget(section_header)

        # Campo de búsqueda rápida
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Buscar archivos...")
        self.search_bar.textChanged.connect(self.filter_files)
        self.layout.addWidget(self.search_bar)

        # Etiqueta de ruta actual
        self.path_label = QLabel(f"Explorando: {self.root_path}")
        self.layout.addWidget(self.path_label)

        # Controles de orden/optimización
        controls = QFrame()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems([
            "Nombre (A→Z)",
            "Nombre (Z→A)",
            "Fecha modificada (reciente)",
            "Fecha modificada (antigua)",
            "Tamaño (grande→pequeño)",
            "Tamaño (pequeño→grande)",
            "Tipo (A→Z)",
        ])
        self.cb_folders_first = QCheckBox("Carpetas primero")
        self.cb_folders_first.setChecked(True)
        self.cb_show_hidden = QCheckBox("Mostrar ocultos")
        self.refresh_btn = QPushButton("Actualizar")
        for w in (self.sort_combo, self.cb_folders_first, self.cb_show_hidden, self.refresh_btn):
            controls_layout.addWidget(w)
        controls_layout.addStretch(1)
        self.layout.addWidget(controls)

        # Modelo del sistema de archivos (asíncrono) + proxy
        self.model = QFileSystemModel()
        # Mostrar todas las entradas excepto . y ..
        try:
            self.model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
        except Exception:
            pass
        root_index = self.model.setRootPath(self.root_path)
        try:
            self.model.setNameFilters([])
            self.model.setNameFilterDisables(True)
        except Exception:
            pass
        # Proxy para filtrar/ordenar y forzar carpetas primero
        self.proxy = SimpleSortFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setDynamicSortFilter(True)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(0)

        # Vista de árbol
        self.tree = QTreeView()
        self.tree.setModel(self.proxy)
        # Establecer el índice raíz mapeando el índice del modelo al proxy
        try:
            self.tree.setRootIndex(self.proxy.mapFromSource(root_index))
        except Exception:
            self.tree.setRootIndex(self.proxy.mapFromSource(self.model.index(self.root_path)))
        self.tree.setHeaderHidden(True)
        self.tree.doubleClicked.connect(self.on_file_open)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.open_context_menu)
        # Permitir arrastrar archivos hacia NodeView u otras vistas
        try:
            self.tree.setDragEnabled(True)
            self.tree.setDragDropMode(QTreeView.DragOnly)
            self.tree.setUniformRowHeights(True)
            # Sorting UI y presentación de columnas
            self.tree.setSortingEnabled(True)
            try:
                # Mostrar columnas útiles y ajustar anchos
                self.tree.setHeaderHidden(False)
                self.tree.sortByColumn(0, Qt.AscendingOrder)
                self.tree.setColumnWidth(0, 180)  # Nombre
                self.tree.setColumnWidth(1, 80)   # Tamaño
                self.tree.setColumnWidth(2, 90)   # Tipo
                self.tree.setColumnWidth(3, 120)  # Fecha
            except Exception:
                pass
        except Exception:
            pass

        self.layout.addWidget(self.tree)

        # Iconos por tipo de archivo
        self.icons = {
            ".py": QIcon.fromTheme("application-python"),
            ".txt": QIcon.fromTheme("text-plain"),
            ".json": QIcon.fromTheme("application-json"),
            "folder": QIcon.fromTheme("folder"),
        }

        # Estilos elegantes
        self.setStyleSheet(
            """
            QWidget#ExplorerRail { background: #1b1f27; border-right: 1px solid #2a2f39; }
            QWidget#ExplorerContent { background: #14171d; }
            QLabel { font-size: 12px; }
            QLabel#ExplorerTitle { font-weight: 600; }
            QToolButton { color: #cbd5e1; padding: 6px; }
            QToolButton:hover { background: #222733; border-radius: 6px; }
            QLineEdit { background: #0f1318; color: #d1d5db; border: 1px solid #2a2f39; padding: 6px; border-radius: 6px; }
            QLabel { color: #94a3b8; }
            QTreeView { background: #0e1217; color: #e2e8f0; border: 1px solid #1f2430; }
            QTreeView::item:selected { background: #1e293b; }
            QTreeView::item:hover { background: #182131; }
            """
        )

        # Ancho inicial
        try:
            self.setMaximumWidth(self._expanded_width)
        except Exception:
            pass

        # Conectar colapso de la sección Folder
        try:
            def _on_section_toggled(checked: bool):
                # checked True => visible; False => colapsado
                self.tree.setVisible(bool(checked))
                # Actualizar ícono
                try:
                    if checked:
                        if not QIcon.fromTheme("pan-down-symbolic").isNull():
                            self.folder_toggle_btn.setIcon(QIcon.fromTheme("pan-down-symbolic"))
                        else:
                            self.folder_toggle_btn.setText("▾")
                    else:
                        if not QIcon.fromTheme("pan-end-symbolic").isNull():
                            self.folder_toggle_btn.setIcon(QIcon.fromTheme("pan-end-symbolic"))
                        else:
                            self.folder_toggle_btn.setText("▸")
                except Exception:
                    pass
            self.folder_toggle_btn.toggled.connect(_on_section_toggled)
        except Exception:
            pass

        # Menú del botón "…"
        try:
            def _open_folder_menu():
                menu = QMenu()
                act_open = menu.addAction("Abrir carpeta…")
                act_current = menu.addAction("Proyecto actual")
                act_docs = menu.addAction("Documentos")
                act_desktop = menu.addAction("Escritorio")
                chosen = menu.exec(self.folder_menu_btn.mapToGlobal(self.folder_menu_btn.rect().bottomLeft()))
                if chosen == act_open:
                    from PySide6.QtWidgets import QFileDialog
                    path = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta", self.root_path)
                    if path:
                        self.set_root(path)
                        # asegurar visible
                        self.folder_toggle_btn.setChecked(True)
                elif chosen == act_current:
                    self.set_root(QDir.currentPath())
                    self.folder_toggle_btn.setChecked(True)
                elif chosen == act_docs:
                    home = QDir.homePath()
                    path = os.path.join(home, "Documents")
                    self.set_root(path)
                    self.folder_toggle_btn.setChecked(True)
                elif chosen == act_desktop:
                    home = QDir.homePath()
                    path = os.path.join(home, "Desktop")
                    self.set_root(path)
                    self.folder_toggle_btn.setChecked(True)
            self.folder_menu_btn.clicked.connect(_open_folder_menu)
        except Exception:
            pass

    # --- Modo compacto con animación ---
    def set_compact(self, compact: bool):
        self._compact = bool(compact)
        if self._compact:
            # Animar opacidad a 0 y luego ocultar
            self._animate_content_opacity(0.0, on_finished=lambda: self.content.setVisible(False))
            target = self._rail_width
        else:
            # Mostrar y animar opacidad a 1
            self.content.setVisible(True)
            self._animate_content_opacity(1.0)
            target = self._expanded_width
        self._animate_width(target)

    def _on_folder_clicked(self):
        # Reservado para futuras acciones (abrir panel de archivos, etc.)
        pass

    def _animate_width(self, target_width: int):
        try:
            anim = QPropertyAnimation(self, b"maximumWidth")
            anim.setDuration(220)
            anim.setStartValue(self.maximumWidth())
            anim.setEndValue(int(target_width))
            anim.setEasingCurve(QEasingCurve.InOutCubic)
            anim.start()
            # Guardar referencia para evitar GC prematuro
            self._width_anim = anim
        except Exception:
            try:
                self.setMaximumWidth(int(target_width))
            except Exception:
                pass

    def _animate_content_opacity(self, target: float, on_finished=None):
        try:
            if not self._opacity_effect:
                if on_finished:
                    on_finished()
                return
            anim = QPropertyAnimation(self._opacity_effect, b"opacity")
            anim.setDuration(180)
            anim.setStartValue(self._opacity_effect.opacity())
            anim.setEndValue(float(target))
            anim.setEasingCurve(QEasingCurve.InOutCubic)
            if on_finished:
                anim.finished.connect(lambda: on_finished())
            anim.start()
            self._opacity_anim = anim
        except Exception:
            try:
                self._opacity_effect.setOpacity(float(target))
                if on_finished:
                    on_finished()
            except Exception:
                pass

    # Permite ocultar la barra interna cuando se usa una externa en la ventana principal
    def set_external_rail(self, use_external: bool):
        try:
            self.rail.setVisible(not bool(use_external))
        except Exception:
            pass

    def filter_files(self, text):
        """
        Filtrado eficiente vía proxy: coincidencia por nombre (columna 0).
        """
        text = (text or "").strip()
        try:
            if text:
                # Coincidencia parcial (case-insensitive)
                self.proxy.setFilterWildcard(f"*{text}*")
            else:
                # Limpiar filtro
                self.proxy.setFilterWildcard("")
        except Exception:
            pass

    def _recursive_filter(self, index, text):
        """
        Recursivamente muestra/oculta elementos según el filtro.
        """
        if not index.isValid():
            return
        file_name = self.model.fileName(index).lower()
        is_match = text in file_name
        self.tree.setRowHidden(index.row(), index.parent(), not is_match)
        if self.model.isDir(index):
            for i in range(self.model.rowCount(index)):
                child_index = self.model.index(i, 0, index)
                self._recursive_filter(child_index, text)

    def open_context_menu(self, pos):
        index = self.tree.indexAt(pos)
        if not index.isValid():
            return
        menu = QMenu()
        open_action = menu.addAction("Abrir")
        rename_action = menu.addAction("Renombrar")
        delete_action = menu.addAction("Eliminar")
        action = menu.exec(self.tree.viewport().mapToGlobal(pos))
        # Mapear índice del proxy al modelo fuente
        try:
            src_index = self.proxy.mapToSource(index)
        except Exception:
            src_index = None
        file_path = self.model.filePath(src_index) if src_index else ""
        if action == open_action:
            self.file_opened.emit(file_path)
        elif action == rename_action:
            try:
                self.tree.edit(index)
            except Exception:
                pass
        elif action == delete_action and os.path.exists(file_path):
            if os.path.isdir(file_path):
                os.rmdir(file_path)
            else:
                os.remove(file_path)

    def on_file_open(self, index):
        """
        Señaliza que un archivo ha sido abierto.
        """
        # Mapear índice del proxy al modelo fuente
        try:
            src_index = self.proxy.mapToSource(index)
        except Exception:
            src_index = None
        file_path = self.model.filePath(src_index) if src_index else ""
        if os.path.isfile(file_path):
            self.file_opened.emit(file_path)

    def set_root(self, path):
        """
        Cambia la carpeta raíz del explorador y actualiza la vista.
        """
        self.root_path = path
        # Obtener el índice directamente del modelo y mapear al proxy
        try:
            index = self.model.setRootPath(path)
        except Exception:
            index = self.model.index(path)
        try:
            self.tree.setRootIndex(self.proxy.mapFromSource(index))
        except Exception:
            self.tree.setRootIndex(self.proxy.mapFromSource(self.model.index(path)))
        self.path_label.setText(f"Explorando: {path}")
        # Restablecer filtro para evitar que ocultaciones previas persistan
        try:
            if hasattr(self, 'search_bar'):
                text = self.search_bar.text().lower()
            else:
                text = ""
            self.filter_files(text)
        except Exception:
            pass

        # Aplicar orden actual desde combo
        try:
            self._apply_sort_from_combo()
        except Exception:
            pass

    # --- Controles: ordenar, carpetas primero, ocultos, refrescar ---
    def _apply_sort_from_combo(self):
        try:
            idx = self.sort_combo.currentIndex()
            # Columnas de QFileSystemModel: 0=Nombre, 1=Tamaño, 2=Tipo, 3=Fecha
            mapping = {
                0: (0, Qt.AscendingOrder),     # Nombre A→Z
                1: (0, Qt.DescendingOrder),    # Nombre Z→A
                2: (3, Qt.DescendingOrder),    # Fecha reciente
                3: (3, Qt.AscendingOrder),     # Fecha antigua
                4: (1, Qt.DescendingOrder),    # Tamaño grande→pequeño
                5: (1, Qt.AscendingOrder),     # Tamaño pequeño→grande
                6: (2, Qt.AscendingOrder),     # Tipo A→Z
            }
            col, order = mapping.get(idx, (0, Qt.AscendingOrder))
            self.tree.sortByColumn(col, order)
        except Exception:
            pass

    def _on_toggle_folders_first(self, checked: bool):
        try:
            self.proxy.set_folders_first(bool(checked))
        except Exception:
            pass

    def _on_toggle_show_hidden(self, checked: bool):
        try:
            filters = QDir.AllEntries | QDir.NoDotAndDotDot
            if checked:
                filters |= QDir.Hidden
            self.model.setFilter(filters)
        except Exception:
            pass

    def _on_refresh(self):
        try:
            idx = self.model.setRootPath(self.root_path)
            self.tree.setRootIndex(self.proxy.mapFromSource(idx))
        except Exception:
            pass

    # Conectar controles
    try:
        FileExplorer._controls_connected  # type: ignore
    except Exception:
        def _connect_controls(self):
            try:
                self.sort_combo.currentIndexChanged.connect(lambda _: self._apply_sort_from_combo())
            except Exception:
                pass
            try:
                self.cb_folders_first.toggled.connect(self._on_toggle_folders_first)
            except Exception:
                pass
            try:
                self.cb_show_hidden.toggled.connect(self._on_toggle_show_hidden)
            except Exception:
                pass
            try:
                self.refresh_btn.clicked.connect(self._on_refresh)
            except Exception:
                pass
        # Llamar conexión tras creación
        _connect_controls(self)
