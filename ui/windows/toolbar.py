"""ui.windows.toolbar

Top toolbar with basic actions.
"""
from dearpygui import dearpygui as dpg


def build_toolbar() -> int:
    with dpg.window(label="Toolbar", no_move=True, no_resize=True, height=60) as win_id:
        dpg.add_button(label="New", tag="btn_new")
        dpg.add_same_line()
        dpg.add_button(label="Save", tag="btn_save")
        dpg.add_same_line()
        status_text = dpg.add_text("WS: connecting...", tag="ws_status")
    return win_id