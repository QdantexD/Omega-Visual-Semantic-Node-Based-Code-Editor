"""ui.windows.properties_panel

Right-side properties panel.
"""
from dearpygui import dearpygui as dpg


def build_properties_panel() -> int:
    with dpg.window(label="Properties", width=280, pos=(920, 60)) as win_id:
        dpg.add_text("Select a node to view properties")
        dpg.add_separator()
        dpg.add_input_text(label="Title", tag="prop_title")
        dpg.add_input_text(label="Type", tag="prop_type")
    return win_id