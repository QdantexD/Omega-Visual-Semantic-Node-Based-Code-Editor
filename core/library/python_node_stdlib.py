"""
Python Node Standard Library
----------------------------

Biblioteca integral para un editor visual de nodos en Python.

- Tipos y valores por defecto
- Variables específicas de nodo (contexto)
- Funciones básicas, matemáticas y de cadenas
- Operadores envueltos como funciones
- Plantillas de estructuras de control (if/for/while/try)
- NodeTemplate: funciones modulares reutilizables
- Stub de conversión a VEX/Houdini (básico)

Esta biblioteca está pensada para ser importada y usada tanto
por nodos en tiempo de ejecución, como por generadores de código
que necesiten plantillas claras y comentadas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
import math


# =============================================================
# Sección 1: Tipos básicos y valores por defecto
# =============================================================

# Valores por defecto comunes
DEFAULT_INT: int = 0
DEFAULT_FLOAT: float = 0.0
DEFAULT_COMPLEX: complex = complex(0.0, 0.0)
DEFAULT_BOOL: bool = False
DEFAULT_STR: str = ""
DEFAULT_LIST: List[Any] = []
DEFAULT_TUPLE: Tuple[Any, ...] = tuple()
DEFAULT_SET: set = set()
DEFAULT_DICT: Dict[str, Any] = {}

# Constantes matemáticas comunes
PI: float = math.pi
E: float = math.e
TAU: float = math.tau

# Mapa de defaults por tipo (útil para generadores de nodos)
DEFAULTS: Dict[str, Any] = {
    "int": DEFAULT_INT,
    "float": DEFAULT_FLOAT,
    "complex": DEFAULT_COMPLEX,
    "bool": DEFAULT_BOOL,
    "str": DEFAULT_STR,
    "list": DEFAULT_LIST,
    "tuple": DEFAULT_TUPLE,
    "set": DEFAULT_SET,
    "dict": DEFAULT_DICT,
    "PI": PI,
    "E": E,
    "TAU": TAU,
}


# =============================================================
# Sección 2: Variables específicas de nodo (Contexto)
# =============================================================

@dataclass
class NodeContext:
    """Contexto básico para un nodo en el editor visual.

    - node_id: identificador único del nodo
    - node_name: nombre legible del nodo
    - node_inputs: nombres/valores de puertos de entrada
    - node_outputs: nombres/valores de puertos de salida
    - node_parameters: parámetros configurables del nodo
    - input_flow: historial o buffer de entrada (para nodos stream)
    - output_flow: historial o buffer de salida
    """

    node_id: str = ""
    node_name: str = "Node"
    node_inputs: Dict[str, Any] = field(default_factory=dict)
    node_outputs: Dict[str, Any] = field(default_factory=dict)
    node_parameters: Dict[str, Any] = field(default_factory=dict)
    input_flow: List[Any] = field(default_factory=list)
    output_flow: List[Any] = field(default_factory=list)

    def get_input(self, name: str, default: Any = None) -> Any:
        return self.node_inputs.get(name, default)

    def set_output(self, name: str, value: Any) -> None:
        self.node_outputs[name] = value
        self.output_flow.append(value)


# =============================================================
# Sección 3: Funciones básicas
# =============================================================

def identity(x: Any) -> Any:
    """Retorna el mismo valor que recibe."""
    return x


def coalesce(x: Any, default: Any) -> Any:
    """Retorna x si no es None; en caso contrario default."""
    return x if x is not None else default


def clamp(x: float, lo: float, hi: float) -> float:
    """Limita x al rango [lo, hi]."""
    return max(lo, min(hi, x))


def ensure_list(x: Any) -> List[Any]:
    """Devuelve x como lista; si ya es lista, la retorna tal cual."""
    return x if isinstance(x, list) else [x]


# =============================================================
# Sección 4: Operadores como funciones (aritm., lógicos, comp.)
# =============================================================

# Aritméticos
def op_add(a: Any, b: Any) -> Any: return a + b
def op_sub(a: Any, b: Any) -> Any: return a - b
def op_mul(a: Any, b: Any) -> Any: return a * b
def op_div(a: Any, b: Any) -> Any: return a / b
def op_mod(a: Any, b: Any) -> Any: return a % b

# Lógicos
def op_and(a: bool, b: bool) -> bool: return a and b
def op_or(a: bool, b: bool) -> bool: return a or b
def op_not(a: bool) -> bool: return not a

# Comparación
def op_eq(a: Any, b: Any) -> bool: return a == b
def op_ne(a: Any, b: Any) -> bool: return a != b
def op_gt(a: Any, b: Any) -> bool: return a > b
def op_lt(a: Any, b: Any) -> bool: return a < b
def op_ge(a: Any, b: Any) -> bool: return a >= b
def op_le(a: Any, b: Any) -> bool: return a <= b


# =============================================================
# Sección 5: Funciones matemáticas
# =============================================================

def math_add(a: float, b: float) -> float: return a + b
def math_sub(a: float, b: float) -> float: return a - b
def math_mul(a: float, b: float) -> float: return a * b
def math_div(a: float, b: float) -> float: return a / b
def math_pow(a: float, b: float) -> float: return math.pow(a, b)
def math_sqrt(x: float) -> float: return math.sqrt(x)
def math_sin(x: float) -> float: return math.sin(x)
def math_cos(x: float) -> float: return math.cos(x)
def math_tan(x: float) -> float: return math.tan(x)
def math_log(x: float, base: float = math.e) -> float:
    return math.log(x, base) if base != math.e else math.log(x)
def math_exp(x: float) -> float: return math.exp(x)
def math_round(x: float, ndigits: Optional[int] = None) -> float:
    return round(x, ndigits) if ndigits is not None else round(x)


# =============================================================
# Sección 6: Funciones de cadenas
# =============================================================

def str_upper(s: str) -> str: return str(s).upper()
def str_lower(s: str) -> str: return str(s).lower()
def str_title(s: str) -> str: return str(s).title()
def str_strip(s: str) -> str: return str(s).strip()
def str_replace(s: str, old: str, new: str) -> str: return str(s).replace(old, new)
def str_join(items: Iterable[Any], sep: str = "\n") -> str:
    return sep.join(str(x) for x in items)
def str_split(s: str, sep: Optional[str] = None) -> List[str]:
    return str(s).split(sep) if sep is not None else str(s).split()


# =============================================================
# Sección 7: Condicionales y bucles como funciones
# =============================================================

def if_else(cond: bool, a: Any, b: Any) -> Any:
    """Retorna a si cond es True; en caso contrario b."""
    return a if cond else b


def for_each(items: Iterable[Any], fn: Callable[[Any], Any]) -> List[Any]:
    """Aplica fn a cada elemento y retorna la lista de resultados."""
    return [fn(x) for x in items]


def while_loop(init: Any, step: Callable[[Any], Any], stop: Callable[[Any], bool], limit: int = 1000) -> Any:
    """Bucle while seguro con límite de iteraciones."""
    x = init
    count = 0
    while not stop(x) and count < limit:
        x = step(x)
        count += 1
    return x


def try_call(fn: Callable[[], Any], catch: Optional[Callable[[Exception], Any]] = None) -> Any:
    """Ejecuta fn. Si falla, retorna catch(ex) o None."""
    try:
        return fn()
    except Exception as ex:
        return catch(ex) if catch else None


# =============================================================
# Sección 8: Plantillas de estructuras de control (strings)
# =============================================================

def tpl_if_else(condition: str, then_expr: str, else_expr: str) -> str:
    """Plantilla de if/else como código Python."""
    return (
        "if " + condition + ":\n"
        "    result = " + then_expr + "\n"
        "else:\n"
        "    result = " + else_expr + "\n"
    )


def tpl_for_loop(var: str, iterable: str, body_expr: str) -> str:
    """Plantilla de for simple que acumula en results."""
    return (
        "results = []\n"
        f"for {var} in {iterable}:\n"
        f"    results.append({body_expr})\n"
    )


def tpl_while_loop(init: str, step_expr: str, stop_cond: str, limit_var: str = "_limit") -> str:
    """Plantilla de while con límite de seguridad."""
    return (
        f"x = {init}\n"
        f"{limit_var} = 1000\n"
        "count = 0\n"
        f"while not ({stop_cond}) and count < {limit_var}:\n"
        f"    x = {step_expr}\n"
        "    count += 1\n"
    )


def tpl_try_except(body_expr: str, except_expr: str = "None") -> str:
    """Plantilla try/except que asigna a result."""
    return (
        "try:\n"
        f"    result = {body_expr}\n"
        "except Exception:\n"
        f"    result = {except_expr}\n"
    )


# =============================================================
# Sección 9: NodeTemplate y nodos reutilizables
# =============================================================

@dataclass
class NodeTemplate:
    """Plantilla modular de nodo Python.

    - name: nombre del nodo
    - inputs: nombres de entradas
    - outputs: nombres de salidas
    - parameters: parámetros configurables
    - python: función Python que implementa la lógica
    - description: texto de ayuda
    """

    name: str
    inputs: Sequence[str]
    outputs: Sequence[str]
    parameters: Dict[str, Any] = field(default_factory=dict)
    python: Optional[Callable[..., Dict[str, Any]]] = None
    description: str = ""

    def run(self, ctx: Optional[NodeContext] = None, **kwargs) -> Dict[str, Any]:
        """Ejecuta la función Python con parámetros y devuelve dict de salidas."""
        if not self.python:
            return {}
        return self.python(ctx, **kwargs)

    # --- Conversión básica a VEX/Houdini (stub) ---
    def to_vex(self) -> str:
        """Convierte el nodo a un snippet VEX simple si aplica.

        Nota: Este stub cubre operaciones básicas; editores avanzados
        deberán implementar conversiones específicas según el tipo.
        """
        name = self.name.lower()
        if name in {"add", "sum"} and set(self.inputs) >= {"a", "b"}:
            return "float result = a + b;"
        if name in {"multiply", "mul"} and set(self.inputs) >= {"a", "b"}:
            return "float result = a * b;"
        if name in {"uppercase", "str_upper"} and set(self.inputs) >= {"s"}:
            return "string result = uppercase(s);"  # Representativo
        # Fallback genérico
        return "// VEX: conversión no definida para este nodo\n"


# --- Ejemplos de nodos reutilizables ---

def _node_add_py(_ctx: Optional[NodeContext], a: float, b: float) -> Dict[str, Any]:
    """Suma dos números y retorna {'result': a+b}."""
    return {"result": float(a) + float(b)}


def _node_upper_py(_ctx: Optional[NodeContext], s: Any) -> Dict[str, Any]:
    """Convierte a mayúsculas y retorna {'result': str(s).upper()}."""
    return {"result": str(s).upper()}


def _node_map_py(_ctx: Optional[NodeContext], items: Iterable[Any], fn: Callable[[Any], Any]) -> Dict[str, Any]:
    """Aplica fn a cada elemento y retorna lista en 'result'."""
    return {"result": [fn(x) for x in items]}


def _node_filter_py(_ctx: Optional[NodeContext], items: Iterable[Any], pred: Callable[[Any], bool]) -> Dict[str, Any]:
    """Filtra elementos que cumplen predicado y retorna lista en 'result'."""
    return {"result": [x for x in items if pred(x)]}


def _node_combine_py(_ctx: Optional[NodeContext], items: Iterable[Any], sep: str = "\n") -> Dict[str, Any]:
    """Concatena elementos con separador y retorna cadena en 'result'."""
    return {"result": sep.join(str(x) for x in items)}


NODE_ADD = NodeTemplate(
    name="Add",
    inputs=["a", "b"],
    outputs=["result"],
    parameters={},
    python=_node_add_py,
    description="Suma dos números (a + b).",
)

NODE_UPPER = NodeTemplate(
    name="Uppercase",
    inputs=["s"],
    outputs=["result"],
    parameters={},
    python=_node_upper_py,
    description="Convierte una cadena a mayúsculas.",
)

NODE_MAP = NodeTemplate(
    name="MapList",
    inputs=["items", "fn"],
    outputs=["result"],
    parameters={},
    python=_node_map_py,
    description="Aplica una función a cada elemento de la lista.",
)

NODE_FILTER = NodeTemplate(
    name="FilterList",
    inputs=["items", "pred"],
    outputs=["result"],
    parameters={},
    python=_node_filter_py,
    description="Filtra elementos según un predicado.",
)

NODE_COMBINE = NodeTemplate(
    name="CombineText",
    inputs=["items", "sep"],
    outputs=["result"],
    parameters={"sep": "\n"},
    python=_node_combine_py,
    description="Concatena elementos con un separador.",
)


# =============================================================
# Sección 10: Export público
# =============================================================

__all__ = [
    # Defaults & consts
    "DEFAULT_INT", "DEFAULT_FLOAT", "DEFAULT_COMPLEX", "DEFAULT_BOOL", "DEFAULT_STR",
    "DEFAULT_LIST", "DEFAULT_TUPLE", "DEFAULT_SET", "DEFAULT_DICT", "PI", "E", "TAU",
    "DEFAULTS",
    # Context
    "NodeContext",
    # Básicas
    "identity", "coalesce", "clamp", "ensure_list",
    # Operadores
    "op_add", "op_sub", "op_mul", "op_div", "op_mod",
    "op_and", "op_or", "op_not",
    "op_eq", "op_ne", "op_gt", "op_lt", "op_ge", "op_le",
    # Matemáticas
    "math_add", "math_sub", "math_mul", "math_div", "math_pow", "math_sqrt",
    "math_sin", "math_cos", "math_tan", "math_log", "math_exp", "math_round",
    # Cadenas
    "str_upper", "str_lower", "str_title", "str_strip", "str_replace", "str_join", "str_split",
    # Funcionales y control
    "if_else", "for_each", "while_loop", "try_call",
    # Plantillas
    "tpl_if_else", "tpl_for_loop", "tpl_while_loop", "tpl_try_except",
    # Node templates
    "NodeTemplate", "NODE_ADD", "NODE_UPPER", "NODE_MAP", "NODE_FILTER", "NODE_COMBINE",
]


# =============================================================
# Sección 11: Catálogo de plantillas Python para la paleta de nodos
# =============================================================

def get_python_catalog() -> Dict[str, List[Dict[str, Any]]]:
    """Devuelve un catálogo sencillo de snippets/plantillas Python.

    Cada entrada tiene: name, description, template (código sugerido).
    Se organiza por categorías: "Strings", "Math", "Control", "Funciones".
    """
    base = [
        {"name": "Input", "description": "Entrada básica de Python", "template": "", "node_type": "input"},
        {"name": "Process", "description": "Proceso básico Python", "template": "output = input", "node_type": "process"},
        {"name": "Output", "description": "Salida con ejecución de código", "template": "print(input)\n# Usa variables conectadas (p.ej. nombre, edad)\noutput = str(input)", "node_type": "output"},
    ]
    strings = [
        {"name": "str.upper", "description": "Mayúsculas", "template": "output = str(input).upper()"},
        {"name": "str.lower", "description": "Minúsculas", "template": "output = str(input).lower()"},
        {"name": "str.replace", "description": "Reemplazar texto", "template": "output = str(input).replace('old', 'new')"},
        {"name": "str.join", "description": "Unir lista con separador", "template": "output = '\\n'.join(map(str, input if isinstance(input, (list, tuple)) else [input]))"},
        {"name": "f-string", "description": "Formato f-string", "template": "output = f'Valor: {input}'"},
    ]

    math_cat = [
        {"name": "add 1", "description": "Suma 1 al número", "template": "output = float(input) + 1"},
        {"name": "round", "description": "Redondear", "template": "output = round(float(input))"},
        {"name": "clamp", "description": "Limitar a [0,1]", "template": "output = clamp(float(input), 0.0, 1.0)"},
    ]

    control = [
        {"name": "if/else", "description": "Condicional básico", "template": "\n" + tpl_if_else("bool(input)", "str(input)", "'sin valor'")},
        {"name": "for", "description": "Bucle sobre lista", "template": "\n" + tpl_for_loop("x", "input if isinstance(input, (list, tuple)) else [input]", "x")},
        {"name": "while", "description": "Bucle con límite", "template": "\n" + tpl_while_loop("0", "x+1", "x>=10")},
        {"name": "try/except", "description": "Captura de errores", "template": "\n" + tpl_try_except("int(input)", "None")},
    ]

    funciones = [
        {"name": "def process", "description": "Función estándar con input", "template": "def process(input):\n    return input\n"},
        {"name": "lambda", "description": "Lambda como process", "template": "process = lambda input: input"},
        {"name": "list comprehension", "description": "Comprensión de listas", "template": "output = [x for x in (input if isinstance(input, (list, tuple)) else [input])]"},
    ]

    return {
        "Base": base,
        "Strings": strings,
        "Math": math_cat,
        "Control": control,
        "Funciones": funciones,
    }

__all__.append("get_python_catalog")