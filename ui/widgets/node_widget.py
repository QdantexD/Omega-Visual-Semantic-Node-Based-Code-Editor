"""ui.widgets.node_widget

DearPyGui node widget helpers.
"""
from dearpygui import dearpygui as dpg


def add_node(editor_id: int, label: str, node_id: str) -> int:
    with dpg.node(label=label, parent=editor_id, tag=node_id) as n_id:
        pass
    return n_id