from typing import Dict, List, Any
from .node_item import NodeItem
from .connection_item import ConnectionItem


class GraphRuntime:
    """Runtime sencillo de dataflow para el editor de nodos.

    - Mantiene un mapa de conexiones (start -> end) con nombres de puertos.
    - Propaga valores desde los puertos de salida de cada nodo hacia los puertos de entrada conectados.
    - Invoca `compute_output_values()` en cada nodo para obtener los valores actuales.
    - Itera algunas veces hasta estabilizar (evita ciclos infinitos con límite de iteraciones).
    """

    def __init__(self, view=None):
        self.view = view
        self._connections: List[ConnectionItem] = []

    def rebuild_from_view(self):
        """Reconstruye el mapa de conexiones a partir de `view.connections`."""
        self._connections.clear()
        if not self.view:
            return
        try:
            for c in getattr(self.view, 'connections', []) or []:
                if getattr(c, 'start_item', None) and getattr(c, 'end_item', None):
                    self._connections.append(c)
        except Exception:
            pass

    def evaluate_all(self, max_iters: int = 8):
        """Evalúa y propaga el grafo completo.

        - Llama a `compute_output_values()` de cada nodo para obtener sus salidas.
        - Propaga a través de las conexiones hacia `receive_input_value()` del nodo destino.
        - Repite hasta que no haya cambios o se alcance `max_iters`.
        """
        if not self.view:
            return

        # Recolectar nodos: sólo instancias de NodeItem para evitar introspección costosa
        try:
            nodes = [it for it in self.view._scene.items() if isinstance(it, NodeItem)]
        except Exception:
            nodes = []

        def _snapshot_inputs() -> Dict[Any, Dict[str, Any]]:
            snap: Dict[Any, Dict[str, Any]] = {}
            for n in nodes:
                try:
                    snap[n] = dict(getattr(n, 'input_values', {}) or {})
                except Exception:
                    snap[n] = {}
            return snap

        last_inputs = _snapshot_inputs()

        # Reiniciar inputs en nodos Output para evitar duplicados entre evaluaciones
        try:
            for n in nodes:
                if str(getattr(n, 'node_type', '')).lower() in ('output', 'group_output'):
                    setattr(n, 'input_values', {})
        except Exception:
            pass

        for _ in range(max_iters):
            # Calcular salidas solo de nodos que lo necesiten (lazy)
            for n in nodes:
                try:
                    # Decidir si recomputar
                    recompute = bool(getattr(n, 'is_dirty', True))
                    try:
                        current_sig = n._inputs_signature() if hasattr(n, '_inputs_signature') else None
                        last_sig = getattr(n, '_last_inputs_hash', None)
                        if current_sig is not None and current_sig != last_sig:
                            recompute = True
                    except Exception:
                        pass
                    # Asegurar primera computación si no hay cache
                    if not isinstance(getattr(n, '_output_cache', None), dict):
                        recompute = True
                    if recompute:
                        outputs = n.compute_output_values()
                        if isinstance(outputs, dict):
                            n.output_values = outputs
                except Exception:
                    # Ignorar nodos que fallen al computar
                    pass

            # Propagar por las conexiones
            changed = False
            for conn in list(self._connections):
                try:
                    start = getattr(conn, 'start_item', None)
                    end = getattr(conn, 'end_item', None)
                    start_port = getattr(conn, 'start_port', 'output')
                    end_port = getattr(conn, 'end_port', 'input')
                    val = None
                    if hasattr(start, 'output_values'):
                        val = (start.output_values or {}).get(start_port, None)
                    # Fallback: sólo para nodos cuyo OUT es su contenido visible
                    # Evita inyectar el texto del nodo de tipo 'process' antes de calcular.
                    if val is None:
                        try:
                            start_type = str(getattr(start, 'node_type', '')).lower()
                        except Exception:
                            start_type = ''
                        if start_type in ('generic', 'input', 'variable', 'group_input', 'combine') and hasattr(start, 'to_plain_text'):
                            val = start.to_plain_text()
                    # Entregar al destino aplicando la lógica del conector
                    if hasattr(end, 'receive_input_value'):
                        prev = (end.input_values or {}).get(end_port, None)
                        try:
                            new_val = conn.apply_logic(prev, val) if hasattr(conn, 'apply_logic') else val
                        except Exception:
                            new_val = val
                        end.receive_input_value(end_port, new_val)
                        now = (end.input_values or {}).get(end_port, None)
                        # Pulso visual si el valor cambia
                        try:
                            if now != prev and hasattr(conn, 'pulse_on_value'):
                                conn.pulse_on_value()
                        except Exception:
                            pass
                        # Reflejar de inmediato en nodos Output/Group Output
                        try:
                            end_type = str(getattr(end, 'node_type', '')).lower()
                            if end_type in ('output', 'group_output'):
                                if now is not None:
                                    text = None
                                    if isinstance(now, list):
                                        text = "\n".join([str(v) for v in now if v is not None])
                                    else:
                                        text = str(now)
                                    if text is not None and hasattr(end, 'update_from_text'):
                                        end.update_from_text(text)
                        except Exception:
                            pass
                        if now != prev:
                            changed = True
                except Exception:
                    # Conexión rota o nodos sin API
                    pass

            # Si no hubo cambios en inputs, estamos estables
            current_inputs = _snapshot_inputs()
            if current_inputs == last_inputs and not changed:
                break
            last_inputs = current_inputs

        # Post-procesado: permitir que nodos de tipo "output"/"group_output" reflejen valores combinados
        for n in nodes:
            try:
                if str(getattr(n, 'node_type', '')).lower() in ('output', 'group_output'):
                    # Si es snapshot, nunca sobrescribir su contenido
                    try:
                        if getattr(n, 'is_snapshot', False):
                            continue
                    except Exception:
                        pass
                    vals = []
                    try:
                        for v in (getattr(n, 'input_values', {}) or {}).values():
                            if v is None:
                                continue
                            if isinstance(v, list):
                                for sv in v:
                                    if sv is not None:
                                        vals.append(str(sv))
                            else:
                                vals.append(str(v))
                    except Exception:
                        pass
                    # Solo actualizar el contenido si hay valores entrantes.
                    # Si no hay entradas, mantener el contenido existente (permite nodos snapshot).
                    if vals:
                        combined = "\n".join(vals)
                        if hasattr(n, 'update_from_text'):
                            n.update_from_text(combined)
            except Exception:
                pass
        # Forzar repintado del viewport tras la evaluación
        try:
            if hasattr(self.view, 'viewport'):
                self.view.viewport().update()
        except Exception:
            pass