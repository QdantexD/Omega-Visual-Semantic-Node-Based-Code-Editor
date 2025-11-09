"""ui.core.events

User event handlers (drag, drop, click) stubs for Omega-Visual.
"""
from typing import Callable


class Events:
    def __init__(self):
        self.on_node_added: Callable[[str], None] | None = None
        self.on_link_created: Callable[[str, str, str, str], None] | None = None

    def emit_node_added(self, node_id: str):
        if self.on_node_added:
            self.on_node_added(node_id)

    def emit_link_created(self, a_node: str, a_port: str, b_node: str, b_port: str):
        if self.on_link_created:
            self.on_link_created(a_node, a_port, b_node, b_port)