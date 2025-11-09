"""ui.core.links

Graph link model for Omega-Visual.
"""
from dataclasses import dataclass


@dataclass
class Link:
    start_node: str
    start_port: str
    end_node: str
    end_port: str