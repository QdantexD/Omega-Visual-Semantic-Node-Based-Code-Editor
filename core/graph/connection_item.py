from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsItem
from PySide6.QtGui import QPen, QColor, QPainterPath, QBrush, QLinearGradient
from PySide6.QtCore import QPointF, QRectF, Qt
import math

class ConnectionItem(QGraphicsPathItem):
    """Item gráfico para conexiones entre nodos con curvas bezier."""
    
    def __init__(self, start_item, end_item=None, start_port="output", end_port="input"):
        super().__init__()
        self.start_item = start_item
        self.end_item = end_item
        self.start_port = start_port
        self.end_port = end_port
        self._temp_end_pos = None  # posición temporal mientras se arrastra
        
        # Configuración visual (neón elegante/profesional)
        self._neon_color = QColor(0, 240, 255)        # cian neón suave
        self._neon_core = QColor(30, 200, 220)        # núcleo discreto
        self._cp_magenta = QColor(255, 0, 204)
        self._cp_cyan = QColor(0, 234, 255)
        self._cp_yellow = QColor(255, 239, 0)
        self._use_gradient = False  # para un look más limpio
        self._glow_alpha_strong = 140
        self._glow_alpha_soft = 70
        self.pen = QPen(self._neon_core)
        self.pen.setWidth(2)
        self.setPen(self.pen)
        
        # Habilitar selección sólo con botón derecho; no interferir con arrastre del nodo
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        try:
            self.setAcceptedMouseButtons(Qt.RightButton)
        except Exception:
            pass
        self.setZValue(-1)  # Detrás de los nodos
        try:
            self.setAcceptHoverEvents(True)
        except Exception:
            pass
        self._hovered = False

        # Estado de animación (brillo sutil)
        self._anim_t = 0.0           # 0..1 para punto de brillo que recorre el cable
        self._anim_dash_offset = 0.0 # desplazamiento de guiones durante arrastre
        self._anim_speed = 0.02      # velocidad de avance del brillo
        self._dash_speed = 1.5       # velocidad del desplazamiento de guiones
        self._flicker_phase = 0.0    # fase de flicker para el glow (muy sutil)
        # Shimmer: pequeños destellos que se desplazan por el cable
        self._shimmer_offset = 0.0
        self._shimmer_speed = 2.2

        self.update_path()

    def set_temp_end(self, pos: QPointF):
        """Establece una posición temporal de final mientras se arrastra."""
        self._temp_end_pos = pos
        self.update_path()
    
    def get_port_position(self, item, port_type, port_name):
        """Obtiene la posición del puerto usando API del nodo si está disponible."""
        try:
            if hasattr(item, 'get_port_position'):
                return item.get_port_position(port_name, port_type)
        except Exception:
            pass
        # Fallback a centro del borde correspondiente
        rect = item.rect()
        pos = item.scenePos()
        if port_type == "output":
            return pos + QPointF(rect.width(), rect.height() / 2)
        else:
            return pos + QPointF(0, rect.height() / 2)
    
    def update_path(self):
        """Actualiza la ruta de la conexión."""
        if not self.start_item:
            return
            
        start_pos = self.get_port_position(self.start_item, "output", self.start_port)
        
        if self.end_item:
            end_pos = self.get_port_position(self.end_item, "input", self.end_port)
        elif self._temp_end_pos is not None:
            end_pos = self._temp_end_pos
        else:
            # Si no hay nodo final ni posición temporal, usar una posición base
            end_pos = start_pos + QPointF(120, 0)
        
        # Crear curva bezier
        path = QPainterPath()
        path.moveTo(start_pos)
        
        # Calcular puntos de control para la curva
        dx = end_pos.x() - start_pos.x()
        dy = end_pos.y() - start_pos.y()
        
        # Distancia de control proporcional a la distancia entre nodos
        ctrl_dist = max(abs(dx) * 0.5, 50)
        
        ctrl1 = start_pos + QPointF(ctrl_dist, 0)
        ctrl2 = end_pos - QPointF(ctrl_dist, 0)
        
        path.cubicTo(ctrl1, ctrl2, end_pos)
        self.setPath(path)

    def _make_gradient_brush(self, start_pos: QPointF, end_pos: QPointF, alpha: int = 255) -> QBrush:
        """Crea un QBrush con gradiente magenta–cian–amarillo (estilo cyberpunk)."""
        grad = QLinearGradient(start_pos, end_pos)
        # stops con alpha aplicado
        m = QColor(self._cp_magenta)
        c = QColor(self._cp_cyan)
        y = QColor(self._cp_yellow)
        m.setAlpha(alpha)
        c.setAlpha(alpha)
        y.setAlpha(alpha)
        grad.setColorAt(0.0, m)
        grad.setColorAt(0.5, c)
        grad.setColorAt(1.0, m)
        return QBrush(grad)

    # Hover para realce sutil
    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def finalize_end(self):
        """Limpia el estado temporal una vez fijado el nodo destino."""
        self._temp_end_pos = None
    
    def shape(self):
        """Define la forma de hit más estrecha para evitar capturar clics sobre nodos."""
        path = self.path()
        stroke_path = QPainterPath()
        if not path.isEmpty():
            rect = path.boundingRect()
            stroke_path.addRect(rect.adjusted(-3, -3, 3, 3))
        return stroke_path
    
    def paint(self, painter, option, widget=None):
        """Pinta la conexión con estilo limpio y neón con animación sutil."""
        if self.path().isEmpty():
            return

        path = self.path()
        start_pos = path.pointAtPercent(0)
        end_pos = path.pointAtPercent(1)

        # Brillo (glow) bajo la línea con flicker sutil
        painter.save()
        flicker = 0.85 + 0.15 * math.sin(self._flicker_phase)  # amplitud baja
        if self._hovered:
            flicker *= 1.15
        soft_alpha = int(self._glow_alpha_soft * min(flicker, 1.25))
        strong_alpha = int(self._glow_alpha_strong * min(flicker, 1.25))
        if self._use_gradient:
            brush_soft = self._make_gradient_brush(start_pos, end_pos, soft_alpha)
            brush_strong = self._make_gradient_brush(start_pos, end_pos, strong_alpha)
            glow_pen_soft = QPen(brush_soft, 8)
            glow_pen_soft.setCapStyle(Qt.RoundCap)
            glow_pen_soft.setJoinStyle(Qt.RoundJoin)
            painter.setPen(glow_pen_soft)
            painter.drawPath(path)
            glow_pen_strong = QPen(brush_strong, 5)
            glow_pen_strong.setCapStyle(Qt.RoundCap)
            glow_pen_strong.setJoinStyle(Qt.RoundJoin)
            painter.setPen(glow_pen_strong)
            painter.drawPath(path)
        else:
            glow_pen_soft = QPen(QColor(self._neon_color.red(), self._neon_color.green(), self._neon_color.blue(), soft_alpha))
            glow_pen_soft.setWidth(8)
            painter.setPen(glow_pen_soft)
            painter.drawPath(path)
            glow_pen_strong = QPen(QColor(self._neon_color.red(), self._neon_color.green(), self._neon_color.blue(), strong_alpha))
            glow_pen_strong.setWidth(5)
            painter.setPen(glow_pen_strong)
            painter.drawPath(path)
        painter.restore()

        # Línea principal (núcleo)
        if self.isSelected():
            core_color = QColor("#f59e0b")
            core_width = 3
            line_style = Qt.SolidLine
        else:
            core_color = self._neon_core
            core_width = 2
            # Durante arrastre mostrar línea discontinua animada
            line_style = Qt.SolidLine if self.end_item is not None else Qt.DashLine

        # Núcleo limpio (sin gradiente) para mayor elegancia
        self.pen.setWidth(core_width)
        self.pen.setStyle(line_style)
        self.pen.setColor(core_color if self.isSelected() else self._neon_core)
        if line_style == Qt.DashLine:
            try:
                self.pen.setDashPattern([8, 6])
                self.pen.setDashOffset(self._anim_dash_offset)
            except Exception:
                pass
        self.setPen(self.pen)
        super().paint(painter, option, widget)

        # Punto de brillo que recorre la curva (animación sutil)
        # Shimmer overlay (solo cuando hay destino fijo)
        if self.end_item is not None:
            painter.save()
            shimmer_alpha = 100 if not self._hovered else 140
            shimmer_pen = QPen(QColor(self._neon_color.red(), self._neon_color.green(), self._neon_color.blue(), shimmer_alpha))
            shimmer_pen.setWidth(2)
            shimmer_pen.setStyle(Qt.DashLine)
            shimmer_pen.setCapStyle(Qt.RoundCap)
            shimmer_pen.setJoinStyle(Qt.RoundJoin)
            shimmer_pen.setDashPattern([3, 12])
            shimmer_pen.setDashOffset(self._shimmer_offset)
            painter.setPen(shimmer_pen)
            painter.drawPath(path)
            painter.restore()

        painter.save()
        painter.setPen(Qt.NoPen)
        # Estilo profesional: sin destello viajero para evitar distracción
        painter.restore()

    def tick_animation(self):
        """Avanza el estado de animación y solicita repintado."""
        self._anim_t += self._anim_speed
        if self._anim_t > 1.0:
            self._anim_t -= 1.0
        self._anim_dash_offset += self._dash_speed
        if self._anim_dash_offset > 1000.0:
            self._anim_dash_offset = 0.0
        self._flicker_phase += 0.08
        if self._flicker_phase > math.pi * 2:
            self._flicker_phase -= math.pi * 2
        self._shimmer_offset += self._shimmer_speed
        if self._shimmer_offset > 1000.0:
            self._shimmer_offset = 0.0
        self.update()
