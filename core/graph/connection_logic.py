from __future__ import annotations

from typing import Any, Dict, Optional, Callable


class BaseLogic:
    def combine(self, prev: Any, incoming: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        return incoming


class PassthroughLogic(BaseLogic):
    pass


class ListAccumLogic(BaseLogic):
    def combine(self, prev: Any, incoming: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        if prev is None:
            return incoming if isinstance(incoming, list) else [incoming]
        if isinstance(prev, list):
            return prev + (incoming if isinstance(incoming, list) else [incoming])
        return [prev] + (incoming if isinstance(incoming, list) else [incoming])


class UniqueListLogic(BaseLogic):
    def combine(self, prev: Any, incoming: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        lst = []
        if prev is None:
            lst = []
        elif isinstance(prev, list):
            lst = list(prev)
        else:
            lst = [prev]
        items = incoming if isinstance(incoming, list) else [incoming]
        for it in items:
            if it not in lst:
                lst.append(it)
        return lst


class ConcatLogic(BaseLogic):
    def combine(self, prev: Any, incoming: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        delim = "\n"
        if config and isinstance(config.get("delimiter"), str):
            delim = config["delimiter"]
        if prev is None:
            prev_str = ""
        elif isinstance(prev, list):
            prev_str = delim.join(str(x) for x in prev if x is not None)
        else:
            prev_str = str(prev)
        in_items = incoming if isinstance(incoming, list) else [incoming]
        in_str = delim.join(str(x) for x in in_items if x is not None)
        if not prev_str:
            return in_str
        if not in_str:
            return prev_str
        return prev_str + (delim if not prev_str.endswith(delim) else "") + in_str


class SwitchLogic(BaseLogic):
    def combine(self, prev: Any, incoming: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        # Simple switch: si 'enabled' es False, mantiene prev; si True, usa incoming
        enabled = True
        if config and isinstance(config.get("enabled"), bool):
            enabled = config["enabled"]
        return incoming if enabled else prev


# --- Utilidades seguras para evaluación Python en conectores ---
def _safe_eval_expr(expr: str, local_vars: Dict[str, Any]) -> Any:
    """Evalúa una expresión Python de forma acotada.
    Provee un juego mínimo de builtins para evitar abuso.
    """
    if not isinstance(expr, str) or not expr.strip():
        return local_vars.get("value")
    safe_globals = {
        "__builtins__": {
            # numéricos y colecciones
            "len": len,
            "sum": sum,
            "min": min,
            "max": max,
            "sorted": sorted,
            "any": any,
            "all": all,
            # tipos
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "set": set,
        }
    }
    try:
        return eval(expr, safe_globals, dict(local_vars))
    except Exception:
        # fallback no ruidoso: devuelve el valor entrante
        return local_vars.get("value")


class LatestValueLogic(BaseLogic):
    """Devuelve el último valor no None (prioriza 'incoming')."""
    def combine(self, prev: Any, incoming: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        return incoming if incoming is not None else prev


class CoalesceLogic(BaseLogic):
    """Devuelve el primer valor no None entre prev e incoming."""
    def combine(self, prev: Any, incoming: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        return prev if prev is not None else incoming


class PythonEvalLogic(BaseLogic):
    """Evalúa una expresión sobre los valores del conector.

    Configuración:
      - expr: str, expresión Python usando variables 'value' (incoming) y 'prev'.
    """
    def combine(self, prev: Any, incoming: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        expr = (config or {}).get("expr")
        return _safe_eval_expr(str(expr or "value"), {"value": incoming, "prev": prev})


class PythonMapLogic(BaseLogic):
    """Aplica una transformación por elemento.

    Configuración:
      - func: str, expresión con variable 'x'. Si 'value' no es lista, se aplica directo.
    """
    def combine(self, prev: Any, incoming: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        func_expr = (config or {}).get("func")
        if not func_expr:
            return incoming
        mapper: Callable[[Any], Any] = lambda x: _safe_eval_expr(func_expr, {"x": x})
        if isinstance(incoming, list):
            try:
                return [mapper(x) for x in incoming]
            except Exception:
                return incoming
        try:
            return mapper(incoming)
        except Exception:
            return incoming


class PythonFilterLogic(BaseLogic):
    """Filtra elementos por predicado.

    Configuración:
      - pred: str, expresión booleana con variable 'x'.
    """
    def combine(self, prev: Any, incoming: Any, config: Optional[Dict[str, Any]] = None) -> Any:
        pred_expr = (config or {}).get("pred")
        if not pred_expr:
            return incoming
        predicate: Callable[[Any], bool] = lambda x: bool(_safe_eval_expr(pred_expr, {"x": x}))
        if isinstance(incoming, list):
            try:
                return [x for x in incoming if predicate(x)]
            except Exception:
                return incoming
        try:
            return incoming if predicate(incoming) else prev
        except Exception:
            return incoming


LOGIC_REGISTRY = {
    "passthrough": PassthroughLogic(),
    "list": ListAccumLogic(),
    "unique": UniqueListLogic(),
    "concat": ConcatLogic(),
    "switch": SwitchLogic(),
    # nuevas lógicas
    "latest": LatestValueLogic(),
    "coalesce": CoalesceLogic(),
    "py_eval": PythonEvalLogic(),
    "py_map": PythonMapLogic(),
    "py_filter": PythonFilterLogic(),
}


def get_logic(name: str) -> BaseLogic:
    return LOGIC_REGISTRY.get(str(name or "passthrough").lower(), LOGIC_REGISTRY["passthrough"])