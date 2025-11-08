from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets
from datetime import datetime
from ..graph.node_item import NodeItem, CodeEditor
from ..graph.connection_item import ConnectionItem


class CodeMapPanel(QtWidgets.QWidget):
    """Panel de solo lectura que refleja código/composición de la selección.

    - Si hay 1 nodo seleccionado: muestra su código (enfasis Python) y diagnóstico de puertos.
    - Si hay 2 nodos seleccionados: muestra cómo se combinan, conectores y lógica aplicada.
    - Escucha cambios de selección y evaluación para actualizar en tiempo real.
    """

    def __init__(self, node_view, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._view = node_view
        self.setObjectName("CodeMapPanel")

        # UI
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QtWidgets.QFrame(self)
        header.setObjectName("cmHeader")
        h = QtWidgets.QHBoxLayout(header)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(6)
        self._title = QtWidgets.QLabel("Mapa de código — Selección", header)
        self._title.setStyleSheet("color:#cbd5e1;font-weight:600;")
        # Toggle de modo: Solo / Doble
        self._btn_solo = QtWidgets.QToolButton(header)
        self._btn_solo.setText("Solo")
        self._btn_solo.setCheckable(True)
        self._btn_solo.setChecked(True)
        self._btn_solo.setStyleSheet(
            "QToolButton{background:#1b2230;color:#cbd5e1;border:1px solid #202a36;padding:4px 10px;border-radius:6px;}"
        )
        self._btn_doble = QtWidgets.QToolButton(header)
        self._btn_doble.setText("Doble")
        self._btn_doble.setCheckable(True)
        self._btn_doble.setStyleSheet(
            "QToolButton{background:#141a24;color:#cbd5e1;border:1px solid #202a36;padding:4px 10px;border-radius:6px;}"
        )
        self._mode_group = QtWidgets.QButtonGroup(header)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self._btn_solo)
        self._mode_group.addButton(self._btn_doble)
        self._mode_group.buttonToggled.connect(lambda _b, _c: self.refresh())
        self._btn_refresh = QtWidgets.QToolButton(header)
        self._btn_refresh.setText("Refrescar")
        self._btn_refresh.clicked.connect(self.refresh)
        self._btn_refresh.setStyleSheet(
            "QToolButton{background:#1b2230;color:#cbd5e1;border:1px solid #202a36;padding:4px 8px;border-radius:6px;}"
        )
        # Botón para mostrar código con viñetas
        self._btn_bullets = QtWidgets.QToolButton(header)
        self._btn_bullets.setText("Puntos")
        self._btn_bullets.setCheckable(True)
        self._btn_bullets.setChecked(True)
        self._btn_bullets.toggled.connect(lambda _c: self.refresh())
        self._btn_bullets.setStyleSheet(
            "QToolButton{background:#141a24;color:#cbd5e1;border:1px solid #202a36;padding:4px 8px;border-radius:6px;}"
        )
        h.addWidget(self._title)
        h.addStretch(1)
        h.addWidget(self._btn_solo)
        h.addWidget(self._btn_doble)
        h.addWidget(self._btn_bullets)
        h.addWidget(self._btn_refresh)

        # Editor con números de línea estilo VS Code
        self._text = CodeEditor(self)
        self._text.setReadOnly(True)
        self._text.setMinimumWidth(300)
        self._text.setWordWrapMode(QtGui.QTextOption.NoWrap)

        root.addWidget(header, 0)

        # Bloque de metadatos (títulos fuera del editor)
        self._meta = QtWidgets.QFrame(self)
        self._meta.setObjectName("cmMeta")
        ml = QtWidgets.QVBoxLayout(self._meta)
        ml.setContentsMargins(8, 6, 8, 6)
        ml.setSpacing(4)
        self._meta_title = QtWidgets.QLabel("Nodo: —", self._meta)
        self._meta_title.setStyleSheet("color:#cbd5e1;font-weight:600;")
        self._meta_lang = QtWidgets.QLabel("Lenguaje: —", self._meta)
        self._meta_lang.setStyleSheet("color:#cbd5e1;")
        self._code_label = QtWidgets.QLabel("Código:", self._meta)
        self._code_label.setStyleSheet("color:#cbd5e1;")
        ml.addWidget(self._meta_title)
        ml.addWidget(self._meta_lang)
        ml.addWidget(self._code_label)
        root.addWidget(self._meta, 0)

        root.addWidget(self._text, 1)

        # Secciones colapsables estilo "Outline" y "Timeline"
        self._sections = QtWidgets.QVBoxLayout()
        self._sections.setContentsMargins(0, 0, 0, 0)
        self._sections.setSpacing(0)
        root.addLayout(self._sections, 0)

        self._outline_btn, self._outline_container, self._outline_text = self._make_section("Outline")
        self._timeline_btn, self._timeline_container, self._timeline_text = self._make_section("Timeline")
        self._sections.addWidget(self._outline_btn)
        self._sections.addWidget(self._outline_container)
        self._sections.addWidget(self._timeline_btn)
        self._sections.addWidget(self._timeline_container)

        # Eventos para Timeline
        self._events: list[str] = []

        # Estilo del panel
        try:
            self.setStyleSheet(
                "#CodeMapPanel{background:#0f1318;border-left:1px solid #202a36;}\n"
                "#cmHeader{background:#0f1318;border-bottom:1px solid #202a36;}\n"
                "#cmMeta{background:#0f1318;border-bottom:1px solid #202a36;}"
            )
        except Exception:
            pass

        # Señales del NodeView
        try:
            self._view.graphEvaluated.connect(self._on_graph_eval)
            self._view.selectedNodeChanged.connect(self._on_selection_event)
            self._view.selectionCountChanged.connect(self._on_selection_count)
            # Refrescar al salir de edición (ESC o cerrar editor incrustado)
            if hasattr(self._view, 'editingExited'):
                self._view.editingExited.connect(self._on_editing_exited)
        except Exception:
            pass

        QtCore.QTimer.singleShot(0, self.refresh)

    # -----------------------------
    # Señales
    # -----------------------------
    def _on_selection_event(self, _):
        self._events.append(f"[{datetime.now().strftime('%H:%M:%S')}] Selección cambiada")
        self.refresh()

    def _on_selection_count(self, count: int):
        self._title.setText(f"Mapa de código — Selección ({count})")

    def _on_graph_eval(self):
        self._events.append(f"[{datetime.now().strftime('%H:%M:%S')}] Grafo evaluado")
        self.refresh()

    def _on_editing_exited(self, node):
        try:
            title = str(getattr(node, 'title', 'Node'))
        except Exception:
            title = 'Node'
        self._events.append(f"[{datetime.now().strftime('%H:%M:%S')}] Edición cerrada: {title}")
        self.refresh()

    # -----------------------------
    # Helpers
    # -----------------------------
    def _selected_nodes(self) -> list[NodeItem]:
        try:
            return [it for it in (self._view._scene.selectedItems() if hasattr(self._view, '_scene') else []) if isinstance(it, NodeItem)]
        except Exception:
            return []

    def _is_python(self, content: str) -> bool:
        if not content:
            return False
        c = content.strip()
        # Heurística simple para Python
        if "#include" in c or ";" in c:
            # probablemente C/C++
            return False
        if any(tok in c for tok in ("def ", "import ", "print(", "class ", "#")):
            return True
        # Fallback: si no hay llaves y predominan saltos/indent, asumir Python
        if "{" not in c and "}" not in c:
            return True
        return False

    def _connections_between(self, a: NodeItem, b: NodeItem) -> list[ConnectionItem]:
        conns: list[ConnectionItem] = []
        try:
            for c in (getattr(a, 'connections', []) or []):
                if isinstance(c, ConnectionItem) and (c.end_item is b or c.start_item is b):
                    conns.append(c)
        except Exception:
            pass
        try:
            for c in (getattr(b, 'connections', []) or []):
                if isinstance(c, ConnectionItem) and (c.end_item is a or c.start_item is a):
                    conns.append(c)
        except Exception:
            pass
        # Devolver únicos
        uniq = []
        seen = set()
        for c in conns:
            if id(c) not in seen:
                seen.add(id(c))
                uniq.append(c)
        return uniq

    # -----------------------------
    # Refresco principal
    # -----------------------------
    def refresh(self) -> None:
        sel = self._selected_nodes()
        if not sel:
            self._meta_title.setText("Nodo: —")
            self._meta_lang.setText("Lenguaje: —")
            self._code_label.setText("Código:")
            self._text.setPlainText("Selecciona 1 o 2 nodos para ver el mapa de código.")
            self._outline_text.setPlainText("")
            self._timeline_text.setPlainText("\n".join(self._events[-50:]))
            return
        if len(sel) > 2:
            self._meta_title.setText("Nodo: —")
            self._meta_lang.setText("Lenguaje: —")
            self._code_label.setText("Código:")
            self._text.setPlainText("Hay más de 2 nodos seleccionados. Limita la selección a 1 o 2 para ver la composición.")
            self._outline_text.setPlainText("")
            self._timeline_text.setPlainText("\n".join(self._events[-50:]))
            return

        # Un único nodo: mostrar su código y diagnóstico
        # Determinar modo
        solo_mode = self._btn_solo.isChecked()

        if len(sel) == 1 or solo_mode:
            n = sel[0]
            lines: list[str] = []
            title = str(getattr(n, 'title', 'Node'))
            ntype = str(getattr(n, 'node_type', 'generic'))
            content = str(getattr(n, 'content', '') or '')
            is_py = self._is_python(content)
            # Meta
            self._meta_title.setText(f"Nodo: {title} [{ntype}]")
            self._meta_lang.setText(f"Lenguaje: {'Python' if is_py else 'Otro (mostrando texto)'}")
            self._code_label.setText("Código:")
            if content.strip():
                preview = content.splitlines()
                # Mostrar las primeras 24 líneas
                if self._btn_bullets.isChecked():
                    lines.extend(self._format_code_lines(preview[:24]))
                else:
                    for ln in preview[:24]:
                        lines.append(f"  {ln}")
                if len(preview) > 24:
                    lines.append("  …")
            # Outline: puertos y conexiones
            outline = []
            try:
                outline.append("Puertos:")
                for p in (getattr(n, 'input_ports', []) or []):
                    name = p.get('name', 'input')
                    cnt = n.port_connection_count(name, 'input')
                    outline.append(f"  IN {name}: {cnt} conexión(es)")
                for p in (getattr(n, 'output_ports', []) or []):
                    name = p.get('name', 'output')
                    cnt = n.port_connection_count(name, 'output')
                    outline.append(f"  OUT {name}: {cnt} conexión(es)")
                # Conexiones entrantes/salientes
                outline.append("Conexiones:")
                for c in (getattr(n, 'connections', []) or []):
                    try:
                        src = getattr(c, 'start_item', None)
                        dst = getattr(c, 'end_item', None)
                        if src is n:
                            outline.append(f"  OUT {c.start_port} → {getattr(dst,'title','?')}:{c.end_port} [{getattr(c,'logic_name','passthrough')}]")
                        elif dst is n:
                            outline.append(f"  IN {c.end_port} ← {getattr(src,'title','?')}:{c.start_port} [{getattr(c,'logic_name','passthrough')}]")
                    except Exception:
                        pass
            except Exception:
                pass
            self._text.setPlainText("\n".join(lines))
            self._outline_text.setPlainText("\n".join(outline))
            self._timeline_text.setPlainText("\n".join(self._events[-50:]))
            return

        # Dos nodos y modo doble: mostrar composición
        a, b = sel[0], sel[1]
        title_a = str(getattr(a, 'title', 'A'))
        title_b = str(getattr(b, 'title', 'B'))
        code_a = str(getattr(a, 'content', '') or '')
        code_b = str(getattr(b, 'content', '') or '')
        is_py_a = self._is_python(code_a)
        is_py_b = self._is_python(code_b)

        # Meta para composición
        self._meta_title.setText(f"COMPOSE: {title_a} → {title_b}")
        self._meta_lang.setText(f"Lenguajes: A={'Python' if is_py_a else 'Otro'} | B={'Python' if is_py_b else 'Otro'}")
        self._code_label.setText("Composición y código A/B:")

        lines = []

        # Conexiones y lógica entre A y B
        conns = self._connections_between(a, b)
        if conns:
            lines.append("Conectores entre A y B:")
            for c in conns:
                try:
                    src = getattr(c, 'start_item', None)
                    dst = getattr(c, 'end_item', None)
                    src_name = 'A' if src is a else ('B' if src is b else '?')
                    dst_name = 'A' if dst is a else ('B' if dst is b else '?')
                    logic = str(getattr(c, 'logic_name', 'passthrough'))
                    cfg = dict(getattr(c, 'logic_config', {}) or {})
                    cfg_preview = ", ".join(f"{k}={repr(v)}" for k, v in cfg.items()) if cfg else "(sin config)"
                    lines.append(f"  {src_name}.{c.start_port} -> {dst_name}.{c.end_port} | lógica={logic} {cfg_preview}")
                except Exception:
                    pass
        else:
            lines.append("(No hay conexión directa; mostrando composición conceptual)")

        # Vista de combinación de código (conceptual). Solo se muestra si ambos parecen Python.
        if is_py_a and is_py_b:
            lines.append("")
            lines.append("# Pseudocódigo de composición (Python)")
            lines.append("def _node_a():")
            for ln in code_a.splitlines()[:12]:
                lines.append(f"    # {ln}")
            lines.append("    return 'out_a'  # ejemplar")
            lines.append("")
            lines.append("def _node_b(inp):")
            for ln in code_b.splitlines()[:12]:
                lines.append(f"    # {ln}")
            lines.append("    return f'processed({inp})'  # ejemplar")
            lines.append("")
            lines.append("res = _node_b(_node_a())")
            lines.append("print(res)")
        else:
            lines.append("")
            lines.append("# Notas:")
            lines.append("- La composición en tiempo real prioriza nodos con código Python.")
            lines.append("- Si alguno no es Python, se muestra diagnóstico de conectores y contenido.")

        # Outline compuesto
        outline = []
        try:
            outline.append("Puertos A:")
            for p in (getattr(a, 'output_ports', []) or []):
                outline.append(f"  OUT {p.get('name','output')}")
            outline.append("Puertos B:")
            for p in (getattr(b, 'input_ports', []) or []):
                outline.append(f"  IN {p.get('name','input')}")
            outline.append("Conexiones A-B:")
            for c in conns:
                outline.append(f"  {getattr(c,'start_port','out')} → {getattr(c,'end_port','in')} [{getattr(c,'logic_name','passthrough')}]")
        except Exception:
            pass

        self._text.setPlainText("\n".join(lines))
        self._outline_text.setPlainText("\n".join(outline))
        self._timeline_text.setPlainText("\n".join(self._events[-50:]))

    def _format_code_lines(self, lines: list[str]) -> list[str]:
        """Formatea cada línea como viñeta para mejorar la lectura.
        Prefija con '  • ' manteniendo el contenido intacto.
        """
        return [f"  • {ln}" for ln in lines]

    # -----------------------------
    # Construcción de secciones colapsables
    # -----------------------------
    def _make_section(self, title: str):
        btn = QtWidgets.QToolButton(self)
        btn.setText(title)
        btn.setCheckable(True)
        btn.setChecked(True)
        btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        btn.setArrowType(QtCore.Qt.DownArrow)
        btn.setStyleSheet(
            "QToolButton{background:#0f1318;color:#cbd5e1;border-top:1px solid #202a36;padding:6px 10px;text-align:left;}"
        )
        container = QtWidgets.QFrame(self)
        container.setObjectName(f"cm{title}Container")
        container.setStyleSheet("QFrame{background:#0f1318;border-bottom:1px solid #202a36;}")
        v = QtWidgets.QVBoxLayout(container)
        v.setContentsMargins(8, 6, 8, 8)
        v.setSpacing(6)
        text = QtWidgets.QPlainTextEdit(container)
        text.setReadOnly(True)
        text.setStyleSheet("QPlainTextEdit{background:#0f172a;color:#e2e8f0;border:1px solid #202a36;padding:6px;border-radius:6px;}")
        v.addWidget(text)

        def _toggle(_checked: bool):
            container.setVisible(_checked)
            btn.setArrowType(QtCore.Qt.DownArrow if _checked else QtCore.Qt.RightArrow)
        btn.toggled.connect(_toggle)
        container.setVisible(True)
        return btn, container, text


__all__ = ["CodeMapPanel"]