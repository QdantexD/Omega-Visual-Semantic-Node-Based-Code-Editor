"""ui.widgets.socket_widget

Helpers for input/output sockets (node attributes).
"""
from dearpygui import dearpygui as dpg


def add_input_socket(node_id: int, label: str) -> int:
    with dpg.node_attribute(parent=node_id, attribute_type=dpg.mvNode_Attr_Input) as attr_id:
        dpg.add_text(label)
    return attr_id


def add_output_socket(node_id: int, label: str) -> int:
    with dpg.node_attribute(parent=node_id, attribute_type=dpg.mvNode_Attr_Output) as attr_id:
        dpg.add_text(label)
    return attr_id