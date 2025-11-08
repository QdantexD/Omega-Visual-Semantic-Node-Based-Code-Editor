from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QMenu, QInputDialog, QRubberBand, QApplication, QGraphicsDropShadowEffect, QGraphicsPathItem,
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel, QWidget, QPushButton
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QRect, QSize, QPoint, QTimer, QStandardPaths
from PySide6.QtGui import QPainter, QColor, QPen, QCursor, QBrush, QTransform, QIcon, QSurfaceFormat
try:
    from PySide6.QtOpenGLWidgets import QOpenGLWidget
except Exception:
    QOpenGLWidget = None
import math, logging, os, hashlib, shutil, difflib
from .node_item import NodeItem
from .group_item import GroupItem
from .connection_item import ConnectionItem
from ..nodes.variable_node import VariableNode
from ..library.variable_library import variable_library
from ..library.cpp_builtins_catalog import get_cpp_catalog
from ..library.python_node_stdlib import get_python_catalog
from ..ui.app_icons import make_hat_icon_neon
from .runtime import GraphRuntime
from .node_model import NodeModel, project_to_dict, project_from_dict
from .grid import draw_background_grid
from .demo_graph import build_demo_graph

logger = logging.getLogger("core.node_view")


class NodeView(QGraphicsView):
    """
    NodeView Pro:
    - Grid de fondo limpio
    - Pan con botón medio o Alt+LMB (estilo Houdini)
    - Selección con click derecho o rubber-band
    - Zoom con Ctrl+Wheel
    - Menú de creación de nodos con Tab
    - Textos de nodos nítidos al zoom
    - Sombras opcionales en nodos
    - Optimizado para rendimiento
    """

    selectedNodeChanged = Signal(object)
    editNodeRequested = Signal(object)
    editingExited = Signal(object)
    # Señales de UI para status bar estilo VS Code
    zoomChanged = Signal(float)
    selectionCountChanged = Signal(int)
    # Señal para notificar que el grafo fue evaluado
    graphEvaluated = Signal()

    PAN_BUTTON = Qt.MiddleButton
    SELECT_BUTTON = Qt.RightButton

    def __init__(self, parent=None):
        super().__init__(parent)

        # Render y optimización
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        # Preferencia de renderizado en GPU (OpenGL) y nivel de MSAA
        self._gpu_enabled = True
        self._msaa_samples = 8
        # Configurar viewport inicial (OpenGL si disponible; fallback a software si falla)
        self._setup_viewport(enable_gl=self._gpu_enabled)
        # Modo de actualización: usar FullViewportUpdate cuando hay GPU para animaciones fluidas
        try:
            if self._gpu_enabled:
                self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
            else:
                self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)
        except Exception:
            self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)
        # Evitar forzar WA_OpaquePaintEvent que puede chocar con algunos drivers
        try:
            self.viewport().setAttribute(Qt.WA_OpaquePaintEvent, False)
        except Exception:
            pass
        # Sin cache global para el fondo; preferimos repintado limpio
        try:
            self.setCacheMode(QGraphicsView.CacheNone)
        except Exception:
            pass
        self.setOptimizationFlag(QGraphicsView.DontAdjustForAntialiasing, True)
        # Evitar guardado/restaurado del estado del painter por item para mayor rendimiento
        # Los items de la escena ya realizan save/restore explícito donde corresponde
        self.setOptimizationFlag(QGraphicsView.DontSavePainterState, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        # Aceptar arrastrar/soltar (para archivos desde Explorer/OS)
        try:
            self.setAcceptDrops(True)
            # En QGraphicsView los eventos van al viewport; habilitar también ahí
            try:
                self.viewport().setAcceptDrops(True)
            except Exception:
                pass
        except Exception:
            pass
        
        # Sistema de conexiones
        self.connections = []
        self.connection_in_progress = None
        self.selected_connection = None
        # Estado para reencaminar (rewire) conexiones desde IN
        self._rewire_original = None

        # Scene
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.setScene(self._scene)
        self._scene.selectionChanged.connect(self._on_scene_selection_changed)
        # Asegurar que la vista acepte y capture eventos de teclado (TAB)
        try:
            self.setFocusPolicy(Qt.StrongFocus)
            self.setFocus()
        except Exception:
            pass
        # Política de scroll al estilo Houdini (sin barras; pan con ratón)
        try:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        except Exception:
            pass
        # Configuración de minimapa estilo Houdini (pintado en foreground)
        self._minimap_enabled = False
        self._minimap_size = QSize(180, 130)
        self._minimap_margin = 12

        # Pan y zoom
        self._zoom = 0
        self._pending_pan = False
        self._pan_active = False
        self._press_pos = QPoint()
        self._last_mouse_pos = QPoint()
        # Efectos en nodos: desactivados por defecto para evitar repintados complejos
        self._node_shadows_enabled = False

        # Estado UX paleta: uso, recientes y favoritos
        self._palette_usage_counts = {}
        self._palette_recent = []
        self._palette_favorites = []
        self._palette_category_filter = "All"

        # Rubber-band
        self._rubber_band = QRubberBand(QRubberBand.Rectangle, self.viewport())
        self._rubber_origin = QPoint()
        self._rubber_selecting = False

        # Última ventana de edición de conexión creada
        self._last_connection_editor = None

        # Hint visual de snap activo
        self._snap_hint_node = None

        # Estado de corte y vista previa de conexiones
        # Inicializados aquí para evitar AttributeError en eventos del mouse
        self._cut_mode = False
        self._cut_path = None
        self._cut_item = None
        # Vista previa de conexión (guía visual entre OUT e IN cercano)
        self._preview_conn_item = None

        # Undo/Redo
        self._undo_stack = []  # lista de tuplas (undo_fn, redo_fn, label)
        self._redo_stack = []
        self._suspend_undo = False  # evita registrar durante ejecución de undo/redo

        # Ajustar hints de render según escala inicial (≈1.0)
        try:
            self._apply_dynamic_render_hints(float(self.transform().m11()))
        except Exception:
            pass

    def _push_undo(self, undo_fn, redo_fn, label: str = ""):
        try:
            if self._suspend_undo:
                return
            self._undo_stack.append((undo_fn, redo_fn, label))
            # Una nueva acción invalida posibles redos
            self._redo_stack.clear()
        except Exception:
            pass

    def undo(self):
        try:
            if not self._undo_stack:
                return
            entry = self._undo_stack.pop()
            undo_fn, redo_fn, label = entry
            self._suspend_undo = True
            try:
                undo_fn()
            finally:
                self._suspend_undo = False
            # Permite rehacer lo deshecho
            self._redo_stack.append((redo_fn, undo_fn, label))
        except Exception:
            pass

    def redo(self):
        try:
            if not self._redo_stack:
                return
            entry = self._redo_stack.pop()
            redo_fn, undo_fn, label = entry
            self._suspend_undo = True
            try:
                redo_fn()
            finally:
                self._suspend_undo = False
            # Vuelve a permitir deshacer
            self._undo_stack.append((undo_fn, redo_fn, label))
        except Exception:
            pass

        # Grid
        self._base_grid = 40
        self._major_factor = 4

        # Timer de animación para conexiones (flujo estilo Blueprint)
        try:
            self._anim_timer = QTimer(self)
            self._anim_timer.setInterval(16)  # ~60 FPS
            self._anim_timer.timeout.connect(self._tick_connection_animation)
            self._anim_timer.start()
        except Exception:
            logger.exception("No se pudo iniciar el timer de animación")
        # Paleta estilo VS Code (oscuro elegante)
        self._bg_color = QColor(30, 32, 36)  # fondo profundo
        self._grid_color = QColor(68, 72, 80, 80)   # líneas finas discretas
        self._major_grid_color = QColor(94, 98, 110, 130)  # líneas mayores sutiles

        # Timer de conveniencia
        self._defer_timer = QTimer(self)
        self._defer_timer.setSingleShot(True)

        # Runtime de grafo (propagación de valores)
        self._runtime = None
        try:
            self._runtime = GraphRuntime(self)
        except Exception:
            logger.exception("No se pudo inicializar GraphRuntime")
        # (Eliminado: creación duplicada del minimapa)

        # Grafo demo delegado al helper para mantener NodeView más ligero
        try:
            self.ensure_demo_graph()
        except Exception:
            logger.warning("No se pudo crear el grafo demo")
        # Evaluar grafo inicial
        try:
            self.evaluate_graph()
        except Exception as e:
            logger.warning(f"Error evaluando grafo inicial: {e}")

    # ----------------------
    # GPU / OpenGL helpers
    # ----------------------
    def _setup_viewport(self, enable_gl: bool = True) -> None:
        """Configura el viewport.

        Si `enable_gl` es True y hay soporte de OpenGL, usa QOpenGLWidget con
        MSAA, depth y stencil. En caso de error, cae a QWidget (software).
        """
        try:
            if enable_gl and QOpenGLWidget is not None:
                fmt = QSurfaceFormat()
                # Perfil core y versión razonable para compatibilidad amplia
                try:
                    fmt.setProfile(QSurfaceFormat.CoreProfile)
                    fmt.setVersion(3, 3)
                except Exception:
                    pass
                # Multisampling y buffers auxiliares para mejor calidad
                try:
                    fmt.setSamples(int(max(0, min(int(self._msaa_samples), 16))))
                except Exception:
                    fmt.setSamples(8)
                try:
                    fmt.setDepthBufferSize(24)
                    fmt.setStencilBufferSize(8)
                except Exception:
                    pass
                # VSync cuando esté disponible
                try:
                    fmt.setSwapInterval(1)
                except Exception:
                    pass
                QSurfaceFormat.setDefaultFormat(fmt)
                gl = QOpenGLWidget()
                try:
                    gl.setFormat(fmt)
                except Exception:
                    pass
                self.setViewport(gl)
                self._gpu_enabled = True
                logger.info("Viewport OpenGL activado (MSAA=%d)", getattr(self, "_msaa_samples", 8))
            else:
                # Software fallback
                self.setViewport(QWidget())
                self._gpu_enabled = False
                logger.info("Viewport software QWidget activado")
        except Exception:
            # Si falla cualquier paso, garantizar que haya viewport funcional
            try:
                self.setViewport(QWidget())
            except Exception:
                pass
            self._gpu_enabled = False
            logger.exception("Fallo configurando viewport OpenGL; se usa software.")

    def enable_gpu_rendering(self, enabled: bool) -> None:
        """Activa o desactiva renderizado con GPU (OpenGL)."""
        try:
            enabled = bool(enabled)
        except Exception:
            enabled = True
        # Reconfigurar viewport sólo si cambia el estado
        if enabled != bool(getattr(self, "_gpu_enabled", True)):
            self._gpu_enabled = enabled
            self._setup_viewport(enable_gl=enabled)
            try:
                self.viewport().update()
            except Exception:
                pass

    def set_msaa_samples(self, samples: int) -> None:
        """Ajusta el nivel de MSAA y reconfigura el viewport si está en GPU."""
        try:
            s = int(samples)
        except Exception:
            s = 8
        s = max(0, min(s, 16))
        if s == getattr(self, "_msaa_samples", 8):
            return
        self._msaa_samples = s
        # Si estamos en GPU, volver a crear el viewport para aplicar formato
        if isinstance(self.viewport(), QOpenGLWidget):
            self._setup_viewport(enable_gl=True)

    def is_gpu_active(self) -> bool:
        """Indica si el viewport actual usa QOpenGLWidget (GPU)."""
        try:
            return isinstance(self.viewport(), QOpenGLWidget)
        except Exception:
            return False

    def _apply_dynamic_render_hints(self, scale_x: float) -> None:
        """Ajusta hints de render en función de la escala para equilibrar calidad/rendimiento.

        - Escala baja (<0.65): desactiva antialiasing y suavizado de pixmaps.
        - Escala media (0.65–1.25): antialiasing básico y text antialiasing.
        - Escala alta (>1.25): antialiasing y suavizado de pixmaps completos.
        """
        try:
            s = float(scale_x)
        except Exception:
            s = 1.0
        try:
            if s < 0.65:
                self.setRenderHint(QPainter.Antialiasing, False)
                self.setRenderHint(QPainter.HighQualityAntialiasing, False)
                self.setRenderHint(QPainter.SmoothPixmapTransform, False)
                self.setRenderHint(QPainter.TextAntialiasing, False)
            elif s <= 1.25:
                self.setRenderHint(QPainter.Antialiasing, True)
                self.setRenderHint(QPainter.HighQualityAntialiasing, False)
                self.setRenderHint(QPainter.SmoothPixmapTransform, True)
                self.setRenderHint(QPainter.TextAntialiasing, True)
            else:
                self.setRenderHint(QPainter.Antialiasing, True)
                # Alta calidad sólo en grandes ampliaciones
                try:
                    self.setRenderHint(QPainter.HighQualityAntialiasing, True)
                except Exception:
                    pass
                self.setRenderHint(QPainter.SmoothPixmapTransform, True)
                self.setRenderHint(QPainter.TextAntialiasing, True)
        except Exception:
            pass

    def ensure_demo_graph(self):
        """Si la escena está vacía, delega la creación del grafo demo."""
        try:
            build_demo_graph(self)
            # Asegurar que no queden nodos Output/Group Output del demo anterior
            try:
                leftovers = [it for it in self._scene.items() if isinstance(it, NodeItem) and str(getattr(it, 'node_type', '')).lower() in ('output','group_output')]
            except Exception:
                leftovers = []
            for it in leftovers:
                try:
                    self.remove_node(it, record_undo=False)
                except Exception:
                    pass
        except Exception:
            logger.exception("No se pudo asegurar el grafo demo")

    # ----------------------
    # Background Grid
    # ----------------------
    def drawBackground(self, painter: QPainter, rect: QRectF):
        # Asegurar colores/base inicializados aunque drawBackground se invoque temprano
        try:
            if not hasattr(self, "_bg_color"):
                self._bg_color = QColor(30, 32, 36)
            if not hasattr(self, "_grid_color"):
                self._grid_color = QColor(68, 72, 80, 80)
            if not hasattr(self, "_major_grid_color"):
                self._major_grid_color = QColor(94, 98, 110, 130)
            if not hasattr(self, "_base_grid"):
                self._base_grid = 40
            if not hasattr(self, "_major_factor"):
                self._major_factor = 4
        except Exception:
            pass
        # Delegar a util para mantener NodeView más simple, con clipping para reducir overdraw
        try:
            painter.save()
            painter.setClipRect(rect)
        except Exception:
            pass
        draw_background_grid(
            painter,
            rect,
            self._bg_color,
            self._grid_color,
            self._major_grid_color,
            float(self._base_grid),
            int(self._major_factor),
        )
        try:
            painter.restore()
        except Exception:
            pass

    # ----------------------
    # Selection Handling
    # ----------------------
    def _on_scene_selection_changed(self):
        selected_items = self._scene.selectedItems()
        node = next((it for it in selected_items if isinstance(it, NodeItem)), None)
        self.selectedNodeChanged.emit(node)
        try:
            self.selectionCountChanged.emit(len(selected_items))
        except Exception:
            pass

    # ----------------------
    # Zoom
    # ----------------------
    def wheelEvent(self, event):
        # Permitir zoom con rueda incluso sin Ctrl (comportamiento configurable)
        requires_ctrl = getattr(self, "_wheel_zoom_requires_ctrl", False)
        if (requires_ctrl and (event.modifiers() & Qt.ControlModifier)) or (not requires_ctrl):
            factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25
            new_zoom = self._zoom + (1 if event.angleDelta().y() > 0 else -1)
            if -40 <= new_zoom <= 80:
                self._zoom = new_zoom
                self.scale(factor, factor)
                # Emitir zoom aproximado como escala X (para status bar)
                try:
                    scale_x = float(self.transform().m11())
                    self.zoomChanged.emit(scale_x)
                    # Ajustar hints de render dinámicamente según escala
                    try:
                        self._apply_dynamic_render_hints(scale_x)
                    except Exception:
                        pass
                    # Aplicar comportamiento adaptativo de textos en nodos
                    try:
                        for it in self._scene.items():
                            if isinstance(it, NodeItem):
                                it.apply_adaptive_text_behavior(scale_x)
                    except Exception:
                        pass
                    # Log de diagnóstico para comprobar escala efectiva de la vista
                    try:
                        print(f"[NodeView] scale_x={scale_x:.3f}")
                    except Exception:
                        pass
                except Exception:
                    pass
                try:
                    self._update_minimap_fit()
                except Exception:
                    pass
            event.accept()
            return
        super().wheelEvent(event)

    def add_connection(self, start_item, end_item, start_port="output", end_port="input", record_undo: bool = True):
        """Agrega una conexión entre dos nodos."""
        connection = ConnectionItem(start_item, end_item, start_port, end_port)
        self._scene.addItem(connection)
        self.connections.append(connection)
        
        # Actualizar nodos
        start_item.add_connection(connection)
        end_item.add_connection(connection)
        # Reevaluar el grafo y emitir señal
        try:
            self.evaluate_graph()
        except Exception:
            pass
        
        # Registrar undo/redo
        try:
            if record_undo and not self._suspend_undo:
                self._push_undo(
                    undo_fn=lambda: self.remove_connection(connection, record_undo=False),
                    redo_fn=lambda: self.add_connection(start_item, end_item, start_port, end_port, record_undo=False),
                    label="add_connection"
                )
        except Exception:
            pass

        return connection

    def _tick_connection_animation(self):
        """Actualiza la animación de todas las conexiones visibles."""
        try:
            for conn in list(self.connections):
                if hasattr(conn, "tick_animation"):
                    conn.tick_animation()
            if self.connection_in_progress and hasattr(self.connection_in_progress, "tick_animation"):
                self.connection_in_progress.tick_animation()
            # Asegurar repintado del viewport para animaciones con OpenGL
            try:
                self.viewport().update()
            except Exception:
                pass
        except Exception:
            # Animación es no-crítica; no bloquear por errores
            pass

    def remove_connection(self, connection, record_undo: bool = True):
        """Elimina una conexión."""
        if connection in self.connections:
            # Capturar propiedades para rehacer si aplica
            try:
                start_item = connection.start_item
                end_item = connection.end_item
                start_port = getattr(connection, "start_port", "output")
                end_port = getattr(connection, "end_port", "input")
            except Exception:
                start_item = None
                end_item = None
                start_port = "output"
                end_port = "input"
            self.connections.remove(connection)
            
            # Actualizar nodos
            connection.start_item.remove_connection(connection)
            if connection.end_item:
                connection.end_item.remove_connection(connection)
            
            self._scene.removeItem(connection)
            # Actualizar runtime y emitir señal de grafo evaluado
            try:
                self.evaluate_graph()
            except Exception:
                pass
            # Registrar undo/redo
            try:
                if record_undo and not self._suspend_undo and start_item is not None and end_item is not None:
                    self._push_undo(
                        undo_fn=lambda: self.add_connection(start_item, end_item, start_port, end_port, record_undo=False),
                        redo_fn=lambda: self.remove_connection(next((c for c in self.connections if c.start_item is start_item and c.end_item is end_item and getattr(c, 'start_port', None) == start_port and getattr(c, 'end_port', None) == end_port), connection), record_undo=False),
                        label="remove_connection"
                    )
            except Exception:
                pass

    def clear_connections(self):
        """Elimina todas las conexiones."""
        for connection in self.connections[:]:
            self.remove_connection(connection)
        # Actualizar runtime
        try:
            if self._runtime:
                self._runtime.rebuild_from_view()
                self._runtime.evaluate_all()
        except Exception:
            pass

    def update_all_connections(self):
        """Actualiza todas las conexiones."""
        for connection in self.connections:
            connection.update_path()
        # Reevaluar tras cambios de layout
        try:
            if self._runtime:
                self._runtime.rebuild_from_view()
                self._runtime.evaluate_all()
        except Exception:
            pass

    # ----------------------
    # Mouse Events
    # ----------------------
    def mousePressEvent(self, event):
        vp_item = self.itemAt(event.pos())
        scene_pos = self.mapToScene(event.pos())

        # Duplicación rápida con Ctrl+Click sobre un nodo
        try:
            if (event.modifiers() & Qt.ControlModifier) and isinstance(vp_item, NodeItem) and (
                event.button() == Qt.LeftButton or event.button() == self.SELECT_BUTTON
            ):
                self._quick_duplicate_node(vp_item)
                event.accept()
                return
        except Exception:
            pass

        # Iniciar trazo de corte si el modo Y está activo
        if self._cut_mode and event.button() == Qt.LeftButton:
            try:
                from PySide6.QtGui import QPainterPath, QPen
                # Click directo sobre cable: cortar al instante
                if isinstance(vp_item, ConnectionItem):
                    try:
                        self.remove_connection(vp_item)
                    except Exception:
                        pass
                    event.accept()
                    return
                # Click en vacío: eliminar cables bajo un pequeño radio
                removed_any = False
                click_cut = QPainterPath()
                click_cut.addEllipse(scene_pos, 8.0, 8.0)
                for conn in list(self.connections):
                    try:
                        if not conn.path().isEmpty() and click_cut.intersects(conn.path()):
                            self.remove_connection(conn)
                            removed_any = True
                    except Exception:
                        pass
                if removed_any:
                    event.accept()
                    return
                # Si no hay cable bajo el clic, permitir trazo para cortar múltiples
                self._cut_path = QPainterPath()
                self._cut_path.moveTo(scene_pos)
                self._cut_item = QGraphicsPathItem()
                pen = QPen(QColor("#ef4444"))  # rojo corte
                pen.setWidth(2)
                pen.setStyle(Qt.DashLine)
                self._cut_item.setPen(pen)
                self._cut_item.setZValue(1000)
                self._scene.addItem(self._cut_item)
                event.accept()
                return
            except Exception:
                pass

        # Clic derecho sobre un cable: eliminar conexión rápidamente
        if event.button() == self.SELECT_BUTTON and isinstance(vp_item, ConnectionItem):
            try:
                self.remove_connection(vp_item)
            except Exception:
                pass
            event.accept()
            return

        # Pan con botón central o Alt+LMB (estilo Houdini)
        if (event.button() == self.PAN_BUTTON and vp_item is None) or (
            event.button() == Qt.LeftButton and (event.modifiers() & Qt.AltModifier)
        ):
            self._pending_pan = True
            self._pan_active = False
            self._press_pos = event.pos()
            self._last_mouse_pos = event.pos()
            event.accept()
            return

        if event.button() == self.SELECT_BUTTON:
            if isinstance(vp_item, NodeItem):
                if not (event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                    for it in self._scene.selectedItems():
                        it.setSelected(False)
                vp_item.setSelected(True)
                self._on_scene_selection_changed()
                # Mostrar menú contextual de selección
                try:
                    self._show_selection_menu(event.pos())
                except Exception:
                    logger.exception("Error mostrando menú contextual")
                event.accept()
                return
            # Fondo vacío: iniciar selección por banda con botón derecho
            try:
                self.setFocus()
            except Exception:
                pass
            try:
                self._rubber_origin = event.pos()
                self._rubber_band.setGeometry(QRect(self._rubber_origin, QSize()))
                self._rubber_band.show()
                self._rubber_selecting = True
            except Exception:
                logger.exception("No se pudo iniciar rubber-band con botón derecho")
            event.accept()
            return

        # Iniciar conexión o rewire (Blueprint-style)
        if event.button() == Qt.LeftButton and isinstance(vp_item, NodeItem):
            # Intentar iniciar desde OUT
            start_port = self._nearest_port(vp_item, scene_pos, port_type="output", threshold=24.0)
            if start_port:
                try:
                    conn = ConnectionItem(vp_item, None, start_port=start_port, end_port="input")
                    self._scene.addItem(conn)
                    self.connection_in_progress = conn
                    event.accept()
                    return
                except Exception:
                    logger.exception("Error iniciando conexión")
                    self.connection_in_progress = None
            # Intentar reencaminar desde IN si hay conexión existente
            in_port = self._nearest_port(vp_item, scene_pos, port_type="input", threshold=24.0)
            if in_port:
                try:
                    existing = None
                    for c in vp_item.connections:
                        if c.end_item is vp_item and getattr(c, "end_port", None) == in_port:
                            existing = c
                            break
                    if existing is not None:
                        # Guardar origen para posible cancelación
                        self._rewire_original = (existing, existing.end_item, existing.end_port)
                        # Desacoplar extremo final y comenzar arrastre
                        try:
                            vp_item.remove_connection(existing)
                        except Exception:
                            pass
                        existing.end_item = None
                        existing.end_port = None
                        existing.set_temp_end(scene_pos)
                        self.connection_in_progress = existing
                        event.accept()
                        return
                except Exception:
                    logger.exception("Error iniciando rewire desde IN")
            # Si no hay puerto cerca, dejar que el nodo se mueva/seleccione normalmente
            super().mousePressEvent(event)
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Inicialización defensiva de atributos usados por eventos tempranos
        try:
            if not hasattr(self, "_cut_mode"):
                self._cut_mode = False
            if not hasattr(self, "_cut_item"):
                self._cut_item = None
            if not hasattr(self, "_cut_path"):
                self._cut_path = None
            if not hasattr(self, "_pending_pan"):
                self._pending_pan = False
            if not hasattr(self, "_pan_active"):
                self._pan_active = False
            if not hasattr(self, "_rubber_selecting"):
                self._rubber_selecting = False
        except Exception:
            pass
        # Trazo de corte activo: continuar dibujando la línea
        if self._cut_mode and self._cut_item is not None and (event.buttons() & Qt.LeftButton):
            try:
                scene_pos = self.mapToScene(event.pos())
                self._cut_path.lineTo(scene_pos)
                self._cut_item.setPath(self._cut_path)
                event.accept()
                return
            except Exception:
                pass
        if self._pending_pan and not self._pan_active:
            if (event.pos() - self._press_pos).manhattanLength() >= QApplication.startDragDistance():
                self._pan_active = True
                self._pending_pan = False
                self._last_mouse_pos = event.pos()
                self.setCursor(Qt.ClosedHandCursor)

        if self._pan_active:
            delta = event.pos() - self._last_mouse_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            self._last_mouse_pos = event.pos()
            event.accept()
            return

        if self._rubber_selecting:
            rect = QRect(self._rubber_origin, event.pos()).normalized()
            self._rubber_band.setGeometry(rect)
            # Autopan al acercarse al borde durante selección por banda
            try:
                self._autopan_if_near_edges(event.pos())
            except Exception:
                pass
            event.accept()
            return

        # Hint de puerto OUT al pasar cerca (sin conexión en progreso)
        try:
            if self.connection_in_progress is None and not (event.buttons() & Qt.LeftButton):
                vp_item = self.itemAt(event.pos())
                if isinstance(vp_item, NodeItem):
                    scene_pos = self.mapToScene(event.pos())
                    out_port = self._nearest_port(vp_item, scene_pos, port_type="output", threshold=28.0)
                    if out_port:
                        try:
                            vp_item.set_snap_hint_output_port(out_port)
                        except Exception:
                            pass
                        # Dibujar guía previa hacia el IN más cercano
                        try:
                            start_pos = vp_item.get_port_position(out_port, 'output') if hasattr(vp_item, 'get_port_position') else None
                            target, end_port = self._find_node_and_port_near_input(start_pos or scene_pos, threshold=48.0)
                            if start_pos is not None and target is not None and end_port:
                                end_pos = target.get_port_position(end_port, 'input') if hasattr(target, 'get_port_position') else None
                                if end_pos is not None:
                                    from PySide6.QtGui import QPainterPath, QPen
                                    # Crear/actualizar item de vista previa
                                    if self._preview_conn_item is None:
                                        self._preview_conn_item = QGraphicsPathItem()
                                        pen = QPen(QColor("#f59e0b"))
                                        pen.setWidth(2)
                                        pen.setStyle(Qt.DashLine)
                                        self._preview_conn_item.setPen(pen)
                                        self._preview_conn_item.setZValue(900)
                                        self._scene.addItem(self._preview_conn_item)
                                    path = QPainterPath()
                                    path.moveTo(start_pos)
                                    # Curva suave estilo blueprint
                                    ctrl_dx = abs(end_pos.x() - start_pos.x()) * 0.5 + 40.0
                                    c1 = QPointF(start_pos.x() + ctrl_dx, start_pos.y())
                                    c2 = QPointF(end_pos.x() - ctrl_dx, end_pos.y())
                                    path.cubicTo(c1, c2, end_pos)
                                    self._preview_conn_item.setPath(path)
                                else:
                                    # No hay IN válido: limpiar vista previa
                                    if self._preview_conn_item is not None:
                                        try:
                                            self._scene.removeItem(self._preview_conn_item)
                                        except Exception:
                                            pass
                                        self._preview_conn_item = None
                            else:
                                # No hay IN cercano: limpiar vista previa
                                if self._preview_conn_item is not None:
                                    try:
                                        self._scene.removeItem(self._preview_conn_item)
                                    except Exception:
                                        pass
                                    self._preview_conn_item = None
                        except Exception:
                            pass
                    else:
                        try:
                            vp_item.set_snap_hint_output_port(None)
                        except Exception:
                            pass
                        # Limpiar vista previa si no hay OUT destacado
                        if self._preview_conn_item is not None:
                            try:
                                self._scene.removeItem(self._preview_conn_item)
                            except Exception:
                                pass
                            self._preview_conn_item = None
                else:
                    # Limpiar cualquier hint residual en nodos seleccionados
                    for it in self._scene.items():
                        if isinstance(it, NodeItem):
                            try:
                                it.set_snap_hint_output_port(None)
                            except Exception:
                                pass
                    # Limpiar vista previa al salir de un nodo
                    if self._preview_conn_item is not None:
                        try:
                            self._scene.removeItem(self._preview_conn_item)
                        except Exception:
                            pass
                        self._preview_conn_item = None
        except Exception:
            pass

        # Mientras se arrastra una conexión, actualizar punto final temporal con snap
        if self.connection_in_progress is not None:
            try:
                # Sólo actualizar mientras se mantiene el click izquierdo
                if event.buttons() & Qt.LeftButton:
                    # Ocultar la vista previa durante arrastre real
                    if self._preview_conn_item is not None:
                        try:
                            self._scene.removeItem(self._preview_conn_item)
                        except Exception:
                            pass
                        self._preview_conn_item = None
                    scene_pos = self.mapToScene(event.pos())
                    # Buscar nodo y puerto cercano con umbral pequeño (colisión precisa)
                    target, end_port = self._find_node_and_port_near_input(scene_pos, threshold=24.0)
                    if target is not None and end_port:
                        # Activar resaltado de puerto destino
                        try:
                            target.set_snap_hint_input_port(end_port)
                            # Limpiar hint anterior si cambia de nodo
                            if self._snap_hint_node is not None and self._snap_hint_node is not target:
                                try:
                                    self._snap_hint_node.set_snap_hint_input_port(None)
                                except Exception:
                                    pass
                            self._snap_hint_node = target
                        except Exception:
                            pass
                        # Posición exacta del puerto para imán
                        snap_pos = target.get_port_position(end_port, 'input') if hasattr(target, 'get_port_position') else None
                        self.connection_in_progress.set_temp_end(snap_pos or scene_pos)
                    else:
                        # Sin snap: limpiar resaltado si existía
                        if self._snap_hint_node is not None:
                            try:
                                self._snap_hint_node.set_snap_hint_input_port(None)
                            except Exception:
                                pass
                            self._snap_hint_node = None
                        snap_pos = self._snap_temp_end_to_nearest_input(scene_pos)
                        self.connection_in_progress.set_temp_end(snap_pos or scene_pos)
                    # Autopan al acercarse al borde durante arrastre de conexión
                    try:
                        self._autopan_if_near_edges(event.pos())
                    except Exception:
                        pass
                    event.accept()
                    return
            except Exception:
                logger.exception("Error actualizando conexión en arrastre")

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # Finalizar corte y seccionar cables intersectados
        if self._cut_mode and self._cut_item is not None and event.button() == Qt.LeftButton:
            try:
                cut_path = self._cut_item.path()
                to_remove = []
                for conn in list(self.connections):
                    try:
                        if not conn.path().isEmpty() and cut_path.intersects(conn.path()):
                            to_remove.append(conn)
                    except Exception:
                        pass
                for conn in to_remove:
                    try:
                        self.remove_connection(conn)
                    except Exception:
                        pass
            except Exception:
                pass
            # Limpiar trazo de corte
            try:
                if self._cut_item:
                    self._scene.removeItem(self._cut_item)
            except Exception:
                pass
            self._cut_item = None
            self._cut_path = None
            # Limpiar vista previa si existía
            if self._preview_conn_item is not None:
                try:
                    self._scene.removeItem(self._preview_conn_item)
                except Exception:
                    pass
                self._preview_conn_item = None
            event.accept()
            return
        if event.button() == self.PAN_BUTTON or (event.button() == Qt.LeftButton and self._pan_active):
            self._pan_active = False
            self._pending_pan = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        if event.button() == self.SELECT_BUTTON and self._rubber_selecting:
            vp_rect = self._rubber_band.geometry()
            self._rubber_band.hide()
            self._rubber_selecting = False
            try:
                tl = self.mapToScene(vp_rect.topLeft())
                br = self.mapToScene(vp_rect.bottomRight())
                scene_rect = QRectF(tl, br).normalized()

                if not (event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                    for it in self._scene.selectedItems():
                        it.setSelected(False)

                for it in self._scene.items(scene_rect, mode=Qt.IntersectsItemShape):
                    if isinstance(it, NodeItem):
                        it.setSelected(True)
                self._on_scene_selection_changed()
            except Exception:
                logger.exception("Error finishing rubber-band")
            event.accept()
            return

        # Limpiar hint OUT si existía tras soltar
        try:
            for it in self._scene.items():
                if isinstance(it, NodeItem):
                    it.set_snap_hint_output_port(None)
        except Exception:
            pass

        # Finalizar conexión si estaba en progreso
        if event.button() == Qt.LeftButton and self.connection_in_progress is not None:
            try:
                scene_pos = self.mapToScene(event.pos())
                target, end_port = self._find_node_and_port_near_input(scene_pos, threshold=24.0)
                if target is not None and end_port and target is not self.connection_in_progress.start_item:
                    self.connection_in_progress.end_item = target
                    self.connection_in_progress.end_port = end_port
                    self.connection_in_progress.update_path()
                    # Limpiar estado temporal para que no siga el cursor
                    try:
                        self.connection_in_progress.finalize_end()
                    except Exception:
                        pass
                    # Limpiar hints visuales
                    try:
                        if self._snap_hint_node is not None:
                            self._snap_hint_node.set_snap_hint_input_port(None)
                    except Exception:
                        pass
                    self._snap_hint_node = None
                    # Registrar conexión (evitar duplicado)
                    if self.connection_in_progress not in self.connections:
                        self.connections.append(self.connection_in_progress)
                    self.connection_in_progress.start_item.add_connection(self.connection_in_progress)
                    target.add_connection(self.connection_in_progress)
                    # Autoacomodar nodos conectados: destino a la derecha del origen
                    try:
                        self._auto_arrange_after_connection(self.connection_in_progress)
                    except Exception:
                        pass
                    # Editor de conexión deshabilitado: no mostrar ventana emergente
                    # Actualizar runtime y emitir señal para refresco en tiempo real
                    try:
                        self.evaluate_graph()
                    except Exception:
                        pass
                    # Registrar undo/redo para la conexión creada manualmente
                    try:
                        self._push_undo(
                            undo_fn=lambda: self.remove_connection(self.connection_in_progress, record_undo=False),
                            redo_fn=lambda: self.add_connection(self.connection_in_progress.start_item, target, self.connection_in_progress.start_port, end_port, record_undo=False),
                            label="add_connection"
                        )
                    except Exception:
                        pass
                else:
                    # Cancelación: restaurar si era rewire, eliminar si era nueva
                    try:
                        if hasattr(self, "_rewire_original") and self._rewire_original and self._rewire_original[0] is self.connection_in_progress:
                            # Si el usuario "saca" el conector y suelta en vacío, eliminar la conexión
                            try:
                                self.remove_connection(self.connection_in_progress)
                            except Exception:
                                pass
                        else:
                            self._scene.removeItem(self.connection_in_progress)
                    except Exception:
                        pass
                    # Limpiar hints visuales
                    try:
                        if self._snap_hint_node is not None:
                            self._snap_hint_node.set_snap_hint_input_port(None)
                    except Exception:
                        pass
                    self._snap_hint_node = None
                    # Reevaluar grafo tras cancelación/reencamine
                    try:
                        if hasattr(self, '_runtime') and self._runtime:
                            self._runtime.rebuild_from_view()
                            self._runtime.evaluate_all()
                    except Exception:
                        pass
                # Limpiar estado de rewire también
                try:
                    self._rewire_original = None
                except Exception:
                    pass
                self.connection_in_progress = None
                event.accept()
                return
            except Exception:
                logger.exception("Error finalizando conexión")
                if self.connection_in_progress:
                    try:
                        self._scene.removeItem(self.connection_in_progress)
                    except Exception:
                        pass
                    self.connection_in_progress = None
                # Limpiar hints visuales en caso de error
                try:
                    if self._snap_hint_node is not None:
                        self._snap_hint_node.set_snap_hint_input_port(None)
                except Exception:
                    pass
                self._snap_hint_node = None
                event.accept()
                return

        super().mouseReleaseEvent(event)

    def _auto_arrange_after_connection(self, connection):
        """Acomoda rápidamente los nodos tras crear una conexión.
        Regla simple: el nodo destino va a la derecha del origen con margen,
        alineado verticalmente. Luego actualiza rutas y reevalúa.
        """
        try:
            start = getattr(connection, 'start_item', None)
            end = getattr(connection, 'end_item', None)
            if start is None or end is None:
                return
            # Espaciado según ancho del origen + margen
            try:
                sr = start.rect()
                spacing = max(160.0, sr.width() + 120.0)
            except Exception:
                spacing = 220.0
            new_x = float(start.x()) + spacing
            new_y = float(start.y())
            # Evitar solapamiento básico
            try:
                for it in self._scene.items():
                    if it is end:
                        continue
                    if isinstance(it, NodeItem):
                        dx = abs(float(it.x()) - new_x)
                        dy = abs(float(it.y()) - new_y)
                        if dx < 60.0 and dy < 40.0:
                            new_y += 60.0
            except Exception:
                pass
            end.setPos(new_x, new_y)
            # Actualizar conexiones y runtime
            try:
                self.update_all_connections()
            except Exception:
                pass
            try:
                if hasattr(self, '_runtime') and self._runtime:
                    self._runtime.rebuild_from_view()
                    self._runtime.evaluate_all()
            except Exception:
                pass
        except Exception:
            logger.exception("Error en autoacomodo tras conexión")

    def mouseDoubleClickEvent(self, event):
        vp_item = self.itemAt(event.pos())
        if isinstance(vp_item, NodeItem):
            self.editNodeRequested.emit(vp_item)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def notify_node_editing_exited(self, node: NodeItem):
        """Hook llamado por NodeItem cuando se pulsa 'Salir' en el editor incrustado.
        Emite la señal para que la ventana principal sincronice su interfaz."""
        try:
            self.editingExited.emit(node)
        except Exception:
            pass
        # Re-evaluar el grafo al salir de edición para reflejar cambios de contenido
        try:
            self.evaluate_graph()
        except Exception:
            pass

    # ----------------------
    # Snap Helpers
    # ----------------------
    def _snap_temp_end_to_nearest_input(self, scene_pos: QPointF):
        """Devuelve la posición del puerto de entrada más cercano si está dentro del umbral."""
        try:
            target, end_port = self._find_node_and_port_near_input(scene_pos)
            if target is not None and end_port:
                # Posición exacta del puerto para imán
                if hasattr(target, 'get_port_position'):
                    return target.get_port_position(end_port, 'input')
                # Fallback a borde izquierdo del nodo si no hay API
                rect = target.rect()
                pos = target.scenePos()
                return pos + QPointF(0, rect.height() / 2)
        except Exception:
            pass
        return None

    # ----------------------
    # Autopan Helper
    # ----------------------
    def _autopan_if_near_edges(self, vp_pos: QPoint, margin: int = 24, step: int = 32):
        """Desplaza la vista cuando el cursor está cerca del borde del viewport.

        Se invoca durante selección por banda y arrastre de conexiones para un UX fluido.
        """
        try:
            vp_rect = self.viewport().rect()
            w, h = vp_rect.width(), vp_rect.height()
            x, y = vp_pos.x(), vp_pos.y()
            hsb = self.horizontalScrollBar()
            vsb = self.verticalScrollBar()
            if x <= margin:
                hsb.setValue(hsb.value() - step)
            elif x >= w - margin:
                hsb.setValue(hsb.value() + step)
            if y <= margin:
                vsb.setValue(vsb.value() - step)
            elif y >= h - margin:
                vsb.setValue(vsb.value() + step)
        except Exception:
            pass

    # ----------------------
    # Node Creation (Palette)
    # ----------------------
    def keyPressEvent(self, event):
        # Undo/Redo por teclado
        try:
            if event.modifiers() & Qt.ControlModifier:
                if event.key() == Qt.Key_Z:
                    self.undo()
                    event.accept()
                    return
                if event.key() == Qt.Key_Y or ((event.modifiers() & Qt.ShiftModifier) and event.key() == Qt.Key_Z):
                    self.redo()
                    event.accept()
                    return
        except Exception:
            pass
        # Abrir paleta de nodos con tecla 'R' (antes TAB)
        if event.key() == Qt.Key_R or (event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_K) or (event.key() == Qt.Key_Slash):
            # Abrir paleta estilo Houdini con filtro
            try:
                self._show_tab_palette()
                event.accept()
                return
            except Exception:
                # Fallback al menú clásico si la paleta falla
                try:
                    self._show_tab_menu()
                    event.accept()
                    return
                except Exception:
                    pass
        # Atajo para eliminar nodos Output/Group Output: Ctrl+Shift+Del
        try:
            if (event.modifiers() & Qt.ControlModifier) and (event.modifiers() & Qt.ShiftModifier) and event.key() == Qt.Key_Delete:
                try:
                    to_remove = [it for it in self._scene.items() if isinstance(it, NodeItem) and str(getattr(it, 'node_type', '')).lower() in ('output','group_output')]
                except Exception:
                    to_remove = []
                for it in to_remove:
                    try:
                        self.remove_node(it, record_undo=True)
                    except Exception:
                        pass
                try:
                    self.evaluate_graph()
                except Exception:
                    pass
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)
        # Alternar minimapa con 'N'
        if event.key() == Qt.Key_N:
            try:
                if hasattr(self, '_minimap') and self._minimap is not None:
                    self._minimap.setVisible(not self._minimap.isVisible())
                    # Reposicionar si se vuelve visible
                    if self._minimap.isVisible():
                        self._update_minimap_fit()
                        self._layout_minimap()
                event.accept()
                return
            except Exception:
                pass
        # Encuadrar selección con 'F' (Frame Selected) – centra y ajusta zoom
        if event.key() == Qt.Key_F:
            try:
                # Usa helper dedicado para encuadrar con fitInView y margen
                self.center_on_selected()
                event.accept()
                return
            except Exception:
                pass
        # Modo corte Houdini con 'Y'
        if event.key() == Qt.Key_Y:
            try:
                self._cut_mode = True
                # Capturar teclado para que el KeyRelease siempre llegue aquí
                try:
                    self.grabKeyboard()
                except Exception:
                    pass
                self.setCursor(Qt.CrossCursor)
                event.accept()
                return
            except Exception:
                pass
        # Cancelar modo corte con Escape
        if event.key() == Qt.Key_Escape and self._cut_mode:
            try:
                self._cut_mode = False
                self.setCursor(Qt.ArrowCursor)
                if self._cut_item is not None:
                    try:
                        self._scene.removeItem(self._cut_item)
                    except Exception:
                        pass
                self._cut_item = None
                self._cut_path = None
                event.accept()
                return
            except Exception:
                pass
        # Salir de edición del nodo activo con Escape (cuando no estamos en modo corte)
        if event.key() == Qt.Key_Escape and not self._cut_mode:
            try:
                for it in self._scene.items():
                    if isinstance(it, NodeItem) and getattr(it, '_editing', False):
                        try:
                            it.set_editing(False)
                        except Exception:
                            pass
                        try:
                            self.editingExited.emit(it)
                        except Exception:
                            pass
                        event.accept()
                        return
            except Exception:
                pass
        # Eliminar nodos seleccionados con tecla Delete
        if event.key() == Qt.Key_Delete:
            try:
                for it in self._scene.selectedItems():
                    if isinstance(it, NodeItem):
                        self.remove_node(it)
                    elif isinstance(it, ConnectionItem):
                        self.remove_connection(it)
                event.accept()
                return
            except Exception:
                logger.exception("Error eliminando nodos con Delete")
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        # Salir del modo corte al soltar 'Y'
        if event.key() == Qt.Key_Y and self._cut_mode and not event.isAutoRepeat():
            try:
                self._cut_mode = False
                self.setCursor(Qt.ArrowCursor)
                try:
                    self.releaseKeyboard()
                except Exception:
                    pass
                if self._cut_item is not None:
                    try:
                        self._scene.removeItem(self._cut_item)
                    except Exception:
                        pass
                self._cut_item = None
                self._cut_path = None
                event.accept()
                return
            except Exception:
                pass
        super().keyReleaseEvent(event)

    # Editor de conexión eliminado: mantener API vacía para compatibilidad
    def open_last_connection_editor(self, expand=False):
        return

    # API pública para abrir el menú TAB desde otras vistas (barra inferior)
    def open_tab_menu(self):
        try:
            self._show_tab_palette()
        except Exception:
            pass

    def _show_tab_palette(self):
        """Muestra una paleta flotante con filtro al estilo Houdini para crear nodos.
        Estética mejorada: panel oscuro elegante con esquinas redondeadas, sombra y cierre
        automático al hacer clic fuera.
        """
        # Posición en escena anclada al cursor o centro del viewport
        view_pos = self.mapFromGlobal(QCursor.pos())
        try:
            vp_rect = self.viewport().rect()
            if not vp_rect.contains(view_pos):
                view_pos = vp_rect.center()
        except Exception:
            pass
        scene_pos = self.mapToScene(view_pos)

        # Construir catálogo con metadatos (nombre, fn, categoría, tags, descripción, icono)
        items = []
        def add_item(name, fn, category="All", tags=None, description="", icon_name=None):
            items.append({
                "name": name,
                "fn": fn,
                "category": category,
                "tags": tags or [],
                "description": description or name,
                "icon_name": icon_name,
            })

        # Base de blueprint
        add_item("Event", lambda pos: self.add_node_with_ports(
            title="Event", x=pos.x(), y=pos.y(), node_type="event",
            inputs=[], outputs=[{"name": "exec", "kind": "exec"}], content="// Evento base"),
            category="Blueprint", tags=["exec","flow"], description="Nodo de evento base", icon_name="media-playback-start")
        add_item("Branch", lambda pos: self.add_node_with_ports(
            title="Branch", x=pos.x(), y=pos.y(), node_type="branch",
            inputs=[{"name": "exec", "kind": "exec"}, {"name": "condition"}],
            outputs=[{"name": "true", "kind": "exec"}, {"name": "false", "kind": "exec"}], content="// Branch"),
            category="Blueprint", tags=["exec","flow"], description="Condicional tipo Branch", icon_name="view-sort-ascending")
        add_item("Sequence", lambda pos: self.add_node_with_ports(
            title="Sequence", x=pos.x(), y=pos.y(), node_type="sequence",
            inputs=[{"name": "exec", "kind": "exec"}],
            outputs=[{"name": "A", "kind": "exec"}, {"name": "B", "kind": "exec"}], content="// Sequence"),
            category="Blueprint", tags=["exec","flow"], description="Secuencia de ejecución", icon_name="view-list")
        add_item("Print", lambda pos: self.add_node_with_ports(
            title="Print", x=pos.x(), y=pos.y(), node_type="print",
            inputs=[{"name": "exec", "kind": "exec"}, {"name": "input"}],
            outputs=[{"name": "then", "kind": "exec"}], content="print(input)"),
            category="Blueprint", tags=["text","exec"], description="Imprime y continúa", icon_name="document-print")

        # Nodos básicos
        add_item("Input", lambda pos: self.add_node_with_ports(
            title="Input", x=pos.x(), y=pos.y(), node_type="input",
            inputs=[], outputs=[{"name": "output", "kind": "data"}], content=""),
            category="Input", tags=["io","data"], description="Fuente de datos", icon_name="go-up")
        # Estilo tipo Blender/Houdini: Group Input/Output
        add_item("Group Input", lambda pos: self.add_node_with_ports(
            title="Group Input", x=pos.x(), y=pos.y(), node_type="group_input",
            inputs=[], outputs=[{"name": "Geometry", "kind": "data"}], content=""),
            category="IO", tags=["group","io"], description="Entrada del grupo (Geometry)", icon_name="go-up")
        add_item("Process", lambda pos: self.add_node_with_ports(
            title="Process", x=pos.x(), y=pos.y(), node_type="process",
            inputs=[{"name": "input", "kind": "data"}], outputs=[{"name": "output", "kind": "data"}], content="input"),
            category="Process", tags=["process"], description="Transforma datos", icon_name="applications-system")
        # Nodo Terminal: agrega múltiples entradas y muestra el Total
        add_item("Terminal", lambda pos: self.add_node_with_ports(
            title="Terminal", x=pos.x(), y=pos.y(), node_type="terminal",
            inputs=[{"name": "input", "kind": "data", "multi": True}], outputs=[{"name": "output", "kind": "data"}], content=""),
            category="IO", tags=["aggregate","total"], description="Nodo Terminal que agrega outputs en Total", icon_name="system-run")
        add_item("Variable", lambda pos: self.add_node_with_ports(
            title="Variable", x=pos.x(), y=pos.y(), node_type="variable",
            inputs=[{"name": "set"}], outputs=[{"name": "output"}], content=""),
            category="Input", tags=["data"], description="Nodo de variable", icon_name="tag")
        add_item("Generic", lambda pos: self.add_node_with_ports(
            title="Node", x=pos.x(), y=pos.y(), node_type="generic",
            inputs=["input"], outputs=["output"], content=""),
            category="Process", tags=["generic"], description="Nodo genérico", icon_name="applications-other")

        # Catálogo C++ como entradas planas
        try:
            catalog = get_cpp_catalog() or {}
        except Exception:
            catalog = {}
        for category, cat_items in catalog.items():
            for it in cat_items:
                label = f"C++: {it.get('name', '(símbolo)')}"
                def make_cpp_fn(item):
                    return lambda pos: self._create_node_from_cpp_catalog_item(item, pos)
                add_item(label, make_cpp_fn(it), category="C++", tags=[category], description=f"Símbolo C++: {label}", icon_name="applications-development")
        # Acciones múltiples C++
        add_item("C++: Definiciones múltiples", lambda pos: self._wrap_multi_cpp(self._generate_cpp_definitions_nodes, pos), category="C++", tags=["bulk"], description="Genera varios nodos de definiciones")
        add_item("C++: Clases múltiples", lambda pos: self._wrap_multi_cpp(self._generate_cpp_classes_nodes, pos), category="C++", tags=["bulk"], description="Genera varios nodos de clases")

        # Catálogo Python como entradas planas
        try:
            py_catalog = get_python_catalog() or {}
        except Exception:
            py_catalog = {}
        for category, cat_items in py_catalog.items():
            for it in cat_items:
                py_label = f"Python: {it.get('name', '(snippet)')}"
                def make_py_fn(item):
                    return lambda pos: self._create_node_from_python_catalog_item(item, pos)
                add_item(py_label, make_py_fn(it), category="Python", tags=[category], description=it.get("description", py_label), icon_name="application-python")

        # Diálogo estilizado tipo popup (cierra al hacer clic fuera)
        dlg = QDialog(self)
        dlg.setWindowTitle("Crear nodo")
        try:
            dlg.setAttribute(Qt.WA_TranslucentBackground, True)
            dlg.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        except Exception:
            pass

        # Contenedor con estilo (bordes redondeados + sombra)
        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        container = QWidget(dlg)
        container.setObjectName("tabPaletteContainer")
        container.setStyleSheet(
            "#tabPaletteContainer {"
            "  background-color: #0f1116;"
            "  border: 1px solid #2a2e36;"
            "  border-radius: 10px;"
            "}"
        )
        shadow = QGraphicsDropShadowEffect(container)
        try:
            shadow.setBlurRadius(24)
            shadow.setOffset(0, 6)
            shadow.setColor(QColor(0, 0, 0, 120))
            container.setGraphicsEffect(shadow)
        except Exception:
            pass
        root.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl = QLabel("Escribe para filtrar…")
        try:
            lbl.setStyleSheet("color: #a1a7b3; font-size: 11px;")
        except Exception:
            pass
        layout.addWidget(lbl)

        # Chips de categoría
        chip_bar = QHBoxLayout()
        chip_bar.setSpacing(6)
        chip_names = ["All", "Input", "Process", "IO", "Visual", "Blueprint", "Python", "C++", "Recientes", "Favoritos"]
        chip_buttons = {}
        for name in chip_names:
            b = QPushButton(name)
            b.setCheckable(True)
            b.setStyleSheet(
                "QPushButton {"
                "  background-color: #111827; border: 1px solid #253044;"
                "  border-radius: 10px; padding: 4px 8px; color: #cbd5e1; font-size: 11px;"
                "}"
                "QPushButton:hover { background-color: #172036; }"
                "QPushButton:checked { background-color: #2563eb; color: #ffffff; border-color: #2563eb; }"
            )
            # Icono distintivo para Python y C++ (SVG propio para nitidez y estabilidad)
            try:
                if name == "Python":
                    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                    svg_py = os.path.join(root, "assets", "icons", "python.svg")
                    icon = QIcon(svg_py) if os.path.exists(svg_py) else QIcon.fromTheme("application-python")
                    if not icon or icon.isNull():
                        icon = make_hat_icon_neon(size=24, color="lime")
                    b.setIcon(icon)
                elif name == "C++":
                    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                    svg_cpp = os.path.join(root, "assets", "icons", "cplusplus.svg")
                    icon = QIcon(svg_cpp) if os.path.exists(svg_cpp) else QIcon.fromTheme("applications-development")
                    b.setIcon(icon if icon and not icon.isNull() else QIcon())
            except Exception:
                pass
            chip_bar.addWidget(b)
            chip_buttons[name] = b
        layout.addLayout(chip_bar)

        edit = QLineEdit()
        edit.setPlaceholderText("Buscar nodo (R)")
        try:
            edit.setStyleSheet(
                "QLineEdit {"
                "  background-color: #141820;"
                "  border: 1px solid #2f3640;"
                "  border-radius: 8px;"
                "  padding: 8px;"
                "  color: #e6edf3;"
                "  selection-background-color: #2563eb;"
                "  selection-color: #ffffff;"
                "}"
                "QLineEdit:focus {"
                "  border-color: #3b82f6;"
                "  background-color: #0f172a;"
                "}"
            )
        except Exception:
            pass
        layout.addWidget(edit)

        listw = QListWidget()
        try:
            listw.setStyleSheet(
                "QListWidget {"
                "  background-color: #0b0e14;"
                "  border: 1px solid #22262e;"
                "  border-radius: 8px;"
                "  padding: 4px;"
                "  color: #e5e7eb;"
                "}"
                "QListWidget::item {"
                "  padding: 6px 8px;"
                "}"
                "QListWidget::item:selected {"
                "  background-color: #2563eb;"
                "  color: #ffffff;"
                "  border-radius: 6px;"
                "}"
                "QListWidget::item:hover {"
                "  background-color: #1f2937;"
                "  color: #e5e7eb;"
                "}"
            )
        except Exception:
            pass
        listw.setMinimumWidth(280)
        listw.setMinimumHeight(220)
        layout.addWidget(listw)

        # Helpers de ranking y filtro
        def _recent_rank(name: str) -> int:
            try:
                idx = self._palette_recent.index(name)
                return max(0, len(self._palette_recent) - idx)
            except Exception:
                return 0

        def _score(query: str, item: dict):
            name = item.get("name", "").lower()
            if not query:
                return (_recent_rank(item.get("name", "")) + self._palette_usage_counts.get(item.get("name", ""), 0), 1.0)
            q = query.lower()
            exact = 1 if name == q else 0
            starts = 1 if name.startswith(q) else 0
            contains = 1 if q in name else 0
            fuzzy = 0.0
            try:
                fuzzy = difflib.SequenceMatcher(None, q, name).ratio()
            except Exception:
                fuzzy = 0.0
            return (
                exact * 100 + starts * 50 + contains * 25 + _recent_rank(item.get("name", "")) * 10 + self._palette_usage_counts.get(item.get("name", ""), 0),
                fuzzy
            )

        # Estado de acción al aceptar
        action_mode = {"mode": "insert"}

        # Debounce de búsqueda
        search_timer = QTimer(dlg)
        search_timer.setSingleShot(True)
        search_timer.setInterval(150)

        # Población inicial con filtros y ranking
        def populate(filter_text: str = ""):
            listw.clear()
            f = (filter_text or "").strip()
            cat = getattr(self, "_palette_category_filter", "All") or "All"

            # Tags en query: palabras que comienzan por '#'
            tag_filters = []
            if f:
                try:
                    tag_filters = [t[1:].lower() for t in f.split() if t.startswith('#') and len(t) > 1]
                except Exception:
                    tag_filters = []
            plain_query = ' '.join([w for w in f.split() if not w.startswith('#')])

            # Filtrar por categoría o recientes/favoritos
            candidates = []
            if cat == "Recientes":
                recent_set = set(self._palette_recent or [])
                for it in items:
                    if it.get("name") in recent_set:
                        candidates.append(it)
            elif cat == "Favoritos":
                fav_set = set(self._palette_favorites or [])
                for it in items:
                    if it.get("name") in fav_set:
                        candidates.append(it)
            elif cat == "All":
                candidates = list(items)
            else:
                internal_cat = "Blueprint" if cat == "Visual" else cat
                candidates = [it for it in items if it.get("category") == internal_cat]

            # Filtrar por tags (AND)
            if tag_filters:
                candidates = [it for it in candidates if set(tag_filters).issubset(set([t.lower() for t in it.get("tags", [])]))]

            # Ordenar por score (coincidencia → recientes → uso → fuzzy)
            scored = []
            for it in candidates:
                s1, s2 = _score(plain_query, it)
                scored.append((s1, s2, it))
            scored.sort(key=lambda t: (t[0], t[1]), reverse=True)

            # Poblar lista con iconos y tooltips
            for _, _, it in scored:
                name = it.get("name", "")
                qicon = None
                try:
                    icon_name = it.get("icon_name")
                    if icon_name:
                        # Usar SVG propio para Python para máxima nitidez
                        if icon_name == "application-python":
                            root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                            svg_py = os.path.join(root, "assets", "icons", "python.svg")
                            if os.path.exists(svg_py):
                                qicon = QIcon(svg_py)
                            else:
                                qicon = QIcon.fromTheme(icon_name)
                            if not qicon or qicon.isNull():
                                try:
                                    qicon = make_hat_icon_neon(size=24, color="lime")
                                except Exception:
                                    qicon = QIcon()
                        else:
                            qicon = QIcon.fromTheme(icon_name)
                except Exception:
                    qicon = None
                is_fav = name in (self._palette_favorites or [])
                display_name = ("★ " + name) if is_fav else name
                itemw = QListWidgetItem(qicon if qicon else QIcon(), display_name)
                usage = self._palette_usage_counts.get(name, 0)
                recent_lbl = " • reciente" if name in (self._palette_recent or []) else ""
                fav_lbl = " • favorito" if is_fav else ""
                itemw.setToolTip(f"{it.get('description', name)}{recent_lbl}{fav_lbl} • usados: {usage}")
                itemw.setData(Qt.UserRole, it)
                listw.addItem(itemw)

        populate()

        def _update_usage_and_recents(name: str):
            try:
                self._palette_usage_counts[name] = int(self._palette_usage_counts.get(name, 0)) + 1
            except Exception:
                pass
            try:
                # Mover a la cabecera de "recientes"
                self._palette_recent = [n for n in (self._palette_recent or []) if n != name]
                self._palette_recent.insert(0, name)
                # Limitar longitud
                if len(self._palette_recent) > 24:
                    self._palette_recent = self._palette_recent[:24]
            except Exception:
                pass

        def _create_selected(auto_connect: bool = False, open_inspector: bool = False, keep_open: bool = False):
            it = listw.currentItem() or (listw.item(0) if listw.count() > 0 else None)
            if it is None:
                if not keep_open:
                    dlg.reject()
                return
            meta = it.data(Qt.UserRole) or {}
            fn = meta.get("fn")
            name = meta.get("name", "")
            # Recordar selección previa para autoconexión
            selected_before = [n for n in self._scene.selectedItems() if isinstance(n, NodeItem)]
            try:
                node = fn(scene_pos) if callable(fn) else None
            except Exception:
                node = None
                logger.exception("No se pudo crear nodo desde paleta TAB")
            if node:
                try:
                    for sel in self._scene.selectedItems():
                        sel.setSelected(False)
                    node.setSelected(True)
                    self.centerOn(node)
                except Exception:
                    pass
                _update_usage_and_recents(name)
                # Autoconectar con un único nodo previamente seleccionado
                if auto_connect:
                    try:
                        if len(selected_before) == 1:
                            src = selected_before[0]
                            # Elegir puertos razonables
                            start_item = src
                            end_item = node
                            start_port = (src.output_ports[0]['name'] if getattr(src, 'output_ports', None) else 'output')
                            end_port = (node.input_ports[0]['name'] if getattr(node, 'input_ports', None) else 'input')
                            # Si el seleccionado no tiene OUT pero sí IN, invertir dirección
                            if not getattr(src, 'output_ports', None):
                                start_item = node
                                end_item = src
                                start_port = (node.output_ports[0]['name'] if getattr(node, 'output_ports', None) else 'output')
                                end_port = (src.input_ports[0]['name'] if getattr(src, 'input_ports', None) else 'input')
                            self.add_connection(start_item, end_item, start_port=start_port, end_port=end_port)
                    except Exception:
                        logger.exception("Autoconexión fallida tras inserción")
                # Abrir inspector si se solicita
                if open_inspector:
                    try:
                        self.editNodeRequested.emit(node)
                    except Exception:
                        pass
            if not keep_open:
                dlg.accept()

        def accept_selected():
            _create_selected(auto_connect=False, open_inspector=False, keep_open=False)

        # Búsqueda con debounce y typeahead
        def _on_text_changed(_t):
            try:
                search_timer.stop()
            except Exception:
                pass
            try:
                search_timer.start()
            except Exception:
                pass
        def _on_search_timeout():
            try:
                populate(edit.text())
            except Exception:
                pass
        edit.textChanged.connect(_on_text_changed)
        search_timer.timeout.connect(_on_search_timeout)
        edit.returnPressed.connect(accept_selected)
        # Navegación desde el campo de búsqueda
        orig_edit_kp = edit.keyPressEvent
        def _edit_keypress(e):
            try:
                if e.key() == Qt.Key_Down:
                    row = max(0, listw.currentRow())
                    listw.setCurrentRow(min(row + 1, listw.count() - 1))
                    e.accept(); return
                if e.key() == Qt.Key_Up:
                    row = max(0, listw.currentRow())
                    listw.setCurrentRow(max(row - 1, 0))
                    e.accept(); return
                if e.key() in (Qt.Key_Escape,):
                    dlg.close(); e.accept(); return
                if e.key() in (Qt.Key_Return, Qt.Key_Enter):
                    accept_selected(); e.accept(); return
                if e.key() == Qt.Key_Tab:
                    _create_selected(auto_connect=False, open_inspector=False, keep_open=True); e.accept(); return
                if (e.modifiers() & Qt.ControlModifier) and e.key() in (Qt.Key_Return, Qt.Key_Enter):
                    _create_selected(auto_connect=True, open_inspector=False, keep_open=False); e.accept(); return
                if (e.modifiers() & Qt.ShiftModifier) and e.key() in (Qt.Key_Return, Qt.Key_Enter):
                    _create_selected(auto_connect=False, open_inspector=True, keep_open=False); e.accept(); return
            except Exception:
                pass
            orig_edit_kp(e)
        edit.keyPressEvent = _edit_keypress

        # Cerrar también con ESC desde la lista
        orig_list_kp = listw.keyPressEvent
        def _list_keypress(e):
            try:
                if e.key() == Qt.Key_Escape:
                    dlg.close(); e.accept(); return
                if e.key() == Qt.Key_F:
                    # Alternar favorito del elemento actual
                    it = listw.currentItem()
                    if it is not None:
                        meta = it.data(Qt.UserRole) or {}
                        name = meta.get('name', '')
                        try:
                            favs = set(self._palette_favorites or [])
                            if name in favs:
                                favs.remove(name)
                            else:
                                favs.add(name)
                            self._palette_favorites = list(favs)
                        except Exception:
                            pass
                        # Refrescar manteniendo el texto
                        populate(edit.text())
                    e.accept(); return
                if e.key() == Qt.Key_Tab:
                    _create_selected(auto_connect=False, open_inspector=False, keep_open=True); e.accept(); return
                if (e.modifiers() & Qt.ControlModifier) and e.key() in (Qt.Key_Return, Qt.Key_Enter):
                    _create_selected(auto_connect=True, open_inspector=False, keep_open=False); e.accept(); return
                if (e.modifiers() & Qt.ShiftModifier) and e.key() in (Qt.Key_Return, Qt.Key_Enter):
                    _create_selected(auto_connect=False, open_inspector=True, keep_open=False); e.accept(); return
                if e.key() in (Qt.Key_Return, Qt.Key_Enter):
                    accept_selected(); e.accept(); return
            except Exception:
                pass
            orig_list_kp(e)
        listw.keyPressEvent = _list_keypress
        listw.itemActivated.connect(lambda *_: accept_selected())

        # Comportamiento de chips de categoría
        def _set_active_chip(cat_name: str):
            try:
                for nm, btn in chip_buttons.items():
                    btn.setChecked(nm == cat_name)
                setattr(self, '_palette_category_filter', cat_name)
            except Exception:
                setattr(self, '_palette_category_filter', cat_name)
            populate(edit.text())
        # Seleccionar "All" por defecto
        try:
            chip_buttons.get("All").setChecked(True)
        except Exception:
            pass
        for nm, btn in chip_buttons.items():
            try:
                btn.clicked.connect(lambda checked=False, name=nm: _set_active_chip(name))
            except Exception:
                pass

        # Posicionar cerca del cursor
        try:
            dlg.move(QCursor.pos())
        except Exception:
            pass
        edit.setFocus()
        # Mostrar como popup (se cierra al hacer clic fuera)
        try:
            dlg.show()
        except Exception:
            # Fallback a exec si show falla (sin cierre automático)
            dlg.exec()

    def _wrap_multi_cpp(self, fn, pos: QPointF):
        try:
            created = fn(var_node=None, scene_pos=pos)
            if created:
                for it in self._scene.selectedItems():
                    it.setSelected(False)
                created[0].setSelected(True)
                self.centerOn(created[0])
            return None
        except Exception:
            logger.exception("No se pudieron generar nodos C++ múltiples desde paleta TAB")
            return None

    # Controles de zoom para la barra inferior del editor de nodos
    def zoom_in(self):
        try:
            factor = 1.25
            new_zoom = self._zoom + 1
            if -40 <= new_zoom <= 80:
                self._zoom = new_zoom
                self.scale(factor, factor)
                try:
                    scale_x = float(self.transform().m11())
                    self.zoomChanged.emit(scale_x)
                    try:
                        for it in self._scene.items():
                            if isinstance(it, NodeItem):
                                it.apply_adaptive_text_behavior(scale_x)
                    except Exception:
                        pass
                except Exception:
                    pass
                try:
                    self._update_minimap_fit()
                except Exception:
                    pass
        except Exception:
            pass

    def zoom_out(self):
        try:
            factor = 1 / 1.25
            new_zoom = self._zoom - 1
            if -40 <= new_zoom <= 80:
                self._zoom = new_zoom
                self.scale(factor, factor)
                try:
                    scale_x = float(self.transform().m11())
                    self.zoomChanged.emit(scale_x)
                    try:
                        for it in self._scene.items():
                            if isinstance(it, NodeItem):
                                it.apply_adaptive_text_behavior(scale_x)
                    except Exception:
                        pass
                except Exception:
                    pass
                try:
                    self._update_minimap_fit()
                except Exception:
                    pass
        except Exception:
            pass

    def reset_zoom(self):
        try:
            self.resetTransform()
            self._zoom = 0
            try:
                scale_x = float(self.transform().m11())
                self.zoomChanged.emit(scale_x)
                try:
                    for it in self._scene.items():
                        if isinstance(it, NodeItem):
                            it.apply_adaptive_text_behavior(scale_x)
                except Exception:
                    pass
            except Exception:
                pass
            try:
                self._update_minimap_fit()
            except Exception:
                pass
        except Exception:
            pass

    # Layout rápido horizontal de la selección actual
    def auto_layout_selection(self):
        try:
            selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
            if not selected_nodes:
                return
            # Ordenar por X y colocar en fila con espaciado
            selected_nodes.sort(key=lambda n: float(n.x()))
            start_x = float(selected_nodes[0].x())
            start_y = float(selected_nodes[0].y())
            spacing = 220.0
            for i, n in enumerate(selected_nodes):
                try:
                    r = n.rect()
                    spacing = max(spacing, r.width() + 140.0)
                except Exception:
                    pass
                n.setPos(start_x + i * spacing, start_y)
            try:
                self.update_all_connections()
            except Exception:
                pass
        except Exception:
            pass

    def delete_selected_nodes(self):
        try:
            selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
            for n in selected_nodes:
                self.remove_node(n)
            try:
                self.update_all_connections()
            except Exception:
                pass
        except Exception:
            pass

    def toggle_minimap(self):
        try:
            self._minimap_enabled = not bool(getattr(self, '_minimap_enabled', False))
            self.viewport().update()
        except Exception:
            pass

    def _show_tab_menu(self):
        menu = QMenu(self)
        # Menú: acciones de generación múltiple al nivel superior
        menu.addAction("Definiciones múltiples (C++)")
        menu.addAction("Clases múltiples (C++)")
        menu.addSeparator()

        # Submenú Catálogo C++ con categorías y elementos
        try:
            catalog = get_cpp_catalog()
        except Exception:
            catalog = {}
        if catalog:
            cat_menu = QMenu("Catálogo C++", menu)
            # Mapear QAction -> item para resolución directa
            action_item_map = {}
            for category, items in catalog.items():
                sub = QMenu(category, cat_menu)
                for it in items:
                    text = it.get("name", "(símbolo)")
                    act = sub.addAction(text)
                    # Guardar referencia al item
                    action_item_map[id(act)] = it
                cat_menu.addMenu(sub)
            menu.addMenu(cat_menu)
            menu._catalog_action_item_map = action_item_map  # adjuntar tabla para su uso tras exec

        # Submenú Blueprint Base (nodos prefabricados)
        bp_menu = QMenu("Blueprint Base", menu)
        bp_menu.addAction("Event")
        bp_menu.addAction("Branch")
        bp_menu.addAction("Sequence")
        bp_menu.addAction("Print")
        menu.addMenu(bp_menu)
        
        chosen = menu.exec(QCursor.pos())
        if chosen is None:
            return

        # Posición robusta en escena: si el cursor global no cae sobre la vista,
        # usar el centro del viewport para evitar crear nodos fuera de pantalla.
        view_pos = self.mapFromGlobal(QCursor.pos())
        try:
            vp_rect = self.viewport().rect()
            if not vp_rect.contains(view_pos):
                view_pos = vp_rect.center()
        except Exception:
            pass
        scene_pos = self.mapToScene(view_pos)
        
        action_text = chosen.text()

        # Si la acción proviene del Catálogo C++, crear nodo desde el item
        try:
            action_item_map = getattr(menu, "_catalog_action_item_map", {})
            if action_item_map and id(chosen) in action_item_map:
                item = action_item_map[id(chosen)]
                node = self._create_node_from_cpp_catalog_item(item, scene_pos)
                if node:
                    self._apply_node_effects(node)
                    node.setSelected(True)
                    self.centerOn(node)
                return
        except Exception:
            pass
        
        if action_text == "Definiciones múltiples (C++)":
            try:
                created = self._generate_cpp_definitions_nodes(var_node=None, scene_pos=scene_pos)
                if created:
                    for it in self._scene.selectedItems():
                        it.setSelected(False)
                    created[0].setSelected(True)
                    self.centerOn(created[0])
            except Exception:
                logger.exception("No se pudieron generar nodos de definiciones C++ múltiples desde TAB")
            node = None
        elif action_text == "Clases múltiples (C++)":
            try:
                created = self._generate_cpp_classes_nodes(var_node=None, scene_pos=scene_pos)
                if created:
                    for it in self._scene.selectedItems():
                        it.setSelected(False)
                        created[0].setSelected(True)
                        self.centerOn(created[0])
            except Exception:
                logger.exception("No se pudieron generar nodos de clases C++ múltiples desde TAB")
            node = None
        elif action_text == "Event":
            try:
                node = self.add_node_with_ports(
                    title="Event",
                    x=float(scene_pos.x()),
                    y=float(scene_pos.y()),
                    node_type="event",
                    inputs=[],
                    outputs=[{"name": "exec", "kind": "exec"}],
                    content="// Evento base: dispara ejecución"
                )
                if node:
                    for it in self._scene.selectedItems():
                        it.setSelected(False)
                    node.setSelected(True)
                    self.centerOn(node)
            except Exception:
                logger.exception("No se pudo crear nodo Event")
        elif action_text == "Branch":
            try:
                node = self.add_node_with_ports(
                    title="Branch",
                    x=float(scene_pos.x()),
                    y=float(scene_pos.y()),
                    node_type="branch",
                    inputs=[{"name": "exec", "kind": "exec"}, {"name": "condition"}],
                    outputs=[{"name": "true", "kind": "exec"}, {"name": "false", "kind": "exec"}],
                    content="// Branch: enruta ejecución según condición"
                )
                if node:
                    for it in self._scene.selectedItems():
                        it.setSelected(False)
                    node.setSelected(True)
                    self.centerOn(node)
            except Exception:
                logger.exception("No se pudo crear nodo Branch")
        elif action_text == "Sequence":
            try:
                node = self.add_node_with_ports(
                    title="Sequence",
                    x=float(scene_pos.x()),
                    y=float(scene_pos.y()),
                    node_type="sequence",
                    inputs=[{"name": "exec", "kind": "exec"}],
                    outputs=[{"name": "A", "kind": "exec"}, {"name": "B", "kind": "exec"}],
                    content="// Sequence: dispara salidas en orden"
                )
                if node:
                    for it in self._scene.selectedItems():
                        it.setSelected(False)
                    node.setSelected(True)
                    self.centerOn(node)
            except Exception:
                logger.exception("No se pudo crear nodo Sequence")
        elif action_text == "Print":
            try:
                node = self.add_node_with_ports(
                    title="Print",
                    x=float(scene_pos.x()),
                    y=float(scene_pos.y()),
                    node_type="print",
                    inputs=[{"name": "exec", "kind": "exec"}, {"name": "input"}],
                    outputs=[{"name": "then", "kind": "exec"}],
                    content="print(input)"
                )
                if node:
                    for it in self._scene.selectedItems():
                        it.setSelected(False)
                    node.setSelected(True)
                    self.centerOn(node)
            except Exception:
                logger.exception("No se pudo crear nodo Print")
        # Opción de enrutamiento eliminada del TAB a petición del usuario
        else:
            return
            
        if node:
            self._apply_node_effects(node)
            node.setSelected(True)
            self.centerOn(node)

    def _create_node_from_cpp_catalog_item(self, item: dict, scene_pos: QPointF):
        """Crea un nodo genérico con contenido mínimo basado en una entrada del catálogo C++."""
        try:
            name = item.get("name", "Símbolo C++")
            header = item.get("header", "")
            desc = item.get("description", "")
            kind = item.get("type", "type")
            inputs = item.get("inputs", [])
            outputs = item.get("outputs", [])

            include = (f"#include {header}\n" if header else "")
            # Encabezado dentro del área de edición de texto, no en el título
            banner = f"// Catálogo C++ — {name}\n"
            comment = f"// Descripción: {desc}\n" if desc else ""

            # Sugerencias de variables desde variable_library (lenguaje C++)
            try:
                variable_library.current_language = "cpp"
            except Exception:
                pass

            def _derive_type_key(symbol_name: str) -> str:
                s = (symbol_name or "").strip()
                # Mantener clave explícita para std::string si aparece
                if "std::string" in s:
                    return "std::string"
                # Quitar prefijos std:: y espacios de nombres
                s = s.replace("std::", "")
                if "::" in s:
                    s = s.split("::")[-1]
                # Quitar parámetros de plantilla <...>
                if "<" in s:
                    s = s.split("<")[0]
                return s or "string"

            base_key = _derive_type_key(name)
            suggestions = variable_library.get_type_suggestions(base_key) or []
            if not suggestions and kind in ("io", "filesystem", "regex", "random"):
                # Fallback a texto para IO/FS/Regex/Random
                suggestions = (
                    variable_library.get_type_suggestions("std::string")
                    or variable_library.get_type_suggestions("string")
                    or []
                )

            vars_block = ""
            if suggestions:
                vars_block = (
                    "\n// Variables sugeridas (" + base_key + "):\n// " + ", ".join(suggestions) + "\n"
                )

            # Plantilla según tipo
            code_body = ""
            if kind in ("type", "class"):
                code_body = f"{name} valor;\n"
            elif kind in ("function", "algorithm", "utility"):
                params = ", ".join(inputs) if inputs else "..."
                ret = outputs[0] if outputs else "void"
                code_body = (
                    f"// Retorno: {ret}\n"
                    f"// Ejemplo de llamada:\n"
                    f"{name}({params});\n"
                )
            elif kind in ("io", "pointer", "chrono", "thread", "filesystem", "regex", "random"):
                code_body = f"// Uso ejemplo para {name}\n"
                if "std::cout" in name:
                    code_body += "std::cout << \"Hola\" << std::endl;\n"
                elif "std::ifstream" in name:
                    code_body += "std::ifstream f(\"file.txt\");\n"
                elif "std::ofstream" in name:
                    code_body += "std::ofstream f(\"out.txt\");\n"
                elif "std::thread" in name:
                    code_body += "std::thread t([]{}); t.join();\n"
            else:
                code_body = f"// Ejemplo para {name}\n"

            cpp_code = banner + comment + include + "\n" + code_body + vars_block

            # Título genérico para consistencia y mejores guías
            node = self.add_node(title="Código C++", x=float(scene_pos.x()), y=float(scene_pos.y()), node_type="generic", content=cpp_code)
            # Identidad visual del nodo C++ (icono y lenguaje)
            try:
                node._language = "cpp"
                root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                svg_cpp = os.path.join(root, "assets", "icons", "cplusplus.svg")
                icon = QIcon(svg_cpp) if os.path.exists(svg_cpp) else QIcon.fromTheme("applications-development")
                node.header_icon = icon if icon and not icon.isNull() else QIcon()
            except Exception:
                pass
            return node
        except Exception:
            logger.exception("Error creando nodo desde catálogo C++")
            return None

    def _create_node_from_python_catalog_item(self, item: dict, scene_pos: QPointF):
        """Crea un nodo Python desde el catálogo, respetando su node_type."""
        try:
            name = item.get("name", "Snippet Python")
            template = item.get("template", "output = input")
            desc = item.get("description", "Python")
            ntype = str(item.get("node_type", "process")).lower()

            # Asegurar sugerencias de variables para Python en otros flujos
            try:
                variable_library.current_language = "python"
            except Exception:
                pass

            banner = f"# Catálogo Python — {name}\n# {desc}\n\n"
            content = banner + template

            if ntype == "input":
                node = self.add_node_with_ports(
                    title="Input",
                    x=float(scene_pos.x()),
                    y=float(scene_pos.y()),
                    node_type="input",
                    inputs=[],
                    outputs=[{"name": "output", "kind": "data"}],
                    content=content,
                )
            elif ntype == "output":
                # Remapeado: crear nodo Terminal en lugar de Output
                node = self.add_node_with_ports(
                    title="Terminal",
                    x=float(scene_pos.x()),
                    y=float(scene_pos.y()),
                    node_type="terminal",
                    inputs=[{"name": "input", "kind": "data"}],
                    outputs=[{"name": "output", "kind": "data"}],
                    content=content,
                )
            else:
                node = self.add_node_with_ports(
                    title="Process",
                    x=float(scene_pos.x()),
                    y=float(scene_pos.y()),
                    node_type="process",
                    inputs=[{"name": "input", "kind": "data"}],
                    outputs=[{"name": "output", "kind": "data"}],
                    content=content,
                )
            # Identidad visual del nodo Python (icono y lenguaje)
            try:
                node._language = "python"
                root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                svg_py = os.path.join(root, "assets", "icons", "python.svg")
                icon = QIcon(svg_py) if os.path.exists(svg_py) else QIcon.fromTheme("application-python")
                if not icon or icon.isNull():
                    icon = make_hat_icon_neon(size=24, color="lime")
                node.header_icon = icon
            except Exception:
                pass
            return node
        except Exception:
            logger.exception("Error creando nodo desde catálogo Python")
            return None
    def _generate_single_classic_variable(self, language_key: str, scene_pos):
        """Genera un único VariableNode con el primer tipo/nombre sugerido del lenguaje."""
        try:
            variable_library.current_language = language_key
        except Exception:
            pass
        try:
            suggestions = variable_library.get_all_suggestions()
        except Exception:
            suggestions = {}
        if not suggestions:
            return None
        # Tomar el primer tipo y el primer nombre
        data_type = next(iter(suggestions.keys()))
        names = suggestions.get(data_type, {}).get("suggestions", [])
        var_name = names[0] if names else data_type
        node = VariableNode(title="Variable", x=float(scene_pos.x()), y=float(scene_pos.y()), node_type="variable")
        try:
            node.set_variable_info({"language": language_key})
        except Exception:
            node._language = language_key
        try:
            node._on_variable_selected(data_type, var_name)
        except Exception:
            try:
                node.set_variable_info({"type": data_type, "name": var_name})
            except Exception:
                pass
        try:
            self._scene.addItem(node)
        except Exception:
            pass
        return node

    def _populate_selected_variables_from_library(self, language_key: str):
        """Rellena nodos VariableNode ya definidos (seleccionados) con tipos/nombres de la biblioteca del lenguaje."""
        try:
            variable_library.current_language = language_key
        except Exception:
            pass
        try:
            suggestions = variable_library.get_all_suggestions()
        except Exception:
            suggestions = {}
        if not suggestions:
            return

        # Preparar un ciclo de tipos y nombres
        type_items = list(suggestions.items())  # [(tipo, info)]
        if not type_items:
            return

        selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, VariableNode)]
        if not selected_nodes:
            return

        idx = 0
        for node in selected_nodes:
            try:
                data_type, info = type_items[idx % len(type_items)]
                names = info.get("suggestions", [])
                var_name = names[0] if names else data_type
                # Establecer lenguaje y aplicar tipo/nombre
                try:
                    node.set_variable_info({"language": language_key})
                except Exception:
                    node._language = language_key
                try:
                    node._on_variable_selected(data_type, var_name)
                except Exception:
                    node.set_variable_info({"type": data_type, "name": var_name})
            except Exception:
                pass
            idx += 1

    def _generate_classic_variables(self, language_key: str, scene_pos):
        """Genera automáticamente VariableNodes para los tipos clásicos del lenguaje.
        Usa la biblioteca de variables para tomar sugerencias de nombre por cada tipo.
        """
        try:
            # Ajustar lenguaje actual para que las sugerencias coincidan
            variable_library.current_language = language_key
        except Exception:
            pass

        try:
            all_suggestions = variable_library.get_all_suggestions()  # {tipo: {suggestions, icon, description}}
        except Exception:
            all_suggestions = {}

        # Si no hay sugerencias, nada que hacer
        if not all_suggestions:
            return

        # Layout en cuadrícula alrededor de la posición del cursor
        base_x = float(scene_pos.x())
        base_y = float(scene_pos.y())
        dx = 240.0
        dy = 150.0
        col_count = 3

        created_nodes = []
        index = 0
        for data_type, info in all_suggestions.items():
            try:
                names = info.get("suggestions", [])
                if not names:
                    # Si no hay nombres sugeridos, saltar este tipo
                    continue
                var_name = str(names[0])
            except Exception:
                continue

            # Calcular posición en cuadrícula
            row = index // col_count
            col = index % col_count
            x = base_x + col * dx
            y = base_y + row * dy

            # Crear nodo de variable y fijar lenguaje
            node = VariableNode(title="Variable", x=x, y=y, node_type="variable")
            try:
                node.set_variable_info({"language": language_key})
            except Exception:
                try:
                    node._language = language_key
                except Exception:
                    pass

            # Aplicar tipo/nombre y valor por defecto reutilizando la lógica interna
            try:
                node._on_variable_selected(data_type, var_name)
            except Exception:
                # Fallback mínimo si la llamada falla
                try:
                    node.set_variable_info({"type": data_type, "name": var_name})
                except Exception:
                    pass

            # Añadir a la escena y aplicar efectos
            try:
                self._scene.addItem(node)
                self._apply_node_effects(node)
                created_nodes.append(node)
            except Exception:
                pass

            index += 1

        # Seleccionar el primero y centrar la vista para feedback visual
        if created_nodes:
            try:
                for it in self._scene.selectedItems():
                    it.setSelected(False)
            except Exception:
                pass
            try:
                first = created_nodes[0]
                first.setSelected(True)
                self.centerOn(first)
            except Exception:
                pass

    def _show_selection_menu(self, view_pos):
        """Muestra un menú contextual con acciones sobre la selección actual."""
        menu = QMenu(self)
        # Detectar si hay un único nodo seleccionado y si es VariableNode
        selected_nodes_ctx = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
        single_selected = selected_nodes_ctx[0] if len(selected_nodes_ctx) == 1 else None
        is_variable_selected = isinstance(single_selected, VariableNode) if single_selected else False
        menu.addAction("Eliminar seleccionados")
        menu.addAction("Duplicar seleccionados")
        menu.addSeparator()
        menu.addAction("Combinar nodos (grupo)")
        # Renombrar título del nodo seleccionado
        menu.addAction("Renombrar título…")
        # Gestión versátil de puertos
        menu.addAction("Añadir puerto IN…")
        menu.addAction("Añadir puerto OUT…")
        menu.addAction("Renombrar puerto…")
        menu.addSeparator()
        # Acción para alternar snapshot en nodo seleccionado
        if single_selected is not None:
            try:
                if getattr(single_selected, 'is_snapshot', False):
                    menu.addAction("Quitar snapshot")
                else:
                    menu.addAction("Marcar como snapshot")
            except Exception:
                pass
        # Toggle Blender‑like: mutear nodo para hacer passthrough
        if single_selected is not None:
            try:
                if getattr(single_selected, 'muted', False):
                    menu.addAction("Quitar mute")
                else:
                    menu.addAction("Mutear nodo")
            except Exception:
                pass
        # Acciones específicas para Terminal: abrir terminal externo con perfil
        if single_selected is not None and str(getattr(single_selected, 'node_type', '')).lower() == 'terminal':
            try:
                term_menu = QMenu("Abrir terminal externo", menu)
                term_menu.addAction("PowerShell")
                term_menu.addAction("Command Prompt")
                # Detectar Git Bash
                try:
                    import shutil as _sh
                    if _sh.which("bash") or _sh.which("git-bash") or _sh.which("git.exe"):
                        term_menu.addAction("Git Bash")
                except Exception:
                    pass
                # Windows Terminal (wt.exe)
                try:
                    import shutil as _sh
                    if _sh.which("wt"):
                        term_menu.addAction("Windows Terminal")
                except Exception:
                    pass
                menu.addMenu(term_menu)
                # Acción directa: abrir por defecto (PowerShell)
                menu.addAction("Abrir en PowerShell externo")
            except Exception:
                pass
        # Toggle para reenviar salida desde nodos Output
        if single_selected is not None and str(getattr(single_selected, 'node_type', '')).lower() == 'output':
            try:
                if getattr(single_selected, 'forward_output', False):
                    menu.addAction("Desactivar salida en Output")
                else:
                    menu.addAction("Activar salida en Output")
            except Exception:
                pass
        # Crear snapshot combinado desde selección
        if selected_nodes_ctx:
            menu.addAction("Snapshot combinado desde selección")
        menu.addSeparator()
        # Acciones de tamaño y autoajuste
        menu.addAction("Ajustar a contenido (seleccionados)")
        menu.addAction("Expandir tamaño ×1.25 (seleccionados)")
        menu.addAction("Reducir tamaño ×0.8 (seleccionados)")
        menu.addSeparator()
        menu.addAction("Crear nodo (genérico)")
        menu.addAction("Crear nodo (Combine)")
        # Nodo especial: Monitor (Output) para reflejar valores en Preview
        # Eliminado: acciones para crear nodos Output y Output Global
        # Terminal: agrega todos los outputs en Total y utilidades de limpieza
        menu.addAction("Crear nodo Terminal (Total)")
        menu.addAction("Limpiar Outputs (global)")
        menu.addAction("Eliminar nodos Output")
        # Utilidades
        menu.addSeparator()
        menu.addAction("Limpiar caché…")
        # Submenú: perfiles de terminal embebido (solo si hay un nodo Terminal seleccionado)
        try:
            node = single_selected
            if node is not None and str(getattr(node, 'node_type', '')).lower() == 'terminal':
                menu.addSeparator()
                term_menu = QMenu("Abrir terminal embebido (perfil)", menu)
                term_menu.addAction("Abrir terminal embebido (PowerShell)")
                term_menu.addAction("Abrir terminal embebido (Git Bash)")
                term_menu.addAction("Abrir terminal embebido (Command Prompt)")
                menu.addMenu(term_menu)
                menu.addAction("Cerrar terminal embebido")
        except Exception:
            pass
        # Acción contextual: generar nodo de programación C++ desde variable cuando el lenguaje activo es C++
        if is_variable_selected:
            try:
                lang = getattr(variable_library, 'current_language', 'python')
            except Exception:
                lang = 'python'
            if str(lang).lower() == 'cpp':
                menu.addSeparator()
                menu.addAction("Generar nodo C++ (plantilla)")
                multi_menu = QMenu("Generar nodos múltiples (C++)", menu)
                multi_menu.addAction("Definiciones múltiples (C++)")
                multi_menu.addAction("Clases múltiples (C++)")
                menu.addMenu(multi_menu)

        chosen = menu.exec(self.mapToGlobal(view_pos))
        if chosen is None:
            return

        text = chosen.text()
        try:
            if text == "Eliminar seleccionados":
                for it in self._scene.selectedItems()[:]:
                    if isinstance(it, NodeItem):
                        self.remove_node(it)
            elif text == "Duplicar seleccionados":
                self._duplicate_selected_nodes()
            elif text == "Combinar nodos (grupo)":
                self._combine_selected_nodes()
            elif text == "Renombrar título…":
                # Tomar el primer nodo seleccionado y pedir nuevo título
                selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
                if not selected_nodes:
                    return
                node = selected_nodes[0]
                current = node.title or ""
                try:
                    new_text, ok = QInputDialog.getText(self, "Renombrar nodo", "Nuevo título:", text=current)
                except Exception:
                    logger.exception("Error mostrando diálogo de renombrado")
                    ok = False
                    new_text = current
                if ok:
                    try:
                        node.title = (new_text or "").strip()
                        # Actualizar visualmente el título (manteniendo estilo comentario si aplica)
                        if hasattr(node, "_refresh_title_text"):
                            node._refresh_title_text()
                        node.update()
                    except Exception:
                        logger.exception("Error aplicando nuevo título al nodo")
            elif text == "Añadir puerto IN…":
                selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
                if not selected_nodes:
                    return
                node = selected_nodes[0]
                try:
                    name, ok = QInputDialog.getText(self, "Añadir puerto de entrada", "Nombre del puerto:", text="input")
                except Exception:
                    logger.exception("Error mostrando diálogo de añadir puerto IN")
                    ok = False
                    name = ""
                if ok and name:
                    try:
                        node.add_input_port((name or "").strip())
                    except Exception:
                        logger.exception("Error añadiendo puerto IN")
            elif text == "Añadir puerto OUT…":
                selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
                if not selected_nodes:
                    return
                node = selected_nodes[0]
                try:
                    name, ok = QInputDialog.getText(self, "Añadir puerto de salida", "Nombre del puerto:", text="output")
                except Exception:
                    logger.exception("Error mostrando diálogo de añadir puerto OUT")
                    ok = False
                    name = ""
                if ok and name:
                    try:
                        node.add_output_port((name or "").strip())
                    except Exception:
                        logger.exception("Error añadiendo puerto OUT")
            elif text == "Marcar como snapshot":
                try:
                    node = single_selected
                    if node is not None:
                        # Si es nodo de salida, congelar el contenido con las entradas actuales antes de marcar
                        try:
                            if str(getattr(node, 'node_type', '')).lower() == 'output':
                                vals = []
                                for v in (getattr(node, 'input_values', {}) or {}).values():
                                    if v is None:
                                        continue
                                    if isinstance(v, list):
                                        for sv in v:
                                            if sv is not None:
                                                vals.append(str(sv))
                                    else:
                                        vals.append(str(v))
                                if vals:
                                    combined = "\n".join(vals)
                                    if hasattr(node, 'update_from_text'):
                                        node.update_from_text(combined)
                        except Exception:
                            pass
                        setattr(node, 'is_snapshot', True)
                        if hasattr(node, '_refresh_title_text'):
                            node._refresh_title_text()
                        self.evaluate_graph()
                except Exception:
                    logger.exception("Error marcando nodo como snapshot")
            elif text == "Quitar snapshot":
                try:
                    node = single_selected
                    if node is not None:
                        setattr(node, 'is_snapshot', False)
                        if hasattr(node, '_refresh_title_text'):
                            node._refresh_title_text()
                        self.evaluate_graph()
                except Exception:
                    logger.exception("Error quitando snapshot del nodo")
            elif text == "Activar salida en Output":
                try:
                    node = single_selected
                    if node is not None and str(getattr(node, 'node_type', '')).lower() == 'output':
                        setattr(node, 'forward_output', True)
                        self.evaluate_graph()
                except Exception:
                    logger.exception("Error activando salida en Output")
            elif text == "Desactivar salida en Output":
                try:
                    node = single_selected
                    if node is not None and str(getattr(node, 'node_type', '')).lower() == 'output':
                        setattr(node, 'forward_output', False)
                        self.evaluate_graph()
                except Exception:
                    logger.exception("Error desactivando salida en Output")
            elif text == "Snapshot combinado desde selección":
                try:
                    selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
                    if not selected_nodes:
                        return
                    # Recoger contenido visible de cada nodo seleccionado
                    parts = []
                    for n in selected_nodes:
                        try:
                            txt = ""
                            if hasattr(n, 'to_plain_text'):
                                txt = n.to_plain_text() or ""
                            else:
                                txt = getattr(n, 'content', '') or ''
                            if txt:
                                parts.append(str(txt))
                        except Exception:
                            pass
                    combined = "\n".join(parts)
                    # Posicionar el nuevo nodo cerca del centro de la selección
                    try:
                        xs = [n.pos().x() for n in selected_nodes]
                        ys = [n.pos().y() for n in selected_nodes]
                        cx = sum(xs) / max(1, len(xs))
                        cy = sum(ys) / max(1, len(ys))
                    except Exception:
                        scene_pos = self.mapToScene(view_pos)
                        cx, cy = scene_pos.x(), scene_pos.y()
                    node = self.add_node_with_ports(title="Terminal Combined", x=cx + 40, y=cy + 40, node_type="terminal", inputs=["input"], outputs=["output"], content=combined)
                    if node is not None:
                        try:
                            setattr(node, 'is_snapshot', True)
                            if hasattr(node, '_refresh_title_text'):
                                node._refresh_title_text()
                            node.setSelected(True)
                            self.centerOn(node)
                        except Exception:
                            pass
                        self.evaluate_graph()
                except Exception:
                    logger.exception("Error creando snapshot combinado desde selección")
            elif text == "Renombrar puerto…":
                selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
                if not selected_nodes:
                    return
                node = selected_nodes[0]
                try:
                    # Seleccionar tipo de puerto
                    port_type, ok_type = QInputDialog.getItem(self, "Tipo de puerto", "Selecciona:", ["input", "output"], 0, False)
                except Exception:
                    logger.exception("Error mostrando diálogo de tipo de puerto")
                    ok_type = False
                    port_type = "input"
                if not ok_type:
                    return
                ports = node.input_ports if port_type == "input" else node.output_ports
                names = [p.get("name", "") for p in ports] or ["(sin puertos)"]
                try:
                    old_name, ok_old = QInputDialog.getItem(self, "Puerto a renombrar", "Selecciona puerto:", names, 0, False)
                except Exception:
                    logger.exception("Error mostrando lista de puertos")
                    ok_old = False
                    old_name = ""
                if not ok_old or old_name == "(sin puertos)":
                    return
                try:
                    new_name, ok_new = QInputDialog.getText(self, "Nuevo nombre", "Nombre del puerto:", text=old_name)
                except Exception:
                    logger.exception("Error mostrando diálogo de nuevo nombre")
                    ok_new = False
                    new_name = old_name
                if ok_new and new_name:
                    try:
                        node.rename_port(old_name, new_name, port_type)
                    except Exception:
                        logger.exception("Error renombrando puerto")
            elif text == "Ajustar a contenido (seleccionados)":
                selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
                for n in selected_nodes:
                    try:
                        if hasattr(n, '_auto_resize_to_content'):
                            n._auto_resize_to_content()
                    except Exception:
                        pass
                try:
                    self.update_all_connections()
                except Exception:
                    pass
            elif text == "Mutear nodo":
                selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
                for n in selected_nodes:
                    try:
                        setattr(n, 'muted', True)
                    except Exception:
                        pass
                try:
                    self.evaluate_graph()
                except Exception:
                    pass
            elif text == "Quitar mute":
                selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
                for n in selected_nodes:
                    try:
                        setattr(n, 'muted', False)
                    except Exception:
                        pass
                try:
                    self.evaluate_graph()
                except Exception:
                    pass
            elif text == "Expandir tamaño ×1.25 (seleccionados)":
                selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
                for n in selected_nodes:
                    try:
                        r = n.rect()
                        new_w = max(getattr(n, '_min_w', 140), r.width() * 1.25)
                        new_h = max(getattr(n, '_min_h', 80), r.height() * 1.25)
                        n.prepareGeometryChange()
                        n.setRect(0, 0, new_w, new_h)
                        n._update_title_pos()
                        n._update_content_layout()
                    except Exception:
                        pass
                try:
                    self.update_all_connections()
                except Exception:
                    pass
            elif text == "Reducir tamaño ×0.8 (seleccionados)":
                selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
                for n in selected_nodes:
                    try:
                        r = n.rect()
                        new_w = max(getattr(n, '_min_w', 140), r.width() * 0.8)
                        new_h = max(getattr(n, '_min_h', 80), r.height() * 0.8)
                        n.prepareGeometryChange()
                        n.setRect(0, 0, new_w, new_h)
                        n._update_title_pos()
                        n._update_content_layout()
                    except Exception:
                        pass
                try:
                    self.update_all_connections()
                except Exception:
                    pass
            elif text == "Abrir en PowerShell externo":
                try:
                    # Abrir PowerShell con el directorio actual del proceso
                    cwd = os.getcwd()
                    import subprocess, shutil
                    ps_cmd = shutil.which("powershell") or shutil.which("powershell.exe") or "powershell"
                    subprocess.Popen([ps_cmd, "-NoExit", "-NoLogo"], cwd=cwd)
                except Exception:
                    logger.exception("No se pudo abrir PowerShell externo")
            elif text in ("Abrir terminal embebido (PowerShell)", "Abrir terminal embebido (Command Prompt)", "Abrir terminal embebido (Git Bash)"):
                try:
                    node = single_selected
                    if node is None or str(getattr(node, 'node_type', '')).lower() != 'terminal':
                        return
                    profile_map = {
                        "Abrir terminal embebido (PowerShell)": "PowerShell",
                        "Abrir terminal embebido (Command Prompt)": "Command Prompt",
                        "Abrir terminal embebido (Git Bash)": "Git Bash",
                    }
                    profile = profile_map.get(text, "PowerShell")
                    if hasattr(node, 'open_embedded_terminal'):
                        node.open_embedded_terminal(profile)
                except Exception:
                    logger.exception("No se pudo abrir terminal embebido")
            elif text == "Cerrar terminal embebido":
                try:
                    node = single_selected
                    if node is None or str(getattr(node, 'node_type', '')).lower() != 'terminal':
                        return
                    if hasattr(node, 'close_embedded_terminal'):
                        node.close_embedded_terminal()
                except Exception:
                    logger.exception("No se pudo cerrar terminal embebido")
            elif text == "Crear nodo (genérico)":
                scene_pos = self.mapToScene(view_pos)
                node = self.add_node("Node", scene_pos.x(), scene_pos.y(), node_type="generic")
                if node:
                    node.setSelected(True)
                    self.centerOn(node)
            elif text == "Crear nodo (Combine)":
                scene_pos = self.mapToScene(view_pos)
                node = self.add_node_with_ports("Combine", scene_pos.x(), scene_pos.y(), node_type="combine", inputs=["input"], outputs=["output"], content="")
                if node:
                    node.setSelected(True)
                    self.centerOn(node)
            elif text == "Crear nodo Terminal (Total)":
                scene_pos = self.mapToScene(view_pos)
                # Fuentes: igual que Output Global, pero creando un nodo 'terminal'
                sources = []
                try:
                    selected_nodes_ctx = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
                    if selected_nodes_ctx:
                        sources = [n for n in selected_nodes_ctx if str(getattr(n, 'node_type', '')).lower() not in ('output','group_output')]
                    else:
                        sources = [it for it in self._scene.items() if isinstance(it, NodeItem) and str(getattr(it, 'node_type', '')).lower() not in ('output','group_output')]
                except Exception:
                    sources = []
                in_names = [f"in{i+1}" for i in range(len(sources))] or ["input"]
                term = self.add_node_with_ports("Terminal", scene_pos.x(), scene_pos.y(), node_type="terminal", inputs=in_names, outputs=["output"], content="")
                if term:
                    for idx, src in enumerate(sources):
                        try:
                            start_port = (src.output_ports[0]['name'] if getattr(src, 'output_ports', None) else 'output')
                            end_port = (term.input_ports[idx]['name'] if idx < len(term.input_ports) else 'input')
                            self.add_connection(src, term, start_port=start_port, end_port=end_port)
                        except Exception:
                            pass
                    try:
                        term.setSelected(True)
                        self.centerOn(term)
                    except Exception:
                        pass
                    # Evaluar para reflejar Total inmediatamente
                    try:
                        self.evaluate_graph()
                    except Exception:
                        pass
            elif text == "Limpiar Outputs (global)":
                try:
                    nodes = [it for it in self._scene.items() if isinstance(it, NodeItem)]
                except Exception:
                    nodes = []
                # Resetear valores de salida y entradas; limpiar contenido en outputs
                for n in nodes:
                    try:
                        n.output_values = {}
                        n._output_cache = {}
                        n._last_inputs_hash = None
                        # Reiniciar inputs para siguiente evaluación
                        n.input_values = {}
                        # Limpiar contenido visible de nodos Output/Group Output
                        if str(getattr(n, 'node_type', '')).lower() in ('output','group_output'):
                            if hasattr(n, 'update_from_text'):
                                n.update_from_text("")
                        n.is_dirty = True
                    except Exception:
                        pass
                # Reevaluar y notificar
                try:
                    self.evaluate_graph()
                except Exception:
                    pass
            elif text == "Eliminar nodos Output":
                try:
                    to_remove = [it for it in self._scene.items() if isinstance(it, NodeItem) and str(getattr(it, 'node_type', '')).lower() in ('output','group_output')]
                except Exception:
                    to_remove = []
                for it in to_remove:
                    try:
                        self.remove_node(it, record_undo=True)
                    except Exception:
                        pass
                try:
                    self.evaluate_graph()
                except Exception:
                    pass
            elif text == "Limpiar caché…":
                try:
                    self._clear_node_cache()
                except Exception:
                    logger.exception("No se pudo limpiar caché desde menú")
            elif text == "Generar nodo C++ (plantilla)":
                # Crear un nodo semántico basado en C++ y la variable seleccionada
                var_node_list = [it for it in self._scene.selectedItems() if isinstance(it, VariableNode)]
                if not var_node_list:
                    return
                var_node = var_node_list[0]
                # Obtener nombre y tipo de la variable
                var_name = getattr(var_node, 'variable_name', '') or getattr(var_node, 'title', 'variable')
                var_type = getattr(var_node, 'variable_type', 'int')
                semantic_meta = None
                # Si es vector, ofrecer métodos frecuentes y producir meta
                try:
                    from ..library.cpp_node_defs import std_vector_method, list_vector_methods
                except Exception:
                    std_vector_method = None
                    list_vector_methods = lambda: []

                if var_type in ("vector", "std::vector", "std::vector<T>") and std_vector_method:
                    try:
                        methods = list_vector_methods()
                        method, ok = QInputDialog.getItem(self, "Método de std::vector", "Selecciona:", methods, 0, False)
                    except Exception:
                        logger.exception("Error mostrando lista de métodos de vector")
                        ok = False
                        method = "push_back"
                    if ok:
                        T = "T"
                        semantic_meta = std_vector_method(method, T)

                # Posicionar cerca del nodo variable
                pos = var_node.scenePos()
                new_x, new_y = pos.x() + 220.0, pos.y()

                if isinstance(semantic_meta, dict):
                    title = f"{semantic_meta.get('namespace', 'std')}::{semantic_meta.get('connects_to', ['std::vector<T>'])[0].split('::')[-1]}::{semantic_meta.get('name', 'func')}"
                    # Contenido mínimo informativo; el ensamblador se encargará de includes y orden
                    content = f"// {semantic_meta.get('header')}\n// {title}\n// returns: {semantic_meta.get('returns')}"
                    func_node = self.add_node(title=title, x=new_x, y=new_y, node_type="process", content=content)
                    try:
                        setattr(func_node, 'semantic_meta', semantic_meta)
                    except Exception:
                        pass
                    # Autoconectar variable -> función
                    try:
                        self.add_connection(var_node, func_node, start_port="output", end_port="input")
                    except Exception:
                        logger.exception("No se pudo autoconectar variable -> función")
                else:
                    # Fallback: snippet genérico
                    cpp_code = (
                        "#include <iostream>\n"
                        "int main() {\n"
                        f"    {var_type} {var_name};\n"
                        f"    std::cout << {var_name} << std::endl;\n"
                        "    return 0;\n"
                        "}\n"
                    )
                    code_node = self.add_node(title="Código C++", x=new_x, y=new_y, node_type="generic", content=cpp_code)
                    try:
                        self.add_connection(var_node, code_node, start_port="output", end_port="input")
                    except Exception:
                        pass
            elif text == "Definiciones múltiples (C++)":
                var_node_list = [it for it in self._scene.selectedItems() if isinstance(it, VariableNode)]
                if not var_node_list:
                    return
                var_node = var_node_list[0]
                try:
                    created = self._generate_cpp_definitions_nodes(var_node=var_node, scene_pos=None)
                    if created:
                        for it in self._scene.selectedItems():
                            it.setSelected(False)
                        created[0].setSelected(True)
                        self.centerOn(created[0])
                except Exception:
                    logger.exception("No se pudieron generar nodos de definiciones C++ múltiples desde menú de selección")
            elif text == "Clases múltiples (C++)":
                var_node_list = [it for it in self._scene.selectedItems() if isinstance(it, VariableNode)]
                if not var_node_list:
                    return
                var_node = var_node_list[0]
                try:
                    created = self._generate_cpp_classes_nodes(var_node=var_node, scene_pos=None)
                    if created:
                        for it in self._scene.selectedItems():
                            it.setSelected(False)
                        created[0].setSelected(True)
                        self.centerOn(created[0])
                except Exception:
                    logger.exception("No se pudieron generar nodos de clases C++ múltiples desde menú de selección")
        except Exception:
            logger.exception("Error procesando acción de menú contextual")

    def _combine_selected_nodes(self):
        """Crea un contenedor de grupo que agrupa y mueve los nodos seleccionados."""
        selected_nodes = [it for it in self._scene.selectedItems() if isinstance(it, NodeItem)]
        if len(selected_nodes) < 2:
            return
        try:
            group = GroupItem(selected_nodes, title="Grupo")
            self._scene.addItem(group)
            # Elevar grupo detrás de nodos pero visible
            group.setZValue(min([n.zValue() for n in selected_nodes]) - 0.5)
            # Deseleccionar nodos y seleccionar grupo
            for n in selected_nodes:
                n.setSelected(False)
            group.setSelected(True)
        except Exception:
            logger.exception("No se pudo crear grupo de nodos")

    def _duplicate_selected_nodes(self):
        """Duplica nodos seleccionados conservando puertos, título, tipo y estilo."""
        try:
            offset = QPoint(20, 20)
            for it in self._scene.selectedItems():
                if isinstance(it, NodeItem):
                    pos = it.pos() + QPointF(offset)
                    new_node = NodeItem(title=it.title, x=pos.x(), y=pos.y(), node_type=it.node_type)
                    # Copiar contenido si existe
                    new_node.content = getattr(it, 'content', '')
                    # Copiar puertos
                    try:
                        in_names = [p["name"] for p in it.input_ports]
                        out_names = [p["name"] for p in it.output_ports]
                        if hasattr(new_node, 'set_ports'):
                            new_node.set_ports(in_names or ["input"], out_names or ["output"])
                    except Exception:
                        pass
                    self._scene.addItem(new_node)
                    self._apply_node_effects(new_node)
                    new_node.setSelected(True)
        except Exception:
            logger.exception("Error duplicando nodos seleccionados")

    def _quick_duplicate_node(self, node: NodeItem):
        """Duplica un nodo en el lugar con un pequeño offset y lo selecciona."""
        try:
            pos = node.pos() + QPointF(QPoint(20, 20))
            new_node = NodeItem(title=node.title, x=pos.x(), y=pos.y(), node_type=node.node_type)
            # Copiar contenido si existe
            new_node.content = getattr(node, 'content', '')
            # Copiar puertos
            try:
                in_names = [p["name"] for p in node.input_ports]
                out_names = [p["name"] for p in node.output_ports]
                if hasattr(new_node, 'set_ports'):
                    new_node.set_ports(in_names or ["input"], out_names or ["output"])
            except Exception:
                pass
            self._scene.addItem(new_node)
            self._apply_node_effects(new_node)
            # Seleccionar el duplicado y notificar cambio de selección
            try:
                for it in self._scene.selectedItems():
                    it.setSelected(False)
            except Exception:
                pass
            new_node.setSelected(True)
            self._on_scene_selection_changed()
            # Actualizar runtime por cambio estructural
            try:
                if hasattr(self, '_runtime') and self._runtime:
                    self._runtime.rebuild_from_view()
                    self._runtime.evaluate_all()
            except Exception:
                pass
        except Exception:
            logger.exception("Error en duplicación rápida de nodo")

    # ----------------------
    # Cache helpers
    # ----------------------
    def _get_cache_dir(self) -> str:
        try:
            base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
            if not base:
                base = os.path.join(os.getcwd(), "cache")
            cache_dir = os.path.join(base, "Codemind-Visual", "NodeCache")
            os.makedirs(cache_dir, exist_ok=True)
            return cache_dir
        except Exception:
            fallback = os.path.join(os.getcwd(), "cache")
            os.makedirs(fallback, exist_ok=True)
            return fallback

    def _clear_node_cache(self) -> None:
        """Vacía el directorio de caché y limpia referencias en nodos."""
        try:
            cache_dir = self._get_cache_dir()
            if os.path.isdir(cache_dir):
                for entry in os.listdir(cache_dir):
                    p = os.path.join(cache_dir, entry)
                    try:
                        if os.path.isdir(p):
                            shutil.rmtree(p, ignore_errors=True)
                        else:
                            os.remove(p)
                    except Exception:
                        pass
            # Limpiar cache_path en nodos
            for it in self._scene.items():
                if isinstance(it, NodeItem):
                    try:
                        if hasattr(it, 'cache_path'):
                            setattr(it, 'cache_path', None)
                    except Exception:
                        pass
            logger.info("Caché limpiado: %s", cache_dir)
        except Exception:
            logger.exception("Error limpiando caché")

    # ----------------------
    # Node helpers
    # ----------------------
    def add_node(self, title="Node", x=0.0, y=0.0, node_type="generic", content=""):
        """Añade un nodo a la escena."""
        if str(node_type).lower() == 'variable':
            node = VariableNode(title=title, x=float(x), y=float(y), node_type='variable')
        else:
            node = NodeItem(title=title, x=float(x), y=float(y), node_type=node_type)
        # Aplicar contenido al área de texto del nodo inmediatamente
        try:
            if content:
                node.update_from_text(content)
            else:
                node.content = content
        except Exception:
            node.content = content
        self._scene.addItem(node)
        self._apply_node_effects(node)
        try:
            if isinstance(node, VariableNode):
                node.variable_changed.connect(lambda *_: self.evaluate_graph())
        except Exception:
            pass
        self.evaluate_graph()
        return node

    def add_reroute_node(self, x=0.0, y=0.0):
        """Crea un nodo mínimo para organizar cables (1 IN, 1 OUT)."""
        try:
            node = NodeItem(title="", x=float(x), y=float(y), w=24, h=24, node_type="reroute")
            try:
                node.title_h = 0
            except Exception:
                pass
            try:
                node.set_ports(["in"], ["out"])
            except Exception:
                pass
            self._scene.addItem(node)
            self._apply_node_effects(node)
            self.evaluate_graph()
            return node
        except Exception:
            logger.exception("No se pudo crear nodo de enrutamiento")
            return None


    def add_node_with_ports(self, title="Node", x=0.0, y=0.0, node_type="generic", inputs=None, outputs=None, content="", record_undo: bool = True):
        """Añade un nodo con puertos personalizados (listas de nombres)."""
        if str(node_type).lower() == 'variable':
            node = VariableNode(title=title, x=float(x), y=float(y), node_type='variable')
        else:
            node = NodeItem(title=title, x=float(x), y=float(y), node_type=node_type)
        # Aplicar contenido al área de texto del nodo inmediatamente
        try:
            if content:
                node.update_from_text(content)
            else:
                node.content = content
        except Exception:
            node.content = content
        try:
            # Respetar listas vacías explícitas; sólo usar por defecto si es None
            in_ports = inputs if inputs is not None else ["input"]
            out_ports = outputs if outputs is not None else ["output"]
            node.set_ports(in_ports, out_ports)
        except Exception:
            pass
        self._scene.addItem(node)
        self._apply_node_effects(node)
        # Tag de familia Python para los nodos de muestra "Input", "Process" y "Output"
        try:
            if str(title) in ("Input", "Process", "Output"):
                node._language = "python"
        except Exception:
            pass
        try:
            if isinstance(node, VariableNode):
                node.variable_changed.connect(lambda *_: self.evaluate_graph())
        except Exception:
            pass
        self.evaluate_graph()
        # Registrar undo/redo de creación
        try:
            if record_undo and not self._suspend_undo:
                in_ports = [dict(p) for p in (inputs if inputs is not None else (node.input_ports or []))]
                out_ports = [dict(p) for p in (outputs if outputs is not None else (node.output_ports or []))]
                self._push_undo(
                    undo_fn=lambda: self.remove_node(node, record_undo=False),
                    redo_fn=lambda: self.add_node_with_ports(title=title, x=x, y=y, node_type=node_type, inputs=in_ports, outputs=out_ports, content=getattr(node, 'content', ''), record_undo=False),
                    label="add_node"
                )
        except Exception:
            pass
        return node

    def _generate_cpp_code_nodes(self, var_node=None, scene_pos=None):
        """Genera múltiples nodos de código C++ y los distribuye en una cuadrícula.

        - Si se proporciona `var_node`, usa su nombre y tipo para personalizar los snippets.
        - Si no, usa `scene_pos` y valores por defecto.
        Devuelve la lista de nodos creados.
        """
        created_nodes = []
        # Base de posicionamiento
        if var_node is not None:
            base = var_node.scenePos()
            var_name = getattr(var_node, 'variable_name', '') or getattr(var_node, 'title', 'variable')
            var_type = getattr(var_node, 'variable_type', 'int')
        else:
            base = scene_pos or QPointF(100.0, 100.0)
            var_name = 'variable'
            var_type = 'int'

        # Defaults por tipo para inicialización
        default_val = '0'
        if str(var_type).lower() in ('float', 'double'):
            default_val = '0.0'
        elif str(var_type).lower() in ('string', 'std::string'):
            var_type = 'std::string'
            default_val = '""'

        # Plantillas de código
        snippets = [
            {
                'title': 'C++: Declaración',
                'code': (
                    "#include <iostream>\n"
                    "#include <string>\n\n"
                    "int main() {\n"
                    f"    {var_type} {var_name} = {default_val};\n"
                    "    // TODO: lógica\n"
                    "    return 0;\n"
                    "}\n"
                )
            },
            {
                'title': 'C++: Imprimir',
                'code': (
                    "#include <iostream>\n"
                    "#include <string>\n\n"
                    "int main() {\n"
                    f"    {var_type} {var_name};\n"
                    f"    std::cout << \"Valor: \" << {var_name} << std::endl;\n"
                    "    return 0;\n"
                    "}\n"
                )
            },
            {
                'title': 'C++: Función',
                'code': (
                    "#include <iostream>\n"
                    "#include <string>\n\n"
                    f"{var_type} procesar({var_type} v) {{\n"
                    "    // TODO: transforma v\n"
                    "    return v;\n"
                    "}\n\n"
                    "int main() {\n"
                    f"    {var_type} {var_name} = {default_val};\n"
                    f"    auto r = procesar({var_name});\n"
                    "    std::cout << r << std::endl;\n"
                    "    return 0;\n"
                    "}\n"
                )
            },
            {
                'title': 'C++: Bucle for',
                'code': (
                    "#include <iostream>\n\n"
                    "int main() {\n"
                    f"    int {var_name} = 0;\n"
                    "    for (int i = 0; i < 10; ++i) {\n"
                    f"        {var_name} += i;\n"
                    "    }\n"
                    f"    std::cout << {var_name} << std::endl;\n"
                    "    return 0;\n"
                    "}\n"
                )
            },
            {
                'title': 'C++: Clase',
                'code': (
                    "#include <iostream>\n"
                    "#include <string>\n\n"
                    "class MiClase {\n"
                    f"public: {var_type} {var_name};\n"
                    "    MiClase() : \n"
                    f"        {var_name}({default_val}) {{}}\n"
                    "};\n\n"
                    "int main() {\n"
                    "    MiClase obj;\n"
                    "    // TODO: usa obj\n"
                    "    return 0;\n"
                    "}\n"
                )
            }
        ]

        # Distribución en cuadrícula
        dx, dy = 240.0, 140.0
        base_x, base_y = base.x() + 220.0, base.y() - 70.0
        cols = 2

        for idx, sn in enumerate(snippets):
            col = idx % cols
            row = idx // cols
            x = base_x + col * dx
            y = base_y + row * dy
            try:
                node = self.add_node(title=sn['title'], x=x, y=y, node_type='generic', content=sn['code'])
                created_nodes.append(node)
                # Conectar variable a entrada del nodo si existe
                if var_node is not None:
                    try:
                        self.add_connection(var_node, node, start_port='output', end_port='input')
                    except Exception:
                        pass
            except Exception:
                logger.exception("No se pudo crear nodo de código C++")

        # Activar edición en el primero para experiencia Blueprint
        if created_nodes:
            try:
                created_nodes[0].set_editing(True)
            except Exception:
                pass

        return created_nodes

    def _generate_cpp_definitions_nodes(self, var_node=None, scene_pos=None):
        """Genera múltiples nodos con definiciones C++ (variables, funciones, constantes).

        - Si `var_node` existe, usa su nombre y tipo.
        - Si no, usa defaults y `scene_pos`.
        """
        created_nodes = []
        if var_node is not None:
            base = var_node.scenePos()
            var_name = getattr(var_node, 'variable_name', '') or getattr(var_node, 'title', 'variable')
            var_type = getattr(var_node, 'variable_type', 'int')
        else:
            base = scene_pos or QPointF(100.0, 100.0)
            var_name = 'variable'
            var_type = 'int'

        default_val = '0'
        if str(var_type).lower() in ('float', 'double'):
            default_val = '0.0'
        elif str(var_type).lower() in ('string', 'std::string'):
            var_type = 'std::string'
            default_val = '""'

        # Generación al estilo clásico: pares Header/Source por variante
        pairs = []

        # 1) Variable extern: <var_name>.h / <var_name>.cpp
        header_var = (
            "#pragma once\n" +
            ("#include <string>\n" if var_type == 'std::string' else "") +
            f"extern {var_type} {var_name};\n"
        )
        source_var = (
            f"#include \"{var_name}.h\"\n"
            f"{var_type} {var_name} = {default_val};\n"
        )
        pairs.append({
            'header': {'title': f"C++: {var_name}.h", 'code': header_var},
            'source': {'title': f"C++: {var_name}.cpp", 'code': source_var}
        })

        # 2) Función procesar: procesar.h / procesar.cpp
        header_proc = (
            "#pragma once\n" +
            ("#include <string>\n" if var_type == 'std::string' else "") +
            f"{var_type} procesar({var_type} v);\n"
        )
        source_proc = (
            "#include \"procesar.h\"\n"
            f"{var_type} procesar({var_type} v) {{\n"
            "    return v;\n"
            "}}\n"
        )
        pairs.append({
            'header': {'title': "C++: procesar.h", 'code': header_proc},
            'source': {'title': "C++: procesar.cpp", 'code': source_proc}
        })

        # 3) Constantes y enum: config.h / config.cpp
        header_cfg = (
            "#pragma once\n"
            "enum class Estado { Inicio, Proceso, Fin };\n"
            "constexpr int MAX_ITEMS = 10;\n"
        )
        source_cfg = (
            "#include \"config.h\"\n"
            "Estado estado_inicial() { return Estado::Inicio; }\n"
        )
        pairs.append({
            'header': {'title': "C++: config.h", 'code': header_cfg},
            'source': {'title': "C++: config.cpp", 'code': source_cfg}
        })

        # 4) struct Datos: datos.h / datos.cpp con ctor fuera de clase
        header_datos = (
            "#pragma once\n" +
            ("#include <string>\n" if var_type == 'std::string' else "") +
            "struct Datos {\n" +
            f"    {var_type} valor;\n" +
            "    Datos();\n" +
            "};\n"
        )
        source_datos = (
            "#include \"datos.h\"\n"
            f"Datos::Datos() : valor({default_val}) {{}}\n"
        )
        pairs.append({
            'header': {'title': "C++: datos.h", 'code': header_datos},
            'source': {'title': "C++: datos.cpp", 'code': source_datos}
        })

        # Distribuir en cuadrícula por pares (header izquierda, source derecha)
        dx, dy = 240.0, 140.0
        base_x, base_y = base.x() + 220.0, base.y() - 70.0
        for row, pair in enumerate(pairs):
            xh = base_x
            xs = base_x + dx
            y = base_y + row * dy
            try:
                hn = self.add_node(title=pair['header']['title'], x=xh, y=y, node_type='generic', content=pair['header']['code'])
                created_nodes.append(hn)
                sn = self.add_node(title=pair['source']['title'], x=xs, y=y, node_type='generic', content=pair['source']['code'])
                created_nodes.append(sn)
                if var_node is not None:
                    try:
                        self.add_connection(var_node, hn, start_port='output', end_port='input')
                        self.add_connection(var_node, sn, start_port='output', end_port='input')
                    except Exception:
                        pass
            except Exception:
                logger.exception("No se pudo crear pares header/source de definiciones C++")

        if created_nodes:
            try:
                created_nodes[0].set_editing(True)
            except Exception:
                pass
        return created_nodes

    def _generate_cpp_classes_nodes(self, var_node=None, scene_pos=None):
        """Genera múltiples nodos con clases C++ como pares Header/Source clásicos.

        - Básica: Basica.h / Basica.cpp
        - Con métodos: ConMetodos.h / ConMetodos.cpp
        - Herencia: Derivada.h / Derivada.cpp
        - Plantilla: Contenedor.hpp (header-only)
        """
        created_nodes = []
        if var_node is not None:
            base = var_node.scenePos()
            var_name = getattr(var_node, 'variable_name', '') or getattr(var_node, 'title', 'campo')
            var_type = getattr(var_node, 'variable_type', 'int')
        else:
            base = scene_pos or QPointF(100.0, 100.0)
            var_name = 'campo'
            var_type = 'int'

        default_val = '0'
        if str(var_type).lower() in ('float', 'double'):
            default_val = '0.0'
        elif str(var_type).lower() in ('string', 'std::string'):
            var_type = 'std::string'
            default_val = '""'
        # Pares header/source
        pairs = []

        # Básica
        header_basica = (
            "#pragma once\n" +
            ("#include <string>\n" if var_type == 'std::string' else "") +
            "class Basica {\n" +
            "public:\n" +
            f"    {var_type} {var_name};\n" +
            "    Basica();\n" +
            "    ~Basica();\n" +
            "};\n"
        )
        source_basica = (
            "#include \"Basica.h\"\n"
            f"Basica::Basica() : {var_name}({default_val}) {{}}\n"
            "Basica::~Basica() = default;\n"
        )
        pairs.append({
            'header': {'title': "C++: Basica.h", 'code': header_basica},
            'source': {'title': "C++: Basica.cpp", 'code': source_basica}
        })

        # Con métodos
        header_metodos = (
            "#pragma once\n" +
            ("#include <string>\n" if var_type == 'std::string' else "") +
            "class ConMetodos {\n" +
            f"    {var_type} {var_name};\n" +
            "public:\n" +
            "    ConMetodos();\n" +
            f"    void set({var_type} v);\n" +
            f"    {var_type} get() const;\n" +
            "};\n"
        )
        source_metodos = (
            "#include \"ConMetodos.h\"\n"
            f"ConMetodos::ConMetodos() : {var_name}({default_val}) {{}}\n"
            f"void ConMetodos::set({var_type} v) {{ {var_name} = v; }}\n"
            f"{var_type} ConMetodos::get() const {{ return {var_name}; }}\n"
        )
        pairs.append({
            'header': {'title': "C++: ConMetodos.h", 'code': header_metodos},
            'source': {'title': "C++: ConMetodos.cpp", 'code': source_metodos}
        })

        # Herencia (Base/Derivada)
        header_derivada = (
            "#pragma once\n"
            "class Base { public: virtual ~Base() = default; };\n"
            "class Derivada : public Base {\n"
            "public:\n"
            "    void run();\n"
            "};\n"
        )
        source_derivada = (
            "#include \"Derivada.h\"\n"
            "#include <iostream>\n"
            "void Derivada::run() { std::cout << \"ok\"; }\n"
        )
        pairs.append({
            'header': {'title': "C++: Derivada.h", 'code': header_derivada},
            'source': {'title': "C++: Derivada.cpp", 'code': source_derivada}
        })

        # Plantilla (header-only)
        header_contenedor = (
            "#pragma once\n"
            "template <typename T>\n"
            "class Contenedor {\n"
            "    T valor;\n"
            "public:\n"
            "    explicit Contenedor(T v) : valor(v) {}\n"
            "    T get() const { return valor; }\n"
            "};\n"
        )

        # Distribución en cuadrícula: pares lado a lado; plantilla solo header
        dx, dy = 240.0, 140.0
        base_x, base_y = base.x() + 220.0, base.y() - 70.0
        row = 0
        for pair in pairs:
            xh = base_x
            xs = base_x + dx
            y = base_y + row * dy
            try:
                hn = self.add_node(title=pair['header']['title'], x=xh, y=y, node_type='generic', content=pair['header']['code'])
                created_nodes.append(hn)
                sn = self.add_node(title=pair['source']['title'], x=xs, y=y, node_type='generic', content=pair['source']['code'])
                created_nodes.append(sn)
                if var_node is not None:
                    try:
                        self.add_connection(var_node, hn, start_port='output', end_port='input')
                        self.add_connection(var_node, sn, start_port='output', end_port='input')
                    except Exception:
                        pass
            except Exception:
                logger.exception("No se pudo crear pares header/source de clases C++")
            row += 1

        # Plantilla (header-only) en la siguiente fila, solo a la izquierda
        try:
            y = base_y + row * dy
            hn = self.add_node(title="C++: Contenedor.hpp", x=base_x, y=y, node_type='generic', content=header_contenedor)
            created_nodes.append(hn)
            if var_node is not None:
                try:
                    self.add_connection(var_node, hn, start_port='output', end_port='input')
                except Exception:
                    pass
        except Exception:
            logger.exception("No se pudo crear nodo de plantilla C++ (header-only)")

        if created_nodes:
            try:
                created_nodes[0].set_editing(True)
            except Exception:
                pass
        return created_nodes

    def clear_nodes(self):
        """Elimina todos los nodos y conexiones de la escena."""
        # Primero eliminar todas las conexiones
        self.clear_connections()
        
        # Luego eliminar todos los nodos
        for item in self._scene.items()[:]:
            if isinstance(item, NodeItem):
                try:
                    # Evitar errores si el item ya no pertenece a la escena
                    if item is not None and item.scene() is self._scene:
                        self._scene.removeItem(item)
                except Exception:
                    pass
    
    def remove_node(self, node_item, record_undo: bool = True):
        """Elimina un nodo específico y sus conexiones (con undo opcional)."""
        # Snapshot para undo
        created_ref = {"node": None}
        try:
            if record_undo and not self._suspend_undo:
                title = getattr(node_item, 'title', 'Node')
                node_type = getattr(node_item, 'node_type', 'generic')
                pos = node_item.scenePos()
                x, y = float(pos.x()), float(pos.y())
                content = getattr(node_item, 'content', '')
                inputs = [dict(p) for p in (getattr(node_item, 'input_ports', []) or [])]
                outputs = [dict(p) for p in (getattr(node_item, 'output_ports', []) or [])]
                # Capturar conexiones actuales del nodo
                conns = []
                for c in list(getattr(node_item, 'connections', []) or []):
                    try:
                        conns.append({
                            'side': 'start' if c.start_item is node_item else 'end',
                            'other': c.end_item if c.start_item is node_item else c.start_item,
                            'start_port': getattr(c, 'start_port', 'output'),
                            'end_port': getattr(c, 'end_port', 'input')
                        })
                    except Exception:
                        pass
                def undo_fn():
                    created_ref["node"] = self.add_node_with_ports(title=title, x=x, y=y, node_type=node_type, inputs=inputs, outputs=outputs, content=content, record_undo=False)
                    new_node = created_ref["node"]
                    # Restaurar conexiones
                    for cd in conns:
                        try:
                            if cd['side'] == 'start':
                                self.add_connection(new_node, cd['other'], start_port=cd['start_port'], end_port=cd['end_port'], record_undo=False)
                            else:
                                self.add_connection(cd['other'], new_node, start_port=cd['start_port'], end_port=cd['end_port'], record_undo=False)
                        except Exception:
                            pass
                def redo_fn():
                    try:
                        if created_ref["node"] is not None:
                            self.remove_node(created_ref["node"], record_undo=False)
                            created_ref["node"] = None
                    except Exception:
                        pass
                self._push_undo(undo_fn=undo_fn, redo_fn=redo_fn, label="remove_node")
        except Exception:
            pass

        # Eliminar todas las conexiones del nodo sin registrar undo por cada una
        for connection in node_item.connections[:]:
            self.remove_connection(connection, record_undo=False)
        
        # Eliminar el nodo
        try:
            if node_item is not None and node_item.scene() is self._scene:
                self._scene.removeItem(node_item)
        except Exception:
            pass

    def center_on_selected(self):
        selected = self._scene.selectedItems()
        if not selected:
            return
        combined = selected[0].sceneBoundingRect()
        for it in selected[1:]:
            combined = combined.united(it.sceneBoundingRect())
        pad = max(40.0, max(combined.width(), combined.height()) * 0.15)
        padded = combined.adjusted(-pad, -pad, pad, pad)
        old_anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.fitInView(padded, Qt.KeepAspectRatio)
        self.setTransformationAnchor(old_anchor)
        self._zoom = 0
        try:
            scale_x = float(self.transform().m11())
            self.zoomChanged.emit(scale_x)
        except Exception:
            pass
        # Reaplicar hints acordes al nuevo ajuste
        try:
            self._apply_dynamic_render_hints(scale_x)
            try:
                for it in self._scene.items():
                    if isinstance(it, NodeItem):
                        it.apply_adaptive_text_behavior(scale_x)
            except Exception:
                pass
        except Exception:
            pass

    def closeEvent(self, event):
        self._rubber_band.hide()
        super().closeEvent(event)

    # ----------------------
    # Runtime helpers
    # ----------------------
    def evaluate_graph(self):
        """Reconstruye y evalúa el grafo si el runtime está disponible."""
        try:
            if hasattr(self, '_runtime') and self._runtime:
                self._runtime.rebuild_from_view()
                self._runtime.evaluate_all()
        except Exception:
            pass
        # Emitir siempre la señal para refrescar paneles en tiempo real
        try:
            self.graphEvaluated.emit()
        except Exception:
            pass

    # ----------------------
    # Persistencia (Export/Import)
    # ----------------------
    def export_graph(self) -> dict:
        """Exporta los nodos y conexiones actuales a un diccionario serializable."""
        nodes: list[NodeModel] = []
        id_map = {}
        try:
            # Recoger nodos de la escena
            for item in list(self._scene.items()):
                if isinstance(item, NodeItem):
                    try:
                        inputs = [
                            {"name": str(p.get("name", "input")), "kind": str(p.get("kind", "data"))}
                            for p in (getattr(item, "input_ports", []) or [])
                        ]
                        outputs = [
                            {"name": str(p.get("name", "output")), "kind": str(p.get("kind", "data"))}
                            for p in (getattr(item, "output_ports", []) or [])
                        ]
                    except Exception:
                        inputs, outputs = [], []
                    nm = NodeModel(
                        type=str(getattr(item, "node_type", "generic") or "generic"),
                        title=str(getattr(item, "title", "Node") or "Node"),
                        x=float(item.scenePos().x()),
                        y=float(item.scenePos().y()),
                        content=str(getattr(item, "content", "") or ""),
                        inputs=inputs,
                        outputs=outputs,
                        meta={}
                    )
                    nodes.append(nm)
                    id_map[item] = nm.id
        except Exception:
            pass

        # Recoger conexiones
        conns = []
        try:
            for c in list(self.connections):
                sid = id_map.get(getattr(c, "start_item", None))
                eid = id_map.get(getattr(c, "end_item", None))
                if sid and eid:
                    conns.append({
                        "start": sid,
                        "start_port": str(getattr(c, "start_port", "output") or "output"),
                        "end": eid,
                        "end_port": str(getattr(c, "end_port", "input") or "input"),
                    })
        except Exception:
            pass

        try:
            scale_x = float(self.transform().m11())
        except Exception:
            scale_x = 1.0

        project_dict = project_to_dict(nodes, meta={"view": {"zoom": scale_x}})
        return {"project": project_dict, "connections": conns}

    def import_graph(self, data: dict, clear: bool = True) -> None:
        """Importa un grafo desde un diccionario y reconstruye la escena.

        Si `clear` es True, limpia la escena actual antes de importar.
        """
        try:
            if clear:
                self.clear_nodes()
        except Exception:
            pass

        id_to_item = {}
        # Crear nodos
        try:
            models = project_from_dict(data.get("project", {}))
            for nm in models:
                try:
                    # Omitir nodos Output/Group Output al importar para eliminarlos por completo
                    if str(getattr(nm, 'type', '')).lower() in ('output','group_output'):
                        continue
                    # inputs/outputs ya vienen como lista de dicts {name, kind}
                    node = self.add_node_with_ports(
                        title=str(nm.title or "Node"),
                        x=float(nm.x),
                        y=float(nm.y),
                        node_type=str(nm.type or "generic"),
                        inputs=[dict(p) for p in (nm.inputs or [])],
                        outputs=[dict(p) for p in (nm.outputs or [])],
                        content=str(nm.content or ""),
                        record_undo=False,
                    )
                    if node is not None:
                        id_to_item[nm.id] = node
                except Exception:
                    pass
        except Exception:
            pass

        # Crear conexiones
        try:
            for cd in list(data.get("connections", []) or []):
                sid = cd.get("start")
                eid = cd.get("end")
                sitem = id_to_item.get(sid)
                eitem = id_to_item.get(eid)
                if sitem is not None and eitem is not None:
                    try:
                        self.add_connection(
                            sitem,
                            eitem,
                            start_port=str(cd.get("start_port", "output") or "output"),
                            end_port=str(cd.get("end_port", "input") or "input"),
                            record_undo=False,
                        )
                    except Exception:
                        pass
        except Exception:
            pass

        # Ajuste de vista y evaluación
        try:
            items = list(id_to_item.values())
            if items:
                combined = items[0].sceneBoundingRect()
                for it in items[1:]:
                    combined = combined.united(it.sceneBoundingRect())
                pad = max(60.0, max(combined.width(), combined.height()) * 0.15)
                padded = combined.adjusted(-pad, -pad, pad, pad)
                old_anchor = self.transformationAnchor()
                self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
                self.fitInView(padded, Qt.KeepAspectRatio)
                self.setTransformationAnchor(old_anchor)
                self._zoom = 0
                try:
                    self.zoomChanged.emit(float(self.transform().m11()))
                except Exception:
                    pass
                # Ajustar hints tras auto-encuadre
                try:
                    self._apply_dynamic_render_hints(float(self.transform().m11()))
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.evaluate_graph()
        except Exception:
            pass

    # ----------------------
    # Drag & Drop desde Explorer/OS
    # ----------------------
    def dragEnterEvent(self, event):
        try:
            md = event.mimeData()
            if md.hasUrls() or md.hasText() or md.hasFormat("text/uri-list") or md.hasFormat("application/x-qabstractitemmodeldatalist"):
                event.acceptProposedAction()
                return
        except Exception:
            pass
        event.ignore()

    def dragMoveEvent(self, event):
        """Asegura aceptación durante el movimiento para permitir el drop."""
        try:
            md = event.mimeData()
            if md.hasUrls() or md.hasText() or md.hasFormat("text/uri-list") or md.hasFormat("application/x-qabstractitemmodeldatalist"):
                event.acceptProposedAction()
                return
        except Exception:
            pass
        event.ignore()

    def dropEvent(self, event):
        try:
            scene_pos = self.mapToScene(getattr(event, 'position', lambda: None)() .toPoint() if hasattr(event, 'position') else event.pos())
        except Exception:
            scene_pos = self.mapToScene(event.pos())
        try:
            md = event.mimeData()
            file_paths = []
            if md.hasUrls():
                for url in md.urls():
                    try:
                        local = url.toLocalFile()
                        if local:
                            file_paths.append(local)
                    except Exception:
                        pass
            # Algunos views (como QTreeView+QFileSystemModel) emiten text/uri-list
            if not file_paths and md.hasFormat("text/uri-list"):
                try:
                    raw = bytes(md.data("text/uri-list")).decode("utf-8", errors="replace")
                    for line in raw.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#"):
                            # Convertir file:/// a ruta local
                            if line.startswith("file:///"):
                                local = line.replace("file:///", "")
                                file_paths.append(local)
                            else:
                                file_paths.append(line)
                except Exception:
                    pass
            elif not file_paths and md.hasText():
                file_paths.append(md.text())
            # Mapeo simple de extensiones a tipo de nodo
            def _node_type_for(ext: str) -> str:
                ext = ext.lower()
                if ext in (".txt", ".md", ".log"):
                    return "text"
                if ext in (".py",):
                    return "python"
                if ext in (".cpp", ".cc", ".c", ".hpp", ".h"):
                    return "cpp"
                if ext in (".json", ".yaml", ".yml", ".toml"):
                    return "config"
                if ext in (".csv", ".tsv"):
                    return "table"
                return "file"

            # Deduplicar rutas preservando el orden
            seen = set()
            uniq_paths = []
            for p in file_paths:
                np = os.path.normpath(p)
                if np not in seen:
                    seen.add(np)
                    uniq_paths.append(np)

            for i, path in enumerate(uniq_paths):
                try:
                    x = scene_pos.x() + i * 20.0
                    y = scene_pos.y() + i * 14.0
                    base = os.path.basename(path)
                    title = base
                    ext = os.path.splitext(base)[1]
                    ntype = _node_type_for(ext)
                    # Intentar cargar contenido para tipos de texto/código
                    content = path
                    if ntype in ("text", "python", "cpp", "config", "table"):
                        try:
                            with open(path, "r", encoding="utf-8", errors="replace") as f:
                                content = f.read()
                        except Exception:
                            content = path  # si falla, al menos conservar la ruta
                    node = self.add_node(title, x, y, node_type=ntype, content=content)
                    if node:
                        # Guardar referencia a la ruta fuente (sin romper el modelo)
                        try:
                            setattr(node, "source_path", path)
                        except Exception:
                            pass
                        # Copiar al caché local para almacenamiento independiente
                        try:
                            cache_dir = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
                            if not cache_dir:
                                cache_dir = os.path.join(os.getcwd(), "cache")
                            cache_dir = os.path.join(cache_dir, "Codemind-Visual", "NodeCache")
                            os.makedirs(cache_dir, exist_ok=True)
                            # Nombre con hash para evitar colisiones
                            try:
                                stat = os.stat(path)
                                payload = f"{path}|{stat.st_mtime}|{stat.st_size}".encode("utf-8", errors="ignore")
                            except Exception:
                                payload = path.encode("utf-8", errors="ignore")
                            digest = hashlib.sha1(payload).hexdigest()[:12]
                            name, ext2 = os.path.splitext(base)
                            cached_name = f"{name}.{digest}{ext2}"
                            dst = os.path.join(cache_dir, cached_name)
                            if not os.path.exists(dst):
                                shutil.copy2(path, dst)
                            try:
                                setattr(node, "cache_path", dst)
                            except Exception:
                                pass
                        except Exception:
                            pass
                        node.setSelected(True)
                except Exception:
                    pass
            event.acceptProposedAction()
        except Exception:
            event.ignore()

    # ----------------------
    # Minimap helpers
    # ----------------------
    def _layout_minimap(self):
        # Ya no se usa child view; el layout es calculado en drawForeground
        return

    def _update_minimap_fit(self):
        # El minimapa se ajusta dinámicamente en drawForeground
        return

    def resizeEvent(self, event):
        # No hay child view que reubicar
        super().resizeEvent(event)

    # ----------------------
    # Node Effects (text nítido + sombra opcional)
    # ----------------------
    def _apply_node_effects(self, node):
        try:
            # Texto siempre nítido al zoom
            for text_item in getattr(node, "text_items", []):
                text_item.setFlag(node.ItemIgnoresTransformations, True)
            # Sombra opcional (desactivada por defecto)
            if getattr(self, '_node_shadows_enabled', False):
                shadow = QGraphicsDropShadowEffect()
                shadow.setBlurRadius(6)
                shadow.setOffset(2, 2)
                node.setGraphicsEffect(shadow)
            else:
                try:
                    node.setGraphicsEffect(None)
                except Exception:
                    pass
        except Exception:
            pass

    # ----------------------
    # Foreground overlay: Minimap estilo Houdini
    # ----------------------
    def drawForeground(self, painter: QPainter, rect: QRectF):
        super().drawForeground(painter, rect)
        if not getattr(self, '_minimap_enabled', True):
            return
        painter.save()
        try:
            # Dibujar en coordenadas de viewport (overlay independiente del zoom/pan)
            painter.resetTransform()
            vp = self.viewport().rect()
            mm_size = getattr(self, '_minimap_size', QSize(180, 130))
            margin = int(getattr(self, '_minimap_margin', 12))
            # Área del minimapa en coordenadas de viewport
            mm_rect = QRect(
                vp.right() - mm_size.width() - margin,
                vp.bottom() - mm_size.height() - margin,
                mm_size.width(),
                mm_size.height()
            )
            # Fondo y borde del minimapa
            painter.setRenderHint(QPainter.Antialiasing, True)
            from PySide6.QtGui import QLinearGradient
            grad = QLinearGradient(mm_rect.topLeft(), mm_rect.bottomLeft())
            grad.setColorAt(0.0, QColor(26, 28, 32, 220))
            grad.setColorAt(1.0, QColor(20, 22, 26, 220))
            painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(mm_rect, 8, 8)

            # Contenido del minimapa: encajar los items reales (Houdini-like)
            # Usamos itemsBoundingRect para evitar encajar el rectángulo enorme de la escena
            scene_rect = QRectF(self.sceneRect())
            try:
                items_rect = self.scene().itemsBoundingRect()
                # Si hay contenido real, encajamos ese rectángulo ampliado por un padding
                if items_rect.isValid() and items_rect.width() > 1.0 and items_rect.height() > 1.0:
                    pad_items = 80.0
                    scene_rect = QRectF(
                        items_rect.left() - pad_items,
                        items_rect.top() - pad_items,
                        items_rect.width() + 2 * pad_items,
                        items_rect.height() + 2 * pad_items
                    )
            except Exception:
                pass
            # Padding interno del minimapa
            pad = 6
            content_rect = QRectF(
                mm_rect.left() + pad,
                mm_rect.top() + pad,
                mm_rect.width() - 2 * pad,
                mm_rect.height() - 2 * pad
            )
            # Calcular escala para encajar sceneRect manteniendo aspecto
            sx = content_rect.width() / max(1.0, scene_rect.width())
            sy = content_rect.height() / max(1.0, scene_rect.height())
            s = min(sx, sy)
            # Origen para transformar coordenadas de escena a minimapa
            tx = content_rect.left() - scene_rect.left() * s
            ty = content_rect.top() - scene_rect.top() * s
            # Transform profesional: mapea coordenadas de escena -> minimapa
            scene_to_mm = QTransform(s, 0.0, 0.0, s, tx, ty)
            # Recorte para evitar dibujar fuera del panel del minimapa
            try:
                painter.setClipRect(mm_rect.adjusted(1, 1, -1, -1))
            except Exception:
                pass
            # Activar transform y dibujar en coordenadas de escena (más estable)
            painter.setTransform(scene_to_mm, False)
            # Dibujar límites del contenido
            painter.setPen(QPen(QColor(140, 150, 160, 80), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(scene_rect, 6, 6)

            # Rectángulo de viewport actual (área visible en la vista principal)
            try:
                vis_poly = self.mapToScene(self.viewport().rect())
                vis_rect = vis_poly.boundingRect()
                painter.setPen(QPen(QColor(59, 130, 246, 180), 2))  # azul
                painter.setBrush(QBrush(QColor(59, 130, 246, 40)))
                painter.drawRoundedRect(vis_rect, 5, 5)
            except Exception:
                pass
        finally:
            painter.restore()

    # ----------------------
    # Helpers de puertos
    # ----------------------

    def _nearest_port(self, node: NodeItem, scene_pos: QPointF, port_type: str, threshold: float = 28.0):
        """Devuelve el nombre del puerto más cercano si está dentro del umbral."""
        try:
            ports = node.output_ports if port_type == "output" else node.input_ports
            best = None
            best_dist = float('inf')
            for p in ports:
                pos = node.get_port_position(p["name"], port_type)
                dist = (scene_pos - pos).manhattanLength()
                if dist < best_dist:
                    best_dist = dist
                    best = p["name"]
            return best if best is not None and best_dist <= threshold else None
        except Exception:
            return None

    def _find_node_and_port_near_input(self, scene_pos: QPointF, threshold: float = 16.0):
        """Devuelve (nodo, nombre_de_puerto) si hay un puerto de entrada cercano.

        Optimización: consulta sólo los items en un rectángulo pequeño alrededor
        de la posición dada para reducir iteraciones sobre toda la escena.
        """
        try:
            # Rectángulo de búsqueda centrado en scene_pos con tamaño basado en threshold
            half = float(max(8.0, threshold))
            rect = QRectF(scene_pos.x() - half, scene_pos.y() - half, half * 2.0, half * 2.0)

            best_tuple = (None, None)
            best_dist = float('inf')

            # Limitar búsqueda a elementos dentro del rectángulo
            for item in self._scene.items(rect):
                if isinstance(item, NodeItem):
                    # Iterar puertos de entrada de cada nodo visible en el área
                    for p in getattr(item, 'input_ports', []) or []:
                        try:
                            pos = item.get_port_position(p["name"], "input")
                            dist = (scene_pos - pos).manhattanLength()
                            if dist < best_dist:
                                best_dist = dist
                                best_tuple = (item, p["name"])
                        except Exception:
                            # Ignorar errores por nodos sin API completa
                            pass

            return best_tuple if best_tuple[0] is not None and best_dist <= threshold else (None, None)
        except Exception:
            return (None, None)

    def _nearest_node_and_input_port_relaxed(self, scene_pos: QPointF, margin: float = 24.0):
        """Fallback relajado: si el usuario suelta cerca de un nodo, conectar al puerto de entrada más cercano.

        - Considera el rectángulo del nodo con un margen extra.
        - Si hay varios puertos de entrada, elige el más cercano; si no, usa el primero.
        """
        try:
            best_item = None
            best_port = None
            best_dist = float('inf')
            for item in self._scene.items():
                if isinstance(item, NodeItem):
                    rect = item.sceneBoundingRect().adjusted(-margin, -margin, margin, margin)
                    if rect.contains(scene_pos):
                        # Elegir el puerto de entrada más cercano
                        if item.input_ports:
                            for p in item.input_ports:
                                pos = item.get_port_position(p["name"], "input")
                                dist = (scene_pos - pos).manhattanLength()
                                if dist < best_dist:
                                    best_dist = dist
                                    best_item = item
                                    best_port = p["name"]
                        else:
                            # Sin puertos: usar nombre por defecto y dejar que ConnectionItem calcule
                            best_item = item
                            best_port = "input"
            return (best_item, best_port) if best_item is not None else (None, None)
        except Exception:
            return (None, None)

    def add_variable_node(self, language_key, x, y):
        """Añade un nodo de variable con autocompletado inteligente.
        language_key debe ser uno de: 'python', 'cpp', 'javascript'.
        """
        # Establecer lenguaje actual en la librería para que las sugerencias coincidan
        try:
            variable_library.current_language = language_key
        except Exception:
            pass

        # Crear el nodo de variable (sin pasar 'language' al constructor)
        node = VariableNode(title="Variable", x=float(x), y=float(y), node_type="variable")
        # Reflejar el lenguaje en el propio nodo
        try:
            node.set_variable_info({"language": language_key})
        except Exception:
            node._language = language_key

        self._scene.addItem(node)
        self._apply_node_effects(node)
        return node
