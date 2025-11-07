from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets
from ..graph.node_item import NodeItem


class RealtimeVariablesPanel(QtWidgets.QWidget):
    """Panel lateral de solo lectura para ver variables en tiempo real.

    - Muestra entradas y salidas del nodo principal (o seleccionado).
    - No es editable; sirve como "editor no editable" para inspección.
    - Se actualiza cuando el grafo es evaluado y al cambiar la selección.
    """

    def __init__(self, node_view, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._view = node_view
        self._pinned_node: Optional[NodeItem] = None

        self.setObjectName("RealtimeVariablesPanel")

        # UI
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QtWidgets.QFrame(self)
        header.setObjectName("rtHeader")
        h = QtWidgets.QHBoxLayout(header)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(6)
        self._title = QtWidgets.QLabel("Editor no editable — Monitor en tiempo real", header)
        self._title.setStyleSheet("color:#cbd5e1;font-weight:600;")
        self._btn_pin = QtWidgets.QToolButton(header)
        self._btn_pin.setText("Fijar nodo")
        self._btn_pin.setCheckable(True)
        self._btn_pin.setStyleSheet(
            "QToolButton{background:#1b2230;color:#cbd5e1;border:1px solid #202a36;padding:4px 8px;border-radius:6px;}"
        )
        self._btn_pin.toggled.connect(self._on_toggle_pin)
        h.addWidget(self._title)
        h.addStretch(1)
        h.addWidget(self._btn_pin)

        self._text = QtWidgets.QPlainTextEdit(self)
        self._text.setReadOnly(True)
        self._text.setMinimumWidth(280)
        self._text.setWordWrapMode(QtGui.QTextOption.NoWrap)
        self._text.setStyleSheet(
            "QPlainTextEdit{background:#0f172a;color:#e2e8f0;border:none;padding:6px;}"
        )

        root.addWidget(header, 0)
        root.addWidget(self._text, 1)

        # Estilo del panel
        try:
            self.setStyleSheet(
                "#RealtimeVariablesPanel{background:#0f1318;border-left:1px solid #202a36;}\n"
                "#rtHeader{background:#0f1318;border-bottom:1px solid #202a36;}"
            )
        except Exception:
            pass

        # Señales del NodeView
        try:
            self._view.graphEvaluated.connect(self.refresh)
            self._view.selectedNodeChanged.connect(self._on_selected_node)
        except Exception:
            pass

        # Primera actualización
        QtCore.QTimer.singleShot(0, self.refresh)

    # -----------------------------
    # Interacciones
    # -----------------------------
    def _on_toggle_pin(self, checked: bool) -> None:
        if not checked:
            self._pinned_node = None
            self._title.setText("Editor no editable — Monitor en tiempo real")
            self.refresh()
            return
        # Fijar el nodo actual (seleccionado o candidato principal)
        node = self._best_node()
        self._pinned_node = node
        name = self._node_label(node)
        self._title.setText(f"Fijado: {name}")
        self.refresh()

    def _on_selected_node(self, node: Optional[NodeItem]) -> None:
        if not self._btn_pin.isChecked():
            # Solo actualizar el título si no está fijado
            name = self._node_label(node)
            self._title.setText(f"Seleccionado: {name}")
        self.refresh()

    # -----------------------------
    # Búsqueda del nodo objetivo
    # -----------------------------
    def _best_node(self) -> Optional[NodeItem]:
        # Si hay nodo fijado, usarlo
        if self._pinned_node and isinstance(self._pinned_node, NodeItem):
            return self._pinned_node
        # Preferir el seleccionado
        try:
            selected = [it for it in (self._view._scene.selectedItems() if hasattr(self._view, '_scene') else []) if isinstance(it, NodeItem)]
            if selected:
                return selected[0]
        except Exception:
            pass
        # Buscar un nodo "principal": input/generic
        try:
            for it in self._view._scene.items():
                if isinstance(it, NodeItem):
                    t = str(getattr(it, 'node_type', '')).lower()
                    if t in ('input', 'group_input', 'generic', 'variable'):
                        return it
        except Exception:
            pass
        # Fallback: primero de la escena
        try:
            for it in self._view._scene.items():
                if isinstance(it, NodeItem):
                    return it
        except Exception:
            pass
        return None

    def _node_label(self, node: Optional[NodeItem]) -> str:
        if not isinstance(node, NodeItem):
            return "(ninguno)"
        try:
            title = str(getattr(node, 'title', 'Node') or 'Node')
            ntype = str(getattr(node, 'node_type', 'generic') or 'generic').lower()
            return f"{title} [{ntype}]"
        except Exception:
            return "Node"

    # -----------------------------
    # Refresco de contenido
    # -----------------------------
    def refresh(self) -> None:
        node = self._best_node()
        if not isinstance(node, NodeItem):
            self._text.setPlainText("Sin nodo para monitorear.")
            return

        lines = []
        # Encabezado
        lines.append(f"Nodo: {self._node_label(node)}")
        # Contenido del nodo (solo muestra; no editable aquí)
        try:
            content = getattr(node, 'content', '')
            if content:
                preview = str(content).strip()
                lines.append("Contenido:")
                # Limitar a 8 líneas para evitar panel interminable
                for ln in preview.splitlines()[:8]:
                    lines.append(f"  {ln}")
                if len(preview.splitlines()) > 8:
                    lines.append("  …")
        except Exception:
            pass

        # Entradas actuales
        try:
            ins = dict(getattr(node, 'input_values', {}) or {})
            lines.append("Entradas:")
            if not ins:
                lines.append("  (sin entradas)")
            else:
                for k, v in ins.items():
                    lines.extend(self._format_value_lines(k, v))
        except Exception:
            pass

        # Salidas actuales
        try:
            outs = dict(getattr(node, 'output_values', {}) or {})
            lines.append("Salidas:")
            if not outs:
                lines.append("  (sin salidas)")
            else:
                for k, v in outs.items():
                    lines.extend(self._format_value_lines(k, v))
        except Exception:
            pass

        # Conexiones de puertos (diagnóstico útil)
        try:
            lines.append("Puertos:")
            for p in (getattr(node, 'input_ports', []) or []):
                name = p.get('name', 'input')
                cnt = node.port_connection_count(name, 'input')
                lines.append(f"  IN {name}: {cnt} conexión(es)")
            for p in (getattr(node, 'output_ports', []) or []):
                name = p.get('name', 'output')
                cnt = node.port_connection_count(name, 'output')
                lines.append(f"  OUT {name}: {cnt} conexión(es)")
        except Exception:
            pass

        # Lógica aplicada en conexiones que llegan al nodo
        try:
            incoming = [c for c in (getattr(node, 'connections', []) or []) if getattr(c, 'end_item', None) is node]
            if incoming:
                lines.append("Conexiones (lógica):")
                for c in incoming:
                    lnm = str(getattr(c, 'logic_name', 'passthrough'))
                    ep = str(getattr(c, 'end_port', 'input'))
                    cfg = getattr(c, 'logic_config', {}) or {}
                    # Representar valores de configuración con repr para evitar saltos de línea (e.g. "\n")
                    cfg_preview = ", ".join(f"{k}={repr(v)}" for k, v in dict(cfg).items()) if cfg else "(sin config)"
                    lines.append(f"  -> IN {ep}: {lnm} {cfg_preview}")
        except Exception:
            pass

        # Logs de Python del nodo (si aplica)
        try:
            dbg = ""
            di = getattr(node, 'debug_item', None)
            if di and hasattr(di, 'toPlainText'):
                dbg = str(di.toPlainText() or "")
            if dbg.strip():
                lines.append("Debug Python:")
                for ln in dbg.splitlines()[:10]:
                    lines.append(f"  {ln}")
                if len(dbg.splitlines()) > 10:
                    lines.append("  …")
        except Exception:
            pass

        self._text.setPlainText("\n".join(lines))

    def _format_value_lines(self, key: str, value: object) -> list[str]:
        lines: list[str] = []
        if value is None:
            lines.append(f"  {key} = None")
            return lines
        if isinstance(value, list):
            if not value:
                lines.append(f"  {key} = []")
                return lines
            lines.append(f"  {key}:")
            for idx, sv in enumerate(value):
                lines.append(f"    [{idx}] {sv}")
            return lines
        # Escalar
        lines.append(f"  {key} = {value}")
        return lines


__all__ = ["RealtimeVariablesPanel"]