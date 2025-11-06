from __future__ import annotations

from typing import Any, Dict, Optional


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


LOGIC_REGISTRY = {
    "passthrough": PassthroughLogic(),
    "list": ListAccumLogic(),
    "unique": UniqueListLogic(),
    "concat": ConcatLogic(),
    "switch": SwitchLogic(),
}


def get_logic(name: str) -> BaseLogic:
    return LOGIC_REGISTRY.get(str(name or "passthrough").lower(), LOGIC_REGISTRY["passthrough"])