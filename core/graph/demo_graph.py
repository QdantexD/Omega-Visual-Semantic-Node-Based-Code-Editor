from __future__ import annotations

from PySide6.QtCore import Qt, QPointF, QTimer, QSize


def build_demo_graph(view) -> None:
    """Crea el grafo demo Input->Process->Terminal y encuadra la vista.

    Extraído desde NodeView para mantener el archivo principal más limpio.
    """
    try:
        # Si hay nodos existentes, no hacer nada
        from .node_item import NodeItem  # import local para evitar ciclos en import
        existing = [it for it in view._scene.items() if isinstance(it, NodeItem)]
    except Exception:
        existing = []
    if existing:
        return

    try:
        specs = [
            {"title": "Input", "x": -300, "y": -80, "type": "input", "inputs": [], "outputs": ["output"], "content": "Hola"},
            {"title": "Process", "x": 40, "y": -20, "type": "process", "inputs": ["input"], "outputs": ["output"], "content": "input.upper()"},
            {"title": "Terminal", "x": 320, "y": 70, "type": "terminal", "inputs": ["input"], "outputs": ["output"], "content": ""},
        ]
        created = []
        for spec in specs:
            node = view.add_node_with_ports(
                title=spec["title"], x=spec["x"], y=spec["y"], node_type=spec["type"],
                inputs=spec["inputs"], outputs=spec["outputs"], content=spec.get("content", ""), record_undo=False
            )
            if node:
                created.append(node)

        # Conectar
        try:
            inp = next((n for n in created if getattr(n, 'node_type', '') == 'input'), None)
            proc = next((n for n in created if getattr(n, 'node_type', '') == 'process'), None)
            out = next((n for n in created if getattr(n, 'node_type', '') == 'terminal'), None)
            if inp and proc:
                view.add_connection(inp, proc, start_port=(inp.output_ports[0]['name'] if inp.output_ports else 'output'), end_port=(proc.input_ports[0]['name'] if proc.input_ports else 'input'), record_undo=False)
            if proc and out:
                view.add_connection(proc, out, start_port=(proc.output_ports[0]['name'] if proc.output_ports else 'output'), end_port=(out.input_ports[0]['name'] if out.input_ports else 'input'), record_undo=False)
        except Exception:
            pass

        # Encadrar
        try:
            if created:
                combined = created[0].sceneBoundingRect()
                for it in created[1:]:
                    combined = combined.united(it.sceneBoundingRect())
                pad = max(60.0, max(combined.width(), combined.height()) * 0.15)
                padded = combined.adjusted(-pad, -pad, pad, pad)
                old_anchor = view.transformationAnchor()
                view.setTransformationAnchor(view.AnchorViewCenter)
                view.fitInView(padded, view.KeepAspectRatio)
                view.setTransformationAnchor(old_anchor)
                view._zoom = 0
                try:
                    view.zoomChanged.emit(float(view.transform().m11()))
                except Exception:
                    pass
        except Exception:
            pass

        # Evaluar
        try:
            view.evaluate_graph()
        except Exception:
            pass
    except Exception:
        # Evitar bloquear la app por demo
        pass


__all__ = ["build_demo_graph"]