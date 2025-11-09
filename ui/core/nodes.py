"""ui.core.nodes

Basic node type and model definitions for Omega-Visual.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Node:
    id: str
    type: str
    title: Optional[str] = None
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)