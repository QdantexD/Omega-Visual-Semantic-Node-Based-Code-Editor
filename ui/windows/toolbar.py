"""ui.windows.toolbar

Top toolbar with basic actions.
"""
from dearpygui import dearpygui as dpg


def build_toolbar() -> int:
    with dpg.window(label="Toolbar", no_move=True, no_resize=True, height=60) as win_id:
        with dpg.group(horizontal=True):
            dpg.add_text("Node Type:")
            dpg.add_combo(items=["Compute", "Data", "Op"], default_value="Compute", width=120, tag="node_type")
            dpg.add_button(label="New", tag="btn_new")
            dpg.add_button(label="Duplicate", tag="btn_duplicate")
            dpg.add_button(label="Save", tag="btn_save")
            dpg.add_button(label="Load", tag="btn_load")
            dpg.add_spacer(width=20)
            dpg.add_text("WS: connecting...", tag="ws_status")
    return win_id