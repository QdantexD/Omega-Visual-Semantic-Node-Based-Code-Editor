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
    # Tema negro elegante con acento verde para la toolbar
    try:
        with dpg.theme() as _toolbar_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (18, 18, 18, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (230, 230, 230, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (57, 255, 20, 160))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (57, 255, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (80, 255, 80, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (40, 200, 40, 255))
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 4.0)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 6.0, 6.0)
        dpg.bind_item_theme(win_id, _toolbar_theme)
    except Exception:
        pass

    # Texto negro en botones de la toolbar (solo en estos items)
    try:
        with dpg.theme() as _toolbar_btn_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_Text, (0, 0, 0, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (57, 255, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (80, 255, 80, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (40, 200, 40, 255))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4.0)
        for tag in ("btn_new", "btn_duplicate", "btn_save", "btn_load"):
            try:
                dpg.bind_item_theme(tag, _toolbar_btn_theme)
            except Exception:
                pass
    except Exception:
        pass

    # Combo en verde con texto negro para contraste
    try:
        with dpg.theme() as _toolbar_combo_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_Text, (0, 0, 0, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (57, 255, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (80, 255, 80, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (40, 200, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (57, 255, 20, 180))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4.0)
        dpg.bind_item_theme("node_type", _toolbar_combo_theme)
    except Exception:
        pass
    return win_id