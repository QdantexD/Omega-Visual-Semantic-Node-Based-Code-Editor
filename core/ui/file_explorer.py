"""
Improved FileExplorer for PySide6
- Modular structure (UI + Model + Animator)
- Clearer logging instead of silent pass
- Robust root switching (fix: explorer/tree not visible after selecting folder)
- Better filtering using QRegularExpression
- Centralized signal connections
- Settings persisted as a compact JSON in QSettings

Usage: instantiate FileExplorer(root_path="/some/path") and insert into a layout.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

from PySide6.QtCore import (
    QDir,
    QSettings,
    QTimer,
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    QRegularExpression,
    QSize,
    Signal,
)
from PySide6.QtGui import QIcon, QFontMetrics
# Nota: evitamos QGraphicsOpacityEffect por estabilidad de pintado en algunos sistemas
from PySide6.QtWidgets import (
    QWidget,
    QTreeView,
    QVBoxLayout,
    QFileSystemModel,
    QMenu,
    QLineEdit,
    QLabel,
    QHBoxLayout,
    QToolButton,
    QFrame,
    QComboBox,
    QPushButton,
    QCheckBox,
)
from PySide6.QtCore import QSortFilterProxyModel


LOG = logging.getLogger("file_explorer")
LOG.setLevel(logging.INFO)


class SimpleSortFilterProxy(QSortFilterProxyModel):
    """Proxy con carpeta-primero y soporte para regex en filtro."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folders_first = True

    def set_folders_first(self, enable: bool):
        self.folders_first = bool(enable)
        self.invalidate()

    def lessThan(self, left, right):
        if self.folders_first:
            try:
                model = self.sourceModel()
                left_is_dir = model.isDir(left)
                right_is_dir = model.isDir(right)
                if left_is_dir != right_is_dir:
                    # Queremos que las carpetas aparezcan antes que archivos
                    return left_is_dir and not right_is_dir
            except Exception as e:
                LOG.warning("Proxy lessThan failed: %s", e)
        return super().lessThan(left, right)


class UIAnimator:
    @staticmethod
    def animate_property(target, prop, start, end, duration=220, easing=QEasingCurve.InOutCubic, on_finished=None):
        anim = QPropertyAnimation(target, prop)
        anim.setDuration(duration)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(easing)
        if on_finished:
            anim.finished.connect(on_finished)
        anim.start()
        return anim


