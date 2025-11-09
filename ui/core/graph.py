"""ui.core.graph

Graph manager for Omega-Visual.
"""
from typing import Dict, List
from .nodes import Node
from .links import Link


class Graph:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.links: List[Link] = []

    def add_node(self, node: Node):
        self.nodes[node.id] = node

    def add_link(self, link: Link):
        self.links.append(link)

    def remove_node(self, node_id: str):
        self.nodes.pop(node_id, None)
        self.links = [l for l in self.links if l.start_node != node_id and l.end_node != node_id]

    def snapshot(self) -> Dict:
        return {
            "nodes": [
                {
                    "id": n.id,
                    "type": n.type,
                    "title": n.title,
                    "inputs": n.inputs,
                    "outputs": n.outputs,
                    "meta": n.meta,
                }
                for n in self.nodes.values()
            ],
            "links": [
                {
                    "from": {"node": l.start_node, "port": l.start_port},
                    "to": {"node": l.end_node, "port": l.end_port},
                }
                for l in self.links
            ],
        }