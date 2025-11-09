"""ui.widgets.link_widget

Helper to draw links between sockets.
"""
from dearpygui import dearpygui as dpg


def add_link(editor_id: int, start_attr: int, end_attr: int) -> int:
    return dpg.add_node_link(start_attr, end_attr, parent=editor_id)