class FileExplorer(QWidget):
    """Explorador de archivos mejorado y robusto.

    Señales:
        file_opened(str) -- Emite ruta absoluta cuando se abre un archivo
        compact_requested(bool) -- Para integraciones que requieren cambiar a modo compacto
    """

    file_opened = Signal(str)
    compact_requested = Signal(bool)

    DEFAULT_SETTINGS_KEY = "Explorer/state"

    def __init__(self, root_path: Optional[str] = None):
        super().__init__()
        self.root_path = root_path or QDir.currentPath()
        # Props
        self._rail_width = 48
        self._expanded_width = 240
        self._compact = False
        self._opacity_effect: Optional[QGraphicsOpacityEffect] = None

        # Widgets
        self._create_widgets()
        self._apply_styles()

        # Models
        self._create_models()

        # Connect signals
        self._connect_signals()

        # Load settings and initialize view
        self._load_settings()
        QTimer.singleShot(50, self._post_init)

    # ----------------- Creación UI -----------------
    def _create_widgets(self):
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Rail izquierdo (íconos)
        self.rail = QFrame()
        self.rail.setObjectName("ExplorerRail")
        self.rail.setFixedWidth(self._rail_width)
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
            btn.setCursor(Qt.PointingHandCursor)
            return btn

        self.btn_files = mk_btn("folder", "Archivos")
        rail_layout.addWidget(self.btn_files)
        rail_layout.addStretch(1)
        root_layout.addWidget(self.rail)

        # Contenido principal
        self.content = QFrame()
        self.content.setObjectName("ExplorerContent")
        self.layout = QVBoxLayout(self.content)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(6)

        # Sin efectos de opacidad para evitar conflictos de QPainter
        self._opacity_effect = None

        # Título y header
        self.title_label = QLabel("Explorer")
        self.title_label.setObjectName("ExplorerTitle")
        self.layout.addWidget(self.title_label)

        section_header = QFrame()
        section_header.setObjectName("ExplorerSectionHeader")
        section_header_layout = QHBoxLayout(section_header)
        section_header_layout.setContentsMargins(0, 0, 0, 0)

        self.folder_toggle_btn = QToolButton()
        self.folder_toggle_btn.setCheckable(True)
        self.folder_toggle_btn.setChecked(True)
        try:
            down = QIcon.fromTheme("pan-down-symbolic")
            if not down.isNull():
                self.folder_toggle_btn.setIcon(down)
            else:
                self.folder_toggle_btn.setText("▾")
        except Exception:
            self.folder_toggle_btn.setText("▾")
        self.folder_toggle_btn.setAutoRaise(True)
        self.folder_label = QLabel("Folder")
        section_header_layout.addWidget(self.folder_toggle_btn)
        section_header_layout.addWidget(self.folder_label)
        section_header_layout.addStretch(1)

        self.folder_menu_btn = QToolButton()
        try:
            more = QIcon.fromTheme("open-menu-symbolic")
            if not more.isNull():
                self.folder_menu_btn.setIcon(more)
            else:
                self.folder_menu_btn.setText("…")
        except Exception:
            self.folder_menu_btn.setText("…")
        self.folder_menu_btn.setAutoRaise(True)
        section_header_layout.addWidget(self.folder_menu_btn)

        self.layout.addWidget(section_header)

        # Search bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Buscar archivos...")
        try:
            self.search_bar.setClearButtonEnabled(True)
        except Exception:
            pass
        self.layout.addWidget(self.search_bar)

        # Path label
        self.path_label = QLabel("")
        self.path_label.setObjectName("ExplorerPath")
        self.layout.addWidget(self.path_label)

        # Controls
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
        self.cb_show_hidden = QCheckBox("Mostrar ocultos")
        self.refresh_btn = QPushButton("Actualizar")

        for w in (self.sort_combo, self.cb_folders_first, self.cb_show_hidden, self.refresh_btn):
            controls_layout.addWidget(w)
        controls_layout.addStretch(1)
        self.layout.addWidget(controls)

        # Tree view
        self.tree = QTreeView()
        self.tree.setHeaderHidden(False)
        self.tree.setSortingEnabled(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.setUniformRowHeights(True)
        try:
            self.tree.setAlternatingRowColors(True)
            self.tree.setIndentation(16)
            self.tree.header().setStretchLastSection(True)
            self.tree.setIconSize(QSize(18, 18))
        except Exception:
            pass
        self.tree.setDragEnabled(True)
        self.tree.setDragDropMode(QTreeView.DragOnly)

        # Empty label
        self.empty_label = QLabel("Carpeta vacía")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setVisible(False)
        self.empty_label.setStyleSheet("color: #94a3b8; font-size: 13px; padding: 12px;")

        # Contenedor de sección para animación de colapso/expansión
        self.section_body = QFrame()
        self.section_body_layout = QVBoxLayout(self.section_body)
        self.section_body_layout.setContentsMargins(0, 0, 0, 0)
        self.section_body_layout.setSpacing(0)
        # Sin efectos de opacidad en el contenedor de sección
        self._section_opacity = None

        self.section_body_layout.addWidget(self.tree, 1)
        self.section_body_layout.addWidget(self.empty_label)
        self.section_body.setMaximumHeight(16777215)
        self.layout.addWidget(self.section_body, 1)

        root_layout.addWidget(self.content)

    def _apply_styles(self):
        self.setStyleSheet(
            """
            /* Paleta y componentes al estilo VS Code, más pulidos */
            QWidget#ExplorerRail { background: #141923; border-right: 1px solid #2a2f39; }
            QWidget#ExplorerContent { background: #0f1318; }

            /* Título y sección */
            QLabel { font-size: 12px; color: #b0bac5; }
            QLabel#ExplorerTitle { font-weight: 600; letter-spacing: 0.3px; color: #d8dee9; padding: 2px 0 8px 2px; }
            QFrame#ExplorerSectionHeader { background: #11161d; border: none; border-bottom: 1px solid #202a36; }
            QFrame#ExplorerSectionHeader QLabel { color: #cbd5e1; }
            QToolButton { color: #cbd5e1; padding: 6px; }
            QToolButton:hover { background: #273041; border-radius: 6px; }

            /* Barra de búsqueda y breadcrumb */
            QLineEdit { background: #0e1217; color: #e5e9f0; border: 1px solid #2b3443; padding: 6px 8px; border-radius: 8px; }
            QLabel#ExplorerPath { background: #0e1217; color: #9aa6b2; border: 1px solid #202a36; padding: 6px 10px; border-radius: 8px; }

            /* Controles */
            QComboBox { background: #0e1217; color: #e5e9f0; border: 1px solid #2b3443; padding: 4px 8px; border-radius: 6px; }
            QComboBox QAbstractItemView { background: #0e1217; color: #e5e9f0; selection-background-color: #1b2a3a; }
            QCheckBox { color: #cbd5e1; padding: 2px 4px; }
            QPushButton { background: #182233; color: #e5e9f0; border: 1px solid #2b3443; padding: 6px 10px; border-radius: 6px; }
            QPushButton:hover { background: #213047; }

            /* Árbol */
            QTreeView { background: #0c1015; color: #e5e9f0; border: 1px solid #202a36; outline: 0; }
            QTreeView::item { margin: 1px 0; padding: 4px; }
            QTreeView::item:selected { background: #203040; border: 1px solid #2e3c50; }
            QTreeView::item:hover { background: #182433; }
            QHeaderView::section { background: #151a22; color: #cbd5e1; padding: 6px; border: none; border-bottom: 1px solid #202a36; }

            /* Scrollbars */
            QScrollBar:vertical { background: #0f1318; width: 10px; margin: 0; }
            QScrollBar::handle:vertical { background: #2a3444; border-radius: 5px; min-height: 24px; }
            QScrollBar::handle:vertical:hover { background: #344055; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal { background: #0f1318; height: 10px; margin: 0; }
            QScrollBar::handle:horizontal { background: #2a3444; border-radius: 5px; min-width: 24px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
            """
        )

    # ----------------- Animación de visibilidad -----------------
    def animate_visibility(self, visible: bool):
        """Muestra/oculta el Explorer con una animación de opacidad suave.

        Se usa cuando el sidebar se expande/colapsa desde la Activity Bar.
        """
        try:
            # Fallback sin efecto: visibilidad directa (estable)
            self.setVisible(bool(visible))
        except Exception as e:
            LOG.warning("animate_visibility error: %s", e)
            self.setVisible(bool(visible))

    # ----------------- Models & Proxy -----------------
    def _create_models(self):
        self.model = QFileSystemModel(self)
        # Evitar incluir . y ..
        self.model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)

        # Validar root_path
        if not self.root_path or not os.path.isdir(self.root_path):
            self.root_path = QDir.currentPath() or QDir.homePath()

        # Proxy
        self.proxy = SimpleSortFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setDynamicSortFilter(True)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(0)

        self.tree.setModel(self.proxy)

        # Configurar columnas al estilo VS Code: nombre principal, resto opcional
        try:
            header = self.tree.header()
            header.setStretchLastSection(False)
            header.setHighlightSections(False)
            header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            from PySide6.QtWidgets import QHeaderView
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
            # Ocultar columnas secundarias por defecto para presentación limpia
            self.tree.setColumnHidden(1, True)
            self.tree.setColumnHidden(2, True)
            self.tree.setColumnHidden(3, True)
        except Exception:
            pass

        # Inicial root index
        idx = self.model.setRootPath(self.root_path)
        self._set_tree_root_from_source_index(idx)

        # Icon map (se puede ampliar)
        self.icons = {
            ".py": QIcon.fromTheme("application-python"),
            ".txt": QIcon.fromTheme("text-plain"),
            ".json": QIcon.fromTheme("application-json"),
            "folder": QIcon.fromTheme("folder"),
        }

    def _apply_column_layout(self):
        """Reaplica configuración de columnas (por ejemplo tras cambiar root)."""
        try:
            from PySide6.QtWidgets import QHeaderView
            header = self.tree.header()
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
            self.tree.setColumnHidden(1, True)
            self.tree.setColumnHidden(2, True)
            self.tree.setColumnHidden(3, True)
        except Exception:
            pass

    # ----------------- Señales & Conexiones -----------------
    def _connect_signals(self):
        # UI interactions
        self.search_bar.textChanged.connect(self.filter_files)
        self.folder_toggle_btn.toggled.connect(self._on_section_toggled)
        self.folder_menu_btn.clicked.connect(self._open_folder_menu)
        self.sort_combo.currentIndexChanged.connect(self._apply_sort_from_combo)
        self.cb_folders_first.toggled.connect(self._on_toggle_folders_first)
        self.cb_show_hidden.toggled.connect(self._on_toggle_show_hidden)
        self.refresh_btn.clicked.connect(self._on_refresh)
        self.btn_files.clicked.connect(self._on_folder_clicked)

        # Tree interactions
        self.tree.doubleClicked.connect(self.on_file_open)
        self.tree.customContextMenuRequested.connect(self.open_context_menu)

        # Model signals
        self.model.directoryLoaded.connect(lambda path: self._update_empty_state())
        self.proxy.rowsInserted.connect(lambda *_: self._update_empty_state())
        self.proxy.rowsRemoved.connect(lambda *_: self._update_empty_state())
        self.proxy.modelReset.connect(lambda *_: self._update_empty_state())

    # ----------------- Filtering & Sorting -----------------
    def filter_files(self, text: str):
        text = (text or "").strip()
        try:
            if text:
                # Escape para regex y búsqueda de substring
                esc = QRegularExpression.escape(text)
                rx = QRegularExpression(f".*{esc}.*", QRegularExpression.CaseInsensitiveOption)
                self.proxy.setFilterRegularExpression(rx)
            else:
                self.proxy.setFilterRegularExpression(QRegularExpression(""))
            # actualizar estado visible
            self._schedule_refresh()
            self._update_empty_state()
        except Exception as e:
            LOG.warning("Filter error: %s", e)

    def _on_folder_clicked(self):
        """Asegura que la sección Folder esté visible y da foco al árbol.

        Corrige el caso donde el botón estaba conectado pero el método no existía.
        """
        try:
            self.content.setVisible(True)
            self.folder_toggle_btn.setChecked(True)
            self.section_body.setVisible(True)
            # Refrescar con la raíz actual y aplicar orden
            self._schedule_refresh()
            self._apply_sort_from_combo()
            self.focus_tree()
            self._update_empty_state()
        except Exception as e:
            LOG.warning("Folder click handler failed: %s", e)

    # ----------------- Modo compacto (para integrarse con Activity Bar externa) -----------------
    def set_compact_mode(self, enable: bool):
        """Oculta el rail interno y ajusta márgenes para integrarse con una barra lateral externa.

        Al habilitar compact mode, el Explorer se comporta como el panel de VS Code.
        """
        self._compact = bool(enable)
        try:
            self.rail.setVisible(not enable)
            if enable:
                self.layout.setContentsMargins(10, 8, 8, 8)
            else:
                self.layout.setContentsMargins(8, 8, 8, 8)
        except Exception:
            pass

    def _apply_sort_from_combo(self):
        try:
            idx = self.sort_combo.currentIndex()
            mapping = {
                0: (0, Qt.AscendingOrder),
                1: (0, Qt.DescendingOrder),
                2: (3, Qt.DescendingOrder),
                3: (3, Qt.AscendingOrder),
                4: (1, Qt.DescendingOrder),
                5: (1, Qt.AscendingOrder),
                6: (2, Qt.AscendingOrder),
            }
            col, order = mapping.get(idx, (0, Qt.AscendingOrder))
            self.tree.sortByColumn(col, order)
            self._save_settings()
            self._update_empty_state()
        except Exception as e:
            LOG.warning("Apply sort failed: %s", e)

    def _on_toggle_folders_first(self, checked: bool):
        self.proxy.set_folders_first(bool(checked))
        self._save_settings()
        self._schedule_refresh()

    def _on_toggle_show_hidden(self, checked: bool):
        try:
            filters = QDir.AllEntries | QDir.NoDotAndDotDot
            if checked:
                filters |= QDir.Hidden
            self.model.setFilter(filters)
            self._save_settings()
            self._schedule_refresh()
        except Exception as e:
            LOG.warning("Toggle show hidden failed: %s", e)

    # ----------------- Context menu & open -----------------
    def open_context_menu(self, pos):
        index = self.tree.indexAt(pos)
        if not index.isValid():
            return
        menu = QMenu()
        open_action = menu.addAction("Abrir")
        rename_action = menu.addAction("Renombrar")
        delete_action = menu.addAction("Eliminar")
        chosen = menu.exec(self.tree.viewport().mapToGlobal(pos))
        try:
            src_index = self.proxy.mapToSource(index)
        except Exception:
            src_index = None
        file_path = self.model.filePath(src_index) if src_index else ""
        if chosen == open_action:
            if os.path.isfile(file_path):
                self.file_opened.emit(file_path)
        elif chosen == rename_action:
            try:
                self.tree.edit(index)
            except Exception as e:
                LOG.warning("Rename failed: %s", e)
        elif chosen == delete_action:
            try:
                if os.path.isdir(file_path):
                    os.rmdir(file_path)
                else:
                    os.remove(file_path)
                # refrescar
                self._schedule_refresh()
            except Exception as e:
                LOG.warning("Delete failed: %s", e)

    def on_file_open(self, index):
        try:
            src_index = self.proxy.mapToSource(index)
        except Exception:
            src_index = None
        file_path = self.model.filePath(src_index) if src_index else ""
        if os.path.isfile(file_path):
            self.file_opened.emit(file_path)

    # ----------------- Root management (fix bug) -----------------
    def set_root(self, path: str):
        """Cambia la carpeta raíz y asegura que el árbol y la sección sean visibles.

        Este método corrige el bug donde la vista podía quedar oculta al seleccionar carpeta: garantizamos
        que el índice raíz sea válido y forzamos la visibilidad del panel y de la sección Folder.
        """
        if not path:
            return
        self.root_path = path
        LOG.info("Setting explorer root -> %s", path)
        self.folder_label.setText(self._project_display_name(path))
        self.folder_label.setToolTip(path)
        # Actualizar modelo y rootIndex
        try:
            idx = self.model.setRootPath(path)
        except Exception:
            idx = self.model.index(path)

        # Mapear robustamente y aplicar
        self._set_tree_root_from_source_index(idx)

        self.path_label.setText(f"Explorando: {path}")
        # Asegurar visibilidad (bugfix): mostrar contenido y marcar sección visible
        self.content.setVisible(True)
        self.folder_toggle_btn.setChecked(True)
        self.section_body.setVisible(True)

        # Limpiar/Aplicar filtro actual
        current_filter = self.search_bar.text().strip()
        self.filter_files(current_filter)
        # Ajustar presentación de columnas para el nuevo root
        self._apply_column_layout()
        # Reordenar/guardar
        self._apply_sort_from_combo()
        self._save_settings()
        self._update_empty_state()

    def _set_tree_root_from_source_index(self, src_index):
        """Mapea un índice del modelo fuente al proxy y lo aplica en la vista.

        Se encarga de casos inválidos y usa self.model.index(path) como fallback.
        """
        try:
            if src_index is None or not src_index.isValid():
                # intentar con path directo
                src_index = self.model.index(self.root_path)
        except Exception:
            src_index = self.model.index(self.root_path)
        try:
            proxy_idx = self.proxy.mapFromSource(src_index)
            if proxy_idx.isValid():
                self.tree.setRootIndex(proxy_idx)
            else:
                # Fall back: mostrar desde la raíz global
                self.tree.setRootIndex(self.proxy.mapFromSource(self.model.index(self.root_path)))
        except Exception as e:
            LOG.warning("Failed to set tree root: %s", e)
            try:
                self.tree.setRootIndex(self.proxy.mapFromSource(self.model.index(self.root_path)))
            except Exception:
                pass

    # ----------------- Refresh & empty-state -----------------
    def _on_refresh(self):
        try:
            idx = self.model.setRootPath(self.root_path)
            self._set_tree_root_from_source_index(idx)
            self._update_empty_state()
        except Exception as e:
            LOG.warning("Refresh failed: %s", e)

    def _schedule_refresh(self):
        if not hasattr(self, "_refresh_timer") or self._refresh_timer is None:
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.setInterval(120)
            self._refresh_timer.timeout.connect(self._on_refresh)
        self._refresh_timer.start()

    def _update_empty_state(self):
        try:
            root_idx = self.tree.rootIndex()
            # Usar hasChildren para detectar si hay elementos (más eficiente)
            src_idx = self.proxy.mapToSource(root_idx) if root_idx.isValid() else self.model.index(self.root_path)
            is_empty = not self.model.hasChildren(src_idx)
            section_visible = self.folder_toggle_btn.isChecked()
            # Mantener coherencia de visibilidad con el contenedor de sección
            try:
                if hasattr(self, "section_body"):
                    self.section_body.setVisible(section_visible)
            except Exception:
                pass
            self.empty_label.setVisible(is_empty and section_visible)
            self.tree.setVisible((not is_empty) and section_visible)
        except Exception as e:
            LOG.warning("Update empty state failed: %s", e)

    # ----------------- Section toggle -----------------
    def _on_section_toggled(self, checked: bool):
        try:
            # Animar mostrar/ocultar sección completa
            if hasattr(self, "section_body"):
                self._animate_section(bool(checked))
            else:
                # Fallback si no existe el contenedor
                self.tree.setVisible(bool(checked))
            # Actualizar ícono
            try:
                if checked:
                    ic = QIcon.fromTheme("pan-down-symbolic")
                    if not ic.isNull():
                        self.folder_toggle_btn.setIcon(ic)
                    else:
                        self.folder_toggle_btn.setText("▾")
                else:
                    ic = QIcon.fromTheme("pan-end-symbolic")
                    if not ic.isNull():
                        self.folder_toggle_btn.setIcon(ic)
                    else:
                        self.folder_toggle_btn.setText("▸")
            except Exception:
                pass
            self._save_settings()
        except Exception as e:
            LOG.warning("Section toggle failed: %s", e)

    def _animate_section(self, expand: bool):
        try:
            body = getattr(self, "section_body", None)
            if body is None:
                return
            current_w = max(0, body.width())
            start_w = current_w
            end_w = (max(90, body.sizeHint().width())) if expand else 0

            if expand:
                body.setVisible(True)

            def _on_finished():
                try:
                    if not expand:
                        body.setVisible(False)
                    body.setMaximumWidth(16777215)
                    self._update_empty_state()
                except Exception:
                    pass

            UIAnimator.animate_property(body, b"maximumWidth", start_w, end_w, duration=180, on_finished=_on_finished)
        except Exception as e:
            LOG.warning("Animate section failed: %s", e)

    # ----------------- Folder menu -----------------
    def _open_folder_menu(self):
        menu = QMenu()
        act_open = menu.addAction("Abrir carpeta…")
        act_current = menu.addAction("Proyecto actual")
        act_docs = menu.addAction("Documentos")
        act_desktop = menu.addAction("Escritorio")
        menu.addSeparator()
        # Opciones rápidas de presentación/columns al estilo VS Code
        act_col_size = menu.addAction("Mostrar columna Size")
        act_col_type = menu.addAction("Mostrar columna Type")
        act_col_date = menu.addAction("Mostrar columna Date Modified")
        act_col_size.setCheckable(True)
        act_col_type.setCheckable(True)
        act_col_date.setCheckable(True)
        try:
            act_col_size.setChecked(not self.tree.isColumnHidden(1))
            act_col_type.setChecked(not self.tree.isColumnHidden(2))
            act_col_date.setChecked(not self.tree.isColumnHidden(3))
        except Exception:
            pass
        menu.addSeparator()
        act_folders_first = menu.addAction("Carpetas primero")
        act_show_hidden = menu.addAction("Mostrar ocultos")
        act_folders_first.setCheckable(True)
        act_show_hidden.setCheckable(True)
        act_folders_first.setChecked(self.cb_folders_first.isChecked())
        act_show_hidden.setChecked(self.cb_show_hidden.isChecked())
        menu.addSeparator()
        act_reset = menu.addAction("Restablecer Explorer")

        chosen = menu.exec(self.folder_menu_btn.mapToGlobal(self.folder_menu_btn.rect().bottomLeft()))
        if chosen == act_open:
            from PySide6.QtWidgets import QFileDialog

            path = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta", self.root_path)
            if path:
                self.set_root(path)
        elif chosen == act_current:
            self.set_root(QDir.currentPath())
        elif chosen == act_docs:
            home = QDir.homePath()
            path = os.path.join(home, "Documents")
            self.set_root(path)
        elif chosen == act_desktop:
            home = QDir.homePath()
            path = os.path.join(home, "Desktop")
            self.set_root(path)
        elif chosen == act_col_size:
            try:
                self.tree.setColumnHidden(1, not act_col_size.isChecked())
            except Exception:
                pass
        elif chosen == act_col_type:
            try:
                self.tree.setColumnHidden(2, not act_col_type.isChecked())
            except Exception:
                pass
        elif chosen == act_col_date:
            try:
                self.tree.setColumnHidden(3, not act_col_date.isChecked())
            except Exception:
                pass
        elif chosen == act_folders_first:
            self.cb_folders_first.setChecked(act_folders_first.isChecked())
            self._on_toggle_folders_first(act_folders_first.isChecked())
        elif chosen == act_show_hidden:
            self.cb_show_hidden.setChecked(act_show_hidden.isChecked())
            self._on_toggle_show_hidden(act_show_hidden.isChecked())
        elif chosen == act_reset:
            try:
                s = self._settings()
                s.beginGroup("Explorer")
                s.remove("")
                s.endGroup()
            except Exception as e:
                LOG.warning("Reset settings failed: %s", e)
            self.set_root(QDir.currentPath() or QDir.homePath())

    # ----------------- Compact mode -----------------
    def set_compact(self, compact: bool):
        self._compact = bool(compact)
        if self._compact:
            def hide_content():
                self.content.setVisible(False)
                self._save_settings()
            UIAnimator.animate_property(self, b"maximumWidth", self.maximumWidth(), self._rail_width, duration=220)
        else:
            self.content.setVisible(True)
            UIAnimator.animate_property(self, b"maximumWidth", self.maximumWidth(), self._expanded_width, duration=220)
            self._save_settings()

    # ----------------- Settings -----------------
    def _settings(self) -> QSettings:
        try:
            return QSettings("Codemind", "Editor")
        except Exception:
            return QSettings()

    def _load_settings(self):
        s = self._settings()
        try:
            raw = s.value(self.DEFAULT_SETTINGS_KEY, "{}", type=str)
            data = json.loads(raw or "{}")
        except Exception as e:
            LOG.warning("Load settings failed: %s", e)
            data = {}

        try:
            # Apply basic settings
            last_root = data.get("root")
            if last_root and os.path.isdir(last_root):
                self.root_path = last_root
            self.cb_folders_first.setChecked(bool(data.get("folders_first", True)))
            self.cb_show_hidden.setChecked(bool(data.get("show_hidden", False)))
            self.folder_toggle_btn.setChecked(bool(data.get("visible", True)))
            self.sort_combo.setCurrentIndex(int(data.get("sort", 0)))
        except Exception as e:
            LOG.warning("Apply settings failed: %s", e)

    def _save_settings(self):
        s = self._settings()
        try:
            data = {
                "root": self.root_path,
                "sort": self.sort_combo.currentIndex(),
                "folders_first": self.cb_folders_first.isChecked(),
                "show_hidden": self.cb_show_hidden.isChecked(),
                "visible": self.folder_toggle_btn.isChecked(),
            }
            s.setValue(self.DEFAULT_SETTINGS_KEY, json.dumps(data))
        except Exception as e:
            LOG.warning("Save settings failed: %s", e)

    # ----------------- Utilities -----------------
    def _project_display_name(self, path: str) -> str:
        try:
            base = os.path.basename(os.path.normpath(path)) or "Folder"
            fm = QFontMetrics(self.font())
            return fm.elidedText(base, Qt.ElideRight, 220)
        except Exception:
            return "Folder"

    def _post_init(self):
        # Asegurar root inicial y estado
        try:
            # Aplicar root y orden
            self.set_root(self.root_path)
            self._apply_sort_from_combo()
            self._apply_column_layout()
            self._update_empty_state()
        except Exception as e:
            LOG.warning("Post init failed: %s", e)

    # ----------------- Helpers para integración -----------------
    def focus_tree(self):
        try:
            self.tree.setFocus()
        except Exception:
            pass
