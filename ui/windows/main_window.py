"""ui.windows.main_window

Main window layout with a node editor canvas.
"""
from dearpygui import dearpygui as dpg


def build_main_window() -> tuple[int, int]:
    with dpg.window(label="Omega-Visual", width=900, height=700, pos=(0, 60)) as win_id:
        editor_id = dpg.add_node_editor(tag="node_editor")
    return win_id, editor_id