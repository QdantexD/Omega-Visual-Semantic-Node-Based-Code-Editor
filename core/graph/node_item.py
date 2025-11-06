from PySide6.QtWidgets import (
    QApplication, QGraphicsRectItem, QGraphicsTextItem, QGraphicsView, QGraphicsScene, QGraphicsItem,
    QPlainTextEdit, QWidget, QGraphicsProxyWidget, QGraphicsDropShadowEffect, QPushButton
)
from PySide6.QtCore import QRectF, Qt, QPointF, QSize, QTimer
from PySide6.QtGui import QBrush, QColor, QPen, QFont, QPainter, QPainterPath, QLinearGradient
import sys

GRID_SIZE = 20  # Snap al grid

# -----------------------------
# Editor de código con números de línea (para incrustar en el nodo)
# -----------------------------
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor
    def sizeHint(self):
        return QSize(self._editor.lineNumberAreaWidth(), 0)
    def paintEvent(self, event):
        self._editor.lineNumberAreaPaintEvent(event)

class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._host_node = None  # Se establece desde NodeItem
        # Flag anti-reentrancia para el pintado de números de línea
        self._painting_line_numbers = False
        self.lineNumberArea = LineNumberArea(self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.updateLineNumberAreaWidth(0)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFont(QFont("Courier", 11))
        # Estilos tipo editor de código (sin marco ni borde de enfoque)
        self.setStyleSheet(
            "QPlainTextEdit {"
            " background-color: #0f172a;"  # slate-900
            " color: #e2e8f0;"              # texto claro
            " border: none;"                # sin borde
            " selection-background-color: #1e293b;"
            "}"
        )
        try:
            # Eliminar marco del QFrame base para evitar cuadros visibles
            from PySide6.QtWidgets import QFrame
            self.setFrameStyle(QFrame.NoFrame)
        except Exception:
            pass

    def lineNumberAreaWidth(self):
        digits = 1
        max_ = max(1, self.blockCount())
        while max_ >= 10:
            max_ //= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height())

    def lineNumberAreaPaintEvent(self, event):
        # Evitar reentrancia: si ya estamos pintando, salimos
        if getattr(self, '_painting_line_numbers', False):
            return
        self._painting_line_numbers = True
        painter = QPainter(self.lineNumberArea)
        try:
            painter.fillRect(event.rect(), QColor("#0b1220"))
            block = self.firstVisibleBlock()
            blockNumber = block.blockNumber()
            top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
            bottom = top + self.blockBoundingRect(block).height()
            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and bottom >= event.rect().top():
                    number = str(blockNumber + 1)
                    painter.setPen(QColor("#64748b"))
                    painter.drawText(0, int(top), int(self.lineNumberArea.width()) - 4, int(self.fontMetrics().height()), Qt.AlignRight, number)
                block = block.next()
                top = bottom
                bottom = top + self.blockBoundingRect(block).height()
                blockNumber += 1
        finally:
            try:
                painter.end()
            except Exception:
                pass
            self._painting_line_numbers = False

    def keyPressEvent(self, event):
        # Salir de modo edición con ESC
        if event.key() == Qt.Key_Escape:
            try:
                if self._host_node is not None and hasattr(self._host_node, 'exit_editing_request'):
                    self._host_node.exit_editing_request()
                    event.accept()
                    return
            except Exception:
                pass
        super().keyPressEvent(event)

class NodeItem(QGraphicsRectItem):
    """Nodo estilo Houdini/Nuke: movimiento estable, snap al grid, selección múltiple y hover."""

    def __init__(self, title="Node", x=0, y=0, w=240, h=110, node_type="generic"):
        super().__init__()
        # Tamaños por modo
        self._default_w, self._default_h = w, h
        self._edit_w, self._edit_h = max(260, w + 80), max(160, h + 70)
        self._w, self._h = self._default_w, self._default_h
        # Límites y estado de redimensionamiento
        self._min_w, self._min_h = max(190, w), max(80, h)
        self._resizing = False
        self._resize_start_scene_pos = QPointF()
        self._resize_start_rect = QRectF()
        self._resize_handle_size = 14
        self._auto_resize_enabled = True
        # Métricas al estilo Houdini: esquinas más sobrias y barra compacta
        self.title_h = 28
        self.radius = 10
        self._port_gap = 18
        self.setRect(0, 0, w, h)
        self.setPos(x, y)

        # Flags de interacción
        self.setFlags(
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemSendsGeometryChanges |
            QGraphicsItem.ItemClipsChildrenToShape
        )
        self.setAcceptHoverEvents(True)
        # Caché de item para mejorar estabilidad del render al hacer zoom/pan
        try:
            self.setCacheMode(QGraphicsItem.ItemCoordinateCache)
        except Exception:
            pass
        
        # Puertos de conexión
        self.input_ports = []  # Lista de puertos de entrada
        self.output_ports = []  # Lista de puertos de salida
        self.connections = []  # Conexiones activas
        
        # Agregar puertos por defecto
        self.add_input_port("input")
        self.add_output_port("output")

        # Datos
        self.title = title
        self.content = ""
        self.node_type = node_type
        # Flag de snapshot (nodo "fantasma": su contenido no se sobrescribe por el runtime)
        self.is_snapshot = False
        # Flag para permitir que un nodo de tipo 'output' reenvíe su contenido por el puerto OUT
        self.forward_output = False
        self._hovered = False
        self._editing = False
        self.id = str(id(self))  # ID único para el nodo

        # Padding del área de contenido para evitar solaparse con etiquetas de puertos
        self._content_padding_left = 56
        self._content_padding_right = 56
        self._content_padding_top = 8
        self._content_padding_bottom = 8

        # Valores de puertos (runtime)
        self.input_values = {}
        self.output_values = {}
        # Estado del nodo (Blender‑like)
        self.muted = False

        # Ampliación simple en bordes (hitbox más generosa)
        self._edge_expand_px = 4

        # Hints de snap para resaltar puertos durante arrastre
        self._snap_hint_input_port_name = None
        self._snap_hint_output_port_name = None

        # Paleta oscura estilo Houdini: sobria y profesional
        self._bg_color = QColor("#23262b")              # fondo del nodo
        self._border_color = QColor("#3a3f4b")          # borde normal
        self._selected_border_color = QColor("#f59e0b") # borde seleccionado (ámbar)
        self._title_bg_color = QColor("#1b1e24")        # barra de título
        self._title_text_color = QColor("#e6e8ea")      # texto de título

        # Título (editable)
        self.title_item = QGraphicsTextItem(self)
        self.title_item.setPlainText(self.title)
        self.title_item.setDefaultTextColor(self._title_text_color)
        try:
            f = QFont("Segoe UI", 13, QFont.DemiBold)
        except Exception:
            f = QFont("Sans", 13, QFont.DemiBold)
        try:
            # Un pequeño tracking mejora legibilidad sin parecer 'espaciado de logo'
            f.setLetterSpacing(QFont.PercentageSpacing, 102)
        except Exception:
            pass
        self.title_item.setFont(f)
        self.title_item.setTextInteractionFlags(Qt.NoTextInteraction)
        # Hacer que el título escale con el zoom para evitar textos gigantes
        try:
            self.title_item.setFlag(QGraphicsItem.ItemIgnoresTransformations, False)
            # Recortar el texto al shape del nodo para evitar desbordes
            self.title_item.setFlag(QGraphicsItem.ItemClipsToShape, True)
        except Exception:
            pass
        # Evitar foco para que no aparezcan rectángulos de selección/resaltado
        self.title_item.setFlag(QGraphicsItem.ItemIsFocusable, False)
        self._update_title_pos()
        # Sombra sutil en el título (evitar neon, look más profesional)
        # Evitar efectos de sombra que pueden causar repintados reentrantes en algunos sistemas
        self._title_glow = None

        # Estilo de título plano (sin prefijo), más cercano a Houdini
        self._title_is_comment_style = False
        self._refresh_title_text()

        # Contenido visible bajo el título (editable)
        self.content_item = QGraphicsTextItem(self)
        self.content_item.setPlainText(self.content)
        self.content_item.setDefaultTextColor(QColor("#d1d5db"))
        # Fuente monoespaciada amigable para Windows; fallback si no existe
        try:
            mono = QFont("Consolas", 10)
        except Exception:
            mono = QFont("Courier New", 10)
        self.content_item.setFont(mono)
        self.content_item.setTextInteractionFlags(Qt.NoTextInteraction)
        # Deshabilitar foco para evitar el rectángulo punteado blanco
        self.content_item.setFlag(QGraphicsItem.ItemIsFocusable, False)
        # Texto nítido sin escalar con el zoom
        try:
            # Mantener el texto contenido dentro del nodo en cualquier zoom
            self.content_item.setFlag(QGraphicsItem.ItemIgnoresTransformations, False)
        except Exception:
            pass
        # Mantener oculto en modo vista; se usa para medir alto del documento
        try:
            self.content_item.setVisible(False)
        except Exception:
            pass
        self._update_content_layout()
        # Sombra sutil en el contenido (evitar neon)
        self._content_glow = None
        # Registrar items de texto para efectos desde la vista
        try:
            self.text_items = [self.title_item, self.content_item]
        except Exception:
            self.text_items = []

        # Editor clásico de código incrustado (oculto por defecto)
        self.content_editor = CodeEditor()
        self.content_editor.setPlainText(self.content or "")
        # Vincular el editor con el nodo para manejar ESC
        try:
            self.content_editor._host_node = self
        except Exception:
            pass
        # Evaluación en vivo: debounced mientras se escribe en el editor incrustado
        try:
            self._inline_edit_timer = QTimer()
            self._inline_edit_timer.setSingleShot(True)
            self._inline_edit_timer.setInterval(100)
            self._inline_edit_timer.timeout.connect(self._inline_live_evaluate)
            self.content_editor.textChanged.connect(self._on_inline_text_changed)
        except Exception:
            self._inline_edit_timer = None
        self.content_editor_proxy = QGraphicsProxyWidget(self)
        self.content_editor_proxy.setWidget(self.content_editor)
        self.content_editor_proxy.setVisible(False)
        self.content_editor_proxy.setZValue(11)
        # Botón de salir eliminado: se usará tecla ESC
        # Resaltado sintáctico neón básico para el editor incrustado
        try:
            from ..ui.text_editor import PythonHighlighter
            self._inline_syntax = PythonHighlighter(self.content_editor.document())
        except Exception:
            self._inline_syntax = None

    def _on_inline_text_changed(self):
        """Arranca el temporizador de evaluación en vivo cuando cambia el texto."""
        try:
            if self._inline_edit_timer is not None:
                self._inline_edit_timer.start()
        except Exception:
            pass

    def _inline_live_evaluate(self):
        """Sincroniza el contenido y solicita evaluación del grafo."""
        try:
            # Actualizar el atributo de contenido con el texto actual
            self.content = (self.content_editor.toPlainText() or "").strip()
        except Exception:
            pass
        # Solicitar evaluación del grafo desde la(s) vista(s) que contienen este nodo
        try:
            sc = self.scene()
            if sc:
                for v in sc.views():
                    if hasattr(v, 'evaluate_graph'):
                        try:
                            v.evaluate_graph()
                        except Exception:
                            pass
        except Exception:
            pass

    def _update_title_pos(self):
        rect = self.rect()
        text_rect = self.title_item.boundingRect()
        # Centrado perfecto en la barra de título con ajuste óptico
        x = max(0.0, (rect.width() - text_rect.width()) / 2)
        y_base = (self.title_h - text_rect.height()) / 2
        optical_up = 6.0  # desplaza ligeramente hacia arriba para mejor percepción
        y = max(0.0, y_base - optical_up)
        self.title_item.setPos(x, y)

    def _update_content_layout(self):
        rect = self.rect()
        padding_l = getattr(self, "_content_padding_left", 8)
        padding_r = getattr(self, "_content_padding_right", 8)
        padding_t = getattr(self, "_content_padding_top", 8)
        padding_b = getattr(self, "_content_padding_bottom", 8)
        # Calcular un inicio de contenido debajo de una cabecera estática (título + puertos)
        rows_cap = int(getattr(self, "_header_rows_capacity", 2))
        gap = float(getattr(self, "_port_gap", 18))
        # Cabecera fija para hasta 'rows_cap' filas de puertos
        header_h = 12.0 + max(0, rows_cap - 1) * gap + 22.0
        # Si hay más puertos que la capacidad, empujar contenido para evitar solaparse
        try:
            max_ports = max(len(getattr(self, "input_ports", [])), len(getattr(self, "output_ports", [])))
        except Exception:
            max_ports = 0
        ports_block_h_actual = 12.0 + max(0, max_ports - 1) * gap + (22.0 if max_ports > 0 else 0.0)
        content_top_y = self.title_h + max(padding_t, max(header_h, ports_block_h_actual))
        self.content_item.setPos(padding_l, content_top_y)
        content_w = max(10.0, rect.width() - (padding_l + padding_r))
        content_h = max(10.0, rect.height() - (content_top_y - 0.0) - (padding_b))
        try:
            self.content_item.setTextWidth(content_w)
        except Exception:
            pass
        # Posicionar el editor clásico cuando esté visible
        try:
            self.content_editor_proxy.setPos(padding_l, content_top_y)
            self.content_editor.setFixedSize(int(content_w), int(content_h))
        except Exception:
            pass
        # Botón de salir eliminado: no hay posicionamiento

    def _auto_resize_to_content(self):
        """Ajusta altura (y opcionalmente ancho) del nodo para encajar el contenido."""
        if not getattr(self, "_auto_resize_enabled", True):
            return
        try:
            padding_l = getattr(self, "_content_padding_left", 8)
            padding_r = getattr(self, "_content_padding_right", 8)
            padding_t = getattr(self, "_content_padding_top", 8)
            padding_b = getattr(self, "_content_padding_bottom", 8)
            # Cabecera estática con capacidad de filas y empuje adicional si se excede
            rows_cap = int(getattr(self, "_header_rows_capacity", 2))
            gap = float(getattr(self, "_port_gap", 18))
            header_h = 12.0 + max(0, rows_cap - 1) * gap + 22.0
            try:
                max_ports = max(len(getattr(self, "input_ports", [])), len(getattr(self, "output_ports", [])))
            except Exception:
                max_ports = 0
            ports_block_h_actual = 12.0 + max(0, max_ports - 1) * gap + (22.0 if max_ports > 0 else 0.0)
            content_top_y = self.title_h + max(padding_t, max(header_h, ports_block_h_actual))
            # Altura del documento con el ancho actual del área de contenido
            content_w = max(10.0, self.rect().width() - (padding_l + padding_r))
            try:
                self.content_item.setTextWidth(content_w)
            except Exception:
                pass
            doc_h = 0.0
            try:
                doc_h = float(self.content_item.document().size().height())
            except Exception:
                # Fallback a boundingRect
                try:
                    doc_h = float(self.content_item.boundingRect().height())
                except Exception:
                    doc_h = 0.0
            desired_h = content_top_y + padding_b + max(24.0, doc_h) + 6.0
            # Limitar crecimiento para evitar nodos gigantes accidentales
            max_h = max(self._min_h * 5.0, 600.0)
            new_h = min(max(desired_h, float(self._min_h)), max_h)
            # Ajustar rect si cambia
            if abs(new_h - self.rect().height()) >= 1.0:
                self.prepareGeometryChange()
                self._h = int(new_h)
                self.setRect(0, 0, max(self._min_w, self.rect().width()), self._h)
                self._update_title_pos()
                self._update_content_layout()
                for c in self.connections:
                    if hasattr(c, "update_path"):
                        c.update_path()
        except Exception:
            pass

    def _comment_prefix(self) -> str:
        """Prefijo de comentario según el lenguaje del nodo (si aplica)."""
        lang = getattr(self, "_language", None) or getattr(self, "node_type", None) or ""
        low = str(lang).lower()
        if "python" in low:
            return "# "
        if "cpp" in low or "c++" in low or "javascript" in low or "js" in low:
            return "// "
        return "// "

    def _refresh_title_text(self):
        """Actualiza el texto del título en estilo plano (sin prefijo)."""
        try:
            display = self.title or "título del nodo"
            try:
                # Indicador sutil cuando el nodo es snapshot
                if getattr(self, 'is_snapshot', False):
                    display = f"{display} [snapshot]"
            except Exception:
                pass
            self.title_item.setPlainText(display)
            self.title_item.setDefaultTextColor(self._title_text_color)
            try:
                f = QFont("Segoe UI", 13, QFont.DemiBold)
            except Exception:
                f = QFont("Sans", 13, QFont.DemiBold)
            try:
                f.setLetterSpacing(QFont.PercentageSpacing, 102)
            except Exception:
                pass
            self.title_item.setFont(f)
            self._update_title_pos()
        except Exception:
            pass

    # ----------------------
    # Puertos (múltiples)
    # ----------------------
    def set_ports(self, inputs=None, outputs=None):
        """Define listas de puertos de entrada y salida.
        inputs/outputs: pueden ser listas de nombres (str) o dicts con
        al menos 'name'. Se admite 'kind' opcional ('exec'|'data')."""
        if inputs is not None:
            self.input_ports = []
            for item in (inputs or []):
                if isinstance(item, dict):
                    name = str(item.get("name", "input"))
                    kind = str(item.get("kind", "data")).lower()
                    multi = bool(item.get("multi", False))
                else:
                    name = str(item)
                    kind = "data"
                    multi = False
                self.input_ports.append({"name": name, "type": "input", "kind": kind, "multi": multi, "node": self})
        if outputs is not None:
            self.output_ports = []
            for item in (outputs or []):
                if isinstance(item, dict):
                    name = str(item.get("name", "output"))
                    kind = str(item.get("kind", "data")).lower()
                else:
                    name = str(item)
                    kind = "data"
                self.output_ports.append({"name": name, "type": "output", "kind": kind, "node": self})
        # Sólo agregar por defecto si no se proporcionó parámetro (None)
        if inputs is None and not self.input_ports:
            self.add_input_port("input")
        if outputs is None and not self.output_ports:
            self.add_output_port("output")
        self.update()

    def paint(self, painter: QPainter, option, widget=None):
        """Pinta el nodo con un estilo más elegante al estilo Nuke/Houdini."""
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        # Nivel de detalle basado en zoom para decidir etiquetas visibles
        lod = 1.0
        try:
            lod = float(option.levelOfDetailFromTransform(self.sceneTransform()))
        except Exception:
            pass

        # Colores dinámicos y trazo sobrio
        pen_color = QColor(self._border_color)
        if self.isSelected():
            pen_color = QColor(self._selected_border_color)
        if self._editing:
            # Resaltado sutil en edición
            pen_color = QColor("#f59e0b")  # amber

        # Fondo con borde (doble trazo sutil)
        base_path = QPainterPath()
        base_path.addRoundedRect(rect, self.radius, self.radius)
        painter.setPen(QPen(pen_color, 1.8 if not self._editing else 2.6))
        painter.setBrush(QBrush(self._bg_color if not self._editing else QColor("#0b1220")))
        painter.drawPath(base_path)
        # Inner stroke para profundidad
        inner_rect = rect.adjusted(1, 1, -1, -1)
        painter.setPen(QPen(QColor("#1e293b"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(inner_rect, self.radius - 1, self.radius - 1)

        # Fondo tipo "card" para el preview de texto cuando NO está en edición
        try:
            if not getattr(self, '_editing', False):
                padding_l = getattr(self, "_content_padding_left", 8)
                padding_r = getattr(self, "_content_padding_right", 8)
                padding_t = getattr(self, "_content_padding_top", 8)
                padding_b = getattr(self, "_content_padding_bottom", 8)
                # Calcular cabecera estática y ajuste si hay más puertos de los soportados
                rows_cap = int(getattr(self, "_header_rows_capacity", 2))
                gap = float(getattr(self, "_port_gap", 18))
                header_h = 12.0 + max(0, rows_cap - 1) * gap + 22.0
                max_ports = 0
                try:
                    max_ports = max(len(getattr(self, "input_ports", [])), len(getattr(self, "output_ports", [])))
                except Exception:
                    pass
                ports_block_h_actual = 12.0 + max(0, max_ports - 1) * gap + (22.0 if max_ports > 0 else 0.0)
                content_top_y = rect.top() + self.title_h + max(padding_t, max(header_h, ports_block_h_actual))
                content_rect = QRectF(
                    rect.left() + padding_l,
                    content_top_y,
                    rect.width() - (padding_l + padding_r),
                    max(10.0, rect.height() - (content_top_y - rect.top()) - (padding_b))
                )
                # Gradiente sutil para mejorar profundidad y legibilidad del texto
                from PySide6.QtGui import QLinearGradient
                grad_card = QLinearGradient(content_rect.topLeft(), content_rect.bottomLeft())
                grad_card.setColorAt(0.0, QColor(21, 29, 45, 200))
                grad_card.setColorAt(1.0, QColor(15, 22, 35, 200))
                painter.setPen(QPen(QColor(58, 73, 90, 170), 1))
                painter.setBrush(QBrush(grad_card))
                painter.drawRoundedRect(content_rect, 9, 9)
                # Trazo interno para efecto de "inner shadow" muy leve
                inner = content_rect.adjusted(1, 1, -1, -1)
                painter.setPen(QPen(QColor(25, 33, 50, 120), 1))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(inner, 8, 8)
                # Línea de brillo superior muy tenue
                painter.setPen(QPen(QColor(180, 190, 200, 24), 1))
                painter.drawLine(content_rect.topLeft() + QPointF(2, 1), content_rect.topRight() + QPointF(-2, 1))
                # Render del contenido en modo vista: texto con clipping y escala por zoom
                try:
                    painter.save()
                    clip = content_rect.adjusted(2, 2, -2, -2)
                    painter.setClipRect(clip)
                    base_size = 10
                    size = int(max(7, min(13, base_size * max(0.6, min(1.3, lod)))))
                    try:
                        font = QFont("Consolas", size)
                    except Exception:
                        font = QFont("Courier New", size)
                    painter.setFont(font)
                    painter.setPen(QPen(QColor("#e5e7eb"), 1))
                    # Dibujo con word-wrap dentro del rectángulo de contenido
                    painter.drawText(clip, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, getattr(self, 'content', '') or '')
                except Exception:
                    pass
                finally:
                    try:
                        painter.restore()
                    except Exception:
                        pass
        except Exception:
            pass

        # Indicador de manija de redimensionamiento (esquina inferior derecha)
        try:
            handle_size = int(getattr(self, "_resize_handle_size", 14))
            handle_rect = QRectF(rect.right() - handle_size - 2, rect.bottom() - handle_size - 2, handle_size, handle_size)
            painter.setPen(QPen(QColor("#374151"), 1))
            from PySide6.QtGui import QLinearGradient
            grad_h = QLinearGradient(handle_rect.topLeft(), handle_rect.bottomRight())
            grad_h.setColorAt(0.0, QColor(30, 41, 59, 160))
            grad_h.setColorAt(1.0, QColor(17, 24, 39, 160))
            painter.setBrush(QBrush(grad_h))
            painter.drawRoundedRect(handle_rect, 3, 3)
            # Líneas diagonales sutiles
            painter.setPen(QPen(QColor("#64748b"), 1))
            painter.drawLine(handle_rect.bottomLeft() + QPointF(2, -2), handle_rect.topRight() + QPointF(-2, 2))
            painter.drawLine(handle_rect.bottomLeft() + QPointF(4, -6), handle_rect.topRight() + QPointF(-6, 4))
        except Exception:
            pass

        # Ampliación visual de bordes al pasar el cursor (simple y sutil)
        if self._hovered:
            outer_rect = rect.adjusted(-2, -2, 2, 2)
            painter.setPen(QPen(QColor("#334155"), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(outer_rect, self.radius + 1, self.radius + 1)

        # Barra de título con degradado suave
        title_rect = QRectF(rect)
        title_rect.setHeight(self.title_h)
        from PySide6.QtGui import QLinearGradient
        grad = QLinearGradient(title_rect.topLeft(), title_rect.bottomLeft())
        grad.setColorAt(0.0, QColor("#1f2937"))
        grad.setColorAt(1.0, QColor("#242e3d"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(title_rect, min(self.radius, self.title_h / 2), min(self.radius, self.title_h / 2))
        # Acento superior fino
        painter.setPen(QPen(QColor("#3b82f6" if not self.isSelected() else "#f59e0b"), 2))
        painter.drawLine(title_rect.topLeft() + QPointF(2, 1), title_rect.topRight() + QPointF(-2, 1))

        # Separador
        painter.setPen(QPen(QColor("#1f2937"), 1))
        painter.drawLine(title_rect.bottomLeft(), title_rect.bottomRight())

        # Overlay hover eliminado para evitar resaltados blancos molestos

        # Título
        self.title_item.setDefaultTextColor(self._title_text_color)

        # Etiquetas de conectores desactivadas para un estilo más limpio

        # Puertos con estilo sobrio (tipo Nuke/Houdini)
        # Métricas comunes para simetría perfecta
        pill_radius = 8
        pin_gap = 10  # distancia del pin a la píldora
        pill_pad_x = 10
        pill_pad_y = 4
        # Entradas (izquierda)
        for i, port in enumerate(self.input_ports):
            y_pos = (self.title_h + 12) + (i * self._port_gap)
            center = QPointF(6, y_pos)  # posición del pin IN
            connected = self.is_port_connected(port["name"], "input")
            # Conteo de conexiones para indicador visual
            try:
                in_conn_count = self.port_connection_count(port.get("name", "input"), "input")
            except Exception:
                in_conn_count = 0
            highlight = (self._snap_hint_input_port_name == port.get("name"))
            # Detectar tipo de puerto: exec vs data
            port_name = str(port.get("name", "input"))
            port_kind = str(port.get("kind", "data")).lower() if port is not None else "data"
            if port_kind not in ("exec", "data"):
                port_kind = "exec" if "exec" in port_name.lower() else "data"
            if port_kind == "exec":
                base_color = QColor("#9ca3af") if not connected else QColor("#cbd5e1")
                hi_color = QColor("#ffffff")
                ring_color = QColor("#334155")
                glow_color = QColor(255, 255, 255, 96)
                badge_border = QColor("#e5e7eb")
                badge_fill = QColor(55, 65, 81)
                badge_text = QColor("#f9fafb")
                pill_pen = QColor("#e5e7eb")
                pill_grad_top = QColor(50, 58, 70, 180)
                pill_grad_bot = QColor(35, 42, 52, 180)
                text_color = QColor("#f1f5f9") if highlight else QColor("#e2e8f0")
            else:
                base_color = QColor("#4a5568") if not connected else QColor("#7c8aa5")
                hi_color = QColor("#74c0fc")
                ring_color = QColor("#1e293b")
                glow_color = QColor(116, 192, 252, 96)
                badge_border = QColor("#3b82f6")
                badge_fill = QColor(30, 58, 138)
                badge_text = QColor("#e0f2fe")
                pill_pen = QColor("#3b82f6")
                pill_grad_top = QColor(32, 52, 112, 175)
                pill_grad_bot = QColor(18, 30, 68, 175)
                text_color = QColor("#e0f2fe") if highlight else QColor("#cbd5e1")
            # anillo externo sutil para dar presencia al pin
            painter.setPen(QPen(ring_color, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QRectF(center.x() - 8, center.y() - 8, 16, 16))
            painter.setPen(QPen(hi_color if highlight else QColor("#3a3f4b"), 2 if highlight else 1))
            painter.setBrush(QBrush(hi_color if highlight else base_color))
            size = 12 if highlight else 10
            port_rect = QRectF(center.x() - size/2, center.y() - size/2, size, size)
            painter.drawEllipse(port_rect)
            if highlight:
                glow = port_rect.adjusted(-6, -6, 6, 6)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(glow_color))
                painter.drawEllipse(glow)
            # Badge de cantidad de conexiones (IN)
            try:
                if in_conn_count > 0:
                    badge_r = 9
                    badge_rect = QRectF(center.x() - badge_r, center.y() - 18, badge_r * 2, badge_r * 2)
                    painter.setPen(QPen(badge_border, 1))
                    painter.setBrush(QBrush(badge_fill))
                    painter.drawEllipse(badge_rect)
                    painter.setPen(QPen(badge_text, 1))
                    painter.setFont(QFont("Sans", 8, QFont.Bold))
                    painter.drawText(badge_rect, Qt.AlignCenter, str(in_conn_count))
            except Exception:
                pass
            # Etiqueta con simetría respecto al pin
            try:
                if lod >= 0.6:
                    name = port.get("name", "input")
                    painter.setFont(QFont("Sans", 9, QFont.DemiBold))
                    fm = painter.fontMetrics()
                    text_w = fm.horizontalAdvance(name)
                    text_h = fm.height()
                    pill_w = text_w + 2 * pill_pad_x
                    pill_h = max(20, text_h + 2 * pill_pad_y)
                    baseline_y = y_pos + 2
                    top_y = baseline_y - fm.ascent() - pill_pad_y
                    left_x = center.x() + pin_gap
                    bg_rect = QRectF(left_x, top_y, pill_w, pill_h)
                    from PySide6.QtGui import QLinearGradient
                    grad_in = QLinearGradient(bg_rect.topLeft(), bg_rect.bottomLeft())
                    grad_in.setColorAt(0.0, pill_grad_top)
                    grad_in.setColorAt(1.0, pill_grad_bot)
                    painter.setPen(QPen(pill_pen, 1))
                    painter.setBrush(QBrush(grad_in))
                    painter.drawRoundedRect(bg_rect, pill_radius, pill_radius)
                    # Texto
                    painter.setPen(QPen(text_color, 1))
                    painter.drawText(QPointF(left_x + pill_pad_x, baseline_y), name)
            except Exception:
                pass

        # Salidas (derecha)
        for i, port in enumerate(self.output_ports):
            y_pos = (self.title_h + 12) + (i * self._port_gap)
            center = QPointF(self.rect().width() - 6, y_pos)  # posición del pin OUT
            connected = self.is_port_connected(port["name"], "output")
            # Conteo de conexiones para indicador visual
            try:
                out_conn_count = self.port_connection_count(port.get("name", "output"), "output")
            except Exception:
                out_conn_count = 0
            highlight = (self._snap_hint_output_port_name == port.get("name"))
            port_name = str(port.get("name", "output"))
            port_kind = str(port.get("kind", "data")).lower()
            if port_kind not in ("exec", "data"):
                port_kind = "exec" if "exec" in port_name.lower() else "data"
            if port_kind == "exec":
                base_color = QColor("#9ca3af") if not connected else QColor("#cbd5e1")
                hi_color = QColor("#ffffff")
                ring_color = QColor("#334155")
                glow_color = QColor(255, 255, 255, 96)
                badge_border = QColor("#e5e7eb")
                badge_fill = QColor(55, 65, 81)
                badge_text = QColor("#f9fafb")
                pill_pen = QColor("#e5e7eb")
                pill_grad_top = QColor(50, 58, 70, 180)
                pill_grad_bot = QColor(35, 42, 52, 180)
                text_color = QColor("#f1f5f9") if highlight else QColor("#e2e8f0")
            else:
                base_color = QColor("#4a5568") if not connected else QColor("#7c8aa5")
                hi_color = QColor("#f59e0b")
                ring_color = QColor("#1e293b")
                glow_color = QColor(245, 158, 11, 96)
                badge_border = QColor("#f59e0b")
                badge_fill = QColor(120, 53, 15)
                badge_text = QColor("#ffedd5")
                pill_pen = QColor("#f59e0b")
                pill_grad_top = QColor(166, 88, 26, 180)
                pill_grad_bot = QColor(112, 60, 18, 180)
                text_color = QColor("#ffedd5" if highlight else "#f1c79b")
            # anillo externo sutil para dar presencia al pin
            painter.setPen(QPen(ring_color, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QRectF(center.x() - 8, center.y() - 8, 16, 16))
            painter.setPen(QPen(hi_color if highlight else QColor("#3a3f4b"), 2 if highlight else 1))
            painter.setBrush(QBrush(hi_color if highlight else base_color))
            size = 12 if highlight else 10
            port_rect = QRectF(center.x() - size/2, center.y() - size/2, size, size)
            painter.drawEllipse(port_rect)
            if highlight:
                glow = port_rect.adjusted(-6, -6, 6, 6)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(glow_color))
                painter.drawEllipse(glow)
            # Badge de cantidad de conexiones (OUT)
            try:
                if out_conn_count > 0:
                    badge_r = 9
                    badge_rect = QRectF(center.x() - badge_r, center.y() - 18, badge_r * 2, badge_r * 2)
                    painter.setPen(QPen(badge_border, 1))
                    painter.setBrush(QBrush(badge_fill))
                    painter.drawEllipse(badge_rect)
                    painter.setPen(QPen(badge_text, 1))
                    painter.setFont(QFont("Sans", 8, QFont.Bold))
                    painter.drawText(badge_rect, Qt.AlignCenter, str(out_conn_count))
            except Exception:
                pass
            # Etiqueta con simetría respecto al pin
            try:
                if lod >= 0.6:
                    name = port.get("name", "output")
                    painter.setFont(QFont("Sans", 9, QFont.DemiBold))
                    fm = painter.fontMetrics()
                    text_w = fm.horizontalAdvance(name)
                    text_h = fm.height()
                    pill_w = text_w + 2 * pill_pad_x
                    pill_h = max(20, text_h + 2 * pill_pad_y)
                    baseline_y = y_pos + 2
                    top_y = baseline_y - fm.ascent() - pill_pad_y
                    right_edge = center.x() - pin_gap
                    bg_rect = QRectF(right_edge - pill_w, top_y, pill_w, pill_h)
                    from PySide6.QtGui import QLinearGradient
                    grad_out = QLinearGradient(bg_rect.topLeft(), bg_rect.bottomLeft())
                    grad_out.setColorAt(0.0, pill_grad_top)
                    grad_out.setColorAt(1.0, pill_grad_bot)
                    painter.setPen(QPen(pill_pen, 1))
                    painter.setBrush(QBrush(grad_out))
                    painter.drawRoundedRect(bg_rect, pill_radius, pill_radius)
                    # Texto
                    painter.setPen(QPen(text_color, 1))
                    painter.drawText(QPointF(bg_rect.x() + pill_pad_x, baseline_y), name)
            except Exception:
                pass

    def shape(self):
        """Expande la forma para que los bordes sean más fáciles de agarrar/mover."""
        try:
            path = QPainterPath()
            r = self.rect().adjusted(-self._edge_expand_px, -self._edge_expand_px, self._edge_expand_px, self._edge_expand_px)
            path.addRoundedRect(r, self.radius + self._edge_expand_px / 3.0, self.radius + self._edge_expand_px / 3.0)
            return path
        except Exception:
            # Fallback a forma básica
            path = QPainterPath()
            path.addRoundedRect(self.rect(), self.radius, self.radius)
            return path

    # Hover
    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    # Movimiento estable y snap al grid
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            new_pos: QPointF = value
            scene_rect = self.scene().sceneRect()
            x = min(max(new_pos.x(), scene_rect.left()), scene_rect.right() - self.rect().width())
            y = min(max(new_pos.y(), scene_rect.top()), scene_rect.bottom() - self.rect().height())
            x = round(x / GRID_SIZE) * GRID_SIZE
            y = round(y / GRID_SIZE) * GRID_SIZE
            # Actualizar conexiones cuando el nodo se mueve
            for connection in self.connections:
                if hasattr(connection, 'update_path'):
                    connection.update_path()
            return QPointF(x, y)
        # Mantener layout de contenido actualizado en otros cambios
        try:
            if change == QGraphicsItem.ItemSelectedHasChanged or change == QGraphicsItem.ItemSceneHasChanged:
                # Si el nodo entra/sale de selección y estaba en edición, salir para evitar estados incoherentes
                try:
                    if getattr(self, '_editing', False):
                        self.set_editing(False)
                except Exception:
                    pass
                self._update_content_layout()
        except Exception:
            pass
        return super().itemChange(change, value)

    # Métodos para el editor
    def to_plain_text(self):
        """Retorna el contenido del nodo como texto plano."""
        try:
            return self.content_item.toPlainText()
        except Exception:
            return self.content

    def update_from_text(self, text):
        """Actualiza el contenido del nodo desde texto plano."""
        self.content = text.strip()
        try:
            self.content_item.setPlainText(self.content)
            self._update_content_layout()
            # Autoajuste a contenido cuando no está en edición
            if not getattr(self, '_editing', False):
                self._auto_resize_to_content()
        except Exception:
            pass

    def set_editing(self, editing):
        """Establece el estado de edición del nodo."""
        self._editing = editing
        try:
            if editing:
                # Mantener título no editable; renombrado se hace por menú contextual
                self.title_item.setTextInteractionFlags(Qt.NoTextInteraction)
                self.title_item.clearFocus()
                # Asegurar que el contenido plano no muestre foco
                try:
                    self.content_item.clearFocus()
                except Exception:
                    pass
                # Mostrar editor clásico y ocultar el texto plano
                self.content_item.setVisible(False)
                self.content_editor_proxy.setVisible(True)
                self.content_editor.setReadOnly(False)
                self.content_editor.setPlainText(self.content or "")
                self.content_editor.setFocus()
                # Mantener título con estilo comentario también en edición
                self._refresh_title_text()
                # Cambiar tamaño y elevar Z
                self.prepareGeometryChange()
                self.title_h = 34
                self._w, self._h = self._edit_w, self._edit_h
                self.setRect(0, 0, self._w, self._h)
                self.setZValue(10)
                self._update_title_pos()
                self._update_content_layout()
                for c in self.connections:
                    if hasattr(c, "update_path"):
                        c.update_path()
                # Sin botón Salir: salida se realiza con tecla ESC
            else:
                # Deshabilitar edición y sincronizar valores al modelo
                self.title_item.setTextInteractionFlags(Qt.NoTextInteraction)
                self.title_item.clearFocus()
                self.content_editor.setReadOnly(True)
                # Commit del contenido desde el editor clásico
                try:
                    # Solo tomar el texto del editor si el proxy estaba visible (edición real)
                    if self.content_editor_proxy.isVisible():
                        self.content = (self.content_editor.toPlainText() or "").strip()
                except Exception:
                    pass
                # Ocultar editor y mostrar contenido plano
                self.content_editor_proxy.setVisible(False)
                try:
                    # Asegurar que el proxy quede dentro del rect y sin foco
                    self.content_editor.clearFocus()
                    self.content_editor_proxy.setPos(0, 0)
                    self.content_editor.setFixedSize(1, 1)
                except Exception:
                    pass
                # Mantener el contenido plano oculto (renderizado en paint)
                self.content_item.setVisible(False)
                self.content_item.setPlainText(self.content)
                try:
                    # Evitar que el texto plano tome foco al salir de edición
                    self.content_item.clearFocus()
                except Exception:
                    pass
                # Commit
                try:
                    # Mantener título sin tomar el texto del QGraphicsTextItem
                    self._refresh_title_text()
                    self._update_title_pos()
                    self._update_content_layout()
                except Exception:
                    pass
                # Volver a tamaño compacto y Z normal
                self.prepareGeometryChange()
                self.title_h = 28
                self._w, self._h = self._default_w, self._default_h
                self.setRect(0, 0, self._w, self._h)
                self.setZValue(0)
                self._update_title_pos()
                self._update_content_layout()
                # Tras commit, ajustar a contenido
                self._auto_resize_to_content()
                for c in self.connections:
                    if hasattr(c, "update_path"):
                        c.update_path()
                # Sin botón Salir
        except Exception:
            pass
        self.update()

    # ----------------------
    # Redimensionamiento por arrastre (como imagen en Word)
    # ----------------------
    def _resize_handle_rect(self) -> QRectF:
        r = self.rect()
        s = float(getattr(self, "_resize_handle_size", 14))
        return QRectF(r.right() - s - 2, r.bottom() - s - 2, s, s)

    def hoverMoveEvent(self, event):
        try:
            pos = event.pos()
            if self._resize_handle_rect().contains(pos):
                self.setCursor(Qt.SizeFDiagCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
        except Exception:
            pass
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.LeftButton and self._resize_handle_rect().contains(event.pos()):
                self._resizing = True
                self._resize_start_scene_pos = event.scenePos()
                self._resize_start_rect = QRectF(self.rect())
                # Evitar mover mientras se redimensiona
                self.setFlag(QGraphicsItem.ItemIsMovable, False)
                event.accept()
                return
        except Exception:
            pass
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        try:
            if self._resizing and (event.buttons() & Qt.LeftButton):
                delta = event.scenePos() - self._resize_start_scene_pos
                new_w = max(self._min_w, float(self._resize_start_rect.width()) + float(delta.x()))
                new_h = max(self._min_h, float(self._resize_start_rect.height()) + float(delta.y()))
                self.prepareGeometryChange()
                self._w, self._h = int(new_w), int(new_h)
                self.setRect(0, 0, self._w, self._h)
                self._update_title_pos()
                self._update_content_layout()
                for c in self.connections:
                    if hasattr(c, 'update_path'):
                        c.update_path()
                event.accept()
                return
        except Exception:
            pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        try:
            if self._resizing and event.button() == Qt.LeftButton:
                self._resizing = False
                # Restaurar movimiento
                self.setFlag(QGraphicsItem.ItemIsMovable, True)
                event.accept()
                return
        except Exception:
            pass
        super().mouseReleaseEvent(event)

    def exit_editing_request(self):
        """Solicita salir del modo edición (p.ej. tecla ESC)."""
        try:
            self.set_editing(False)
        except Exception:
            pass
        # Notificar a la vista (NodeView) para sincronizar panel lateral
        try:
            sc = self.scene()
            if sc:
                for v in sc.views():
                    if hasattr(v, 'notify_node_editing_exited'):
                        try:
                            v.notify_node_editing_exited(self)
                        except Exception:
                            pass
        except Exception:
            pass
    
    def add_input_port(self, name, kind: str = "data"):
        """Agrega un puerto de entrada.
        kind: 'exec' o 'data' (por defecto 'data')."""
        port = {"name": name, "type": "input", "kind": str(kind).lower(), "multi": False, "node": self}
        self.input_ports.append(port)
        # Inicializar valor de entrada
        try:
            self.input_values[name] = None
        except Exception:
            pass
        self.update()
        return port
    
    def add_output_port(self, name, kind: str = "data"):
        """Agrega un puerto de salida.
        kind: 'exec' o 'data' (por defecto 'data')."""
        port = {"name": name, "type": "output", "kind": str(kind).lower(), "node": self}
        self.output_ports.append(port)
        # Inicializar valor de salida
        try:
            self.output_values[name] = None
        except Exception:
            pass
        self.update()
        return port

    # API de hints de snap
    def set_snap_hint_input_port(self, name):
        """Establece el nombre del puerto de entrada a resaltar (o None para limpiar)."""
        try:
            self._snap_hint_input_port_name = name
            self.update()
        except Exception:
            pass

    def set_snap_hint_output_port(self, name):
        """Establece el nombre del puerto de salida a resaltar (o None para limpiar)."""
        try:
            self._snap_hint_output_port_name = name
            self.update()
        except Exception:
            pass
    
    def get_port_position(self, port_name, port_type):
        """Obtiene la posición de un puerto específico (en coordenadas de escena)."""
        rect = self.rect()
        base_y = self.title_h + 12
        gap = getattr(self, "_port_gap", 18)
        if port_type == "input":
            ports = self.input_ports
            idx = next((i for i, p in enumerate(ports) if p["name"] == port_name), 0)
            y_offset = base_y + (idx * gap)
            return self.scenePos() + QPointF(6, y_offset)
        else:  # output
            ports = self.output_ports
            idx = next((i for i, p in enumerate(ports) if p["name"] == port_name), 0)
            y_offset = base_y + (idx * gap)
            return self.scenePos() + QPointF(rect.width() - 6, y_offset)

    # ----------------------
    # Runtime: valores y cómputo
    # ----------------------
    def receive_input_value(self, port_name: str, value: object):
        """Recibe un valor en un puerto de entrada y lo almacena."""
        try:
            self.input_values[port_name] = value
        except Exception:
            pass

    def _safe_eval_process(self, expr: str, input_val: object):
        """Evalúa de forma segura una expresión simple con la variable 'input'.

        Permite operaciones típicas sobre strings y números, p.ej.:
        - input.upper()
        - input.lower()
        - len(input)
        - str(input)
        - input + "!"
        """
        if not expr:
            return input_val
        # Entorno muy restringido
        safe_globals = {
            '__builtins__': {
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
            }
        }
        safe_locals = {
            'input': input_val
        }
        try:
            return eval(expr, safe_globals, safe_locals)
        except Exception:
            # Fallback más útil: si hay contenido, concatenar a la entrada
            try:
                expr_text = str(expr or "")
                base = "" if input_val is None else str(input_val)
                if expr_text.strip():
                    sep = "\n" if base and not base.endswith("\n") else ""
                    return f"{base}{sep}{expr_text}"
            except Exception:
                pass
            # Si no hay contenido, devolver entrada sin cambios
            return input_val

    def compute_output_values(self) -> dict:
        """Calcula los valores de salida del nodo según su tipo y entradas.

        Por defecto:
        - generic/input: salida 'output' = contenido del nodo
        - variable: salida 'output' = variable_value (si existe), si no, contenido
        - process: usa `content` como expresión con la variable 'input' (entrada por defecto)
        - output: no produce salida útil; mantiene output vacío
        - combine: concatena todas las entradas y su propio contenido
        """
        node_type = str(getattr(self, 'node_type', 'generic') or 'generic').lower()
        result = dict(self.output_values or {})

        # Si el nodo está silenciado (muted), hace passthrough del primer input
        try:
            if getattr(self, 'muted', False):
                passthrough_val = None
                for p in (self.input_ports or []):
                    name = p.get('name', 'input')
                    v = (self.input_values or {}).get(name, None)
                    if v is None:
                        continue
                    if isinstance(v, list):
                        for sv in reversed(v):
                            if sv is not None:
                                passthrough_val = sv
                                break
                    else:
                        passthrough_val = v
                    if passthrough_val is not None:
                        break
                for op in (self.output_ports or []):
                    result[op.get('name', 'output')] = passthrough_val
                self.output_values.update(result)
                return result
        except Exception:
            pass

        if node_type in ('generic', 'input'):
            # Preferir el atributo `content`, que se sincroniza en vivo durante la edición.
            # Si está vacío, caer a `to_plain_text()` (texto del render plano).
            try:
                val = getattr(self, 'content', '')
                if val is None or val == "":
                    val = self.to_plain_text()
            except Exception:
                val = getattr(self, 'content', '')
            # Usar puerto 'output' por defecto
            if self.output_ports:
                out_name = self.output_ports[0]['name']
                result[out_name] = val
            else:
                result['output'] = val
            return result

        if node_type == 'variable':
            # VariableNode guarda variable_value; fallback a contenido
            val = getattr(self, 'variable_value', None)
            if val is None:
                try:
                    val = self.to_plain_text()
                except Exception:
                    val = getattr(self, 'content', '')
            if self.output_ports:
                out_name = self.output_ports[0]['name']
                result[out_name] = val
            else:
                result['output'] = val
            return result

        if node_type == 'process':
            # Tomar la primera entrada como 'input'
            in_val = None
            if self.input_ports:
                in_name = self.input_ports[0]['name']
                in_val = (self.input_values or {}).get(in_name, None)
            # Normalizar listas provenientes de conexiones de tipo 'data'
            # Usar el último valor no nulo como escalar para la expresión
            if isinstance(in_val, list):
                try:
                    for sv in reversed(in_val):
                        if sv is not None:
                            in_val = sv
                            break
                    # Si todos eran None, mantener None
                except Exception:
                    pass
            expr = getattr(self, 'content', '') or ''
            val = self._safe_eval_process(expr, in_val)
            if self.output_ports:
                out_name = self.output_ports[0]['name']
                result[out_name] = val
            else:
                result['output'] = val
            return result

        if node_type == 'combine':
            # Concatena todas las entradas disponibles y su propio contenido
            parts = []
            try:
                # Entradas por puertos
                for p in (self.input_ports or []):
                    name = p.get('name', 'input')
                    v = (self.input_values or {}).get(name, None)
                    if v is None:
                        continue
                    if isinstance(v, list):
                        for sv in v:
                            if sv is not None:
                                parts.append(str(sv))
                    else:
                        parts.append(str(v))
            except Exception:
                pass
            # Propio contenido como parte adicional (opcional)
            try:
                own = self.to_plain_text()
            except Exception:
                own = getattr(self, 'content', '')
            if own:
                parts.append(str(own))
            combined = "\n".join(parts)
            if self.output_ports:
                out_name = self.output_ports[0]['name']
                result[out_name] = combined
            else:
                result['output'] = combined
            return result

        if node_type == 'output':
            # Por defecto consume valores; si forward_output está activo, publica su contenido en OUT
            try:
                if getattr(self, 'forward_output', False):
                    val = None
                    try:
                        val = self.to_plain_text()
                    except Exception:
                        val = getattr(self, 'content', '')
                    if self.output_ports:
                        out_name = self.output_ports[0]['name']
                        result[out_name] = val
                    else:
                        result['output'] = val
            except Exception:
                pass
            return result

        # Fallback para tipos desconocidos
        try:
            val = self.to_plain_text()
        except Exception:
            val = getattr(self, 'content', '')
        if self.output_ports:
            out_name = self.output_ports[0]['name']
            result[out_name] = val
        else:
            result['output'] = val
        return result
    
    def add_connection(self, connection):
        """Agrega una conexión a este nodo."""
        if connection not in self.connections:
            self.connections.append(connection)
    
    def remove_connection(self, connection):
        """Elimina una conexión de este nodo."""
        if connection in self.connections:
            self.connections.remove(connection)
        self.update()

    def is_port_connected(self, port_name, port_type):
        """Devuelve True si el puerto está conectado."""
        for conn in self.connections:
            if port_type == "input" and conn.end_item is self and getattr(conn, "end_port", None) == port_name:
                return True
            if port_type == "output" and conn.start_item is self and getattr(conn, "start_port", None) == port_name:
                return True
        return False

    def port_connection_count(self, port_name: str, port_type: str) -> int:
        """Devuelve el número de conexiones asociadas al puerto indicado.

        - port_type: "input" cuenta las conexiones que llegan a este nodo/puerto.
        - port_type: "output" cuenta las conexiones que salen desde este nodo/puerto.
        """
        count = 0
        try:
            for conn in self.connections:
                if port_type == "input":
                    if conn.end_item is self and getattr(conn, "end_port", None) == port_name:
                        count += 1
                else:
                    if conn.start_item is self and getattr(conn, "start_port", None) == port_name:
                        count += 1
        except Exception:
            pass
        return count

    # Gestión versátil de puertos
    def remove_port(self, port_name, port_type):
        """Elimina un puerto por nombre y tipo."""
        try:
            if port_type == "input":
                self.input_ports = [p for p in self.input_ports if p.get("name") != port_name]
            else:
                self.output_ports = [p for p in self.output_ports if p.get("name") != port_name]
            self.update()
            return True
        except Exception:
            return False

    def rename_port(self, old_name, new_name, port_type):
        """Renombra un puerto, manteniendo conexiones por nombre si coinciden."""
        new_name = (new_name or "").strip()
        try:
            ports = self.input_ports if port_type == "input" else self.output_ports
            for p in ports:
                if p.get("name") == old_name:
                    p["name"] = new_name
                    break
            # Actualizar conexiones que apunten a este puerto
            try:
                for conn in self.connections:
                    if port_type == "input" and conn.end_item is self and getattr(conn, "end_port", None) == old_name:
                        conn.end_port = new_name
                        if hasattr(conn, "update_path"):
                            conn.update_path()
                    if port_type == "output" and conn.start_item is self and getattr(conn, "start_port", None) == old_name:
                        conn.start_port = new_name
                        if hasattr(conn, "update_path"):
                            conn.update_path()
            except Exception:
                pass
            self.update()
            return True
        except Exception:
            return False
