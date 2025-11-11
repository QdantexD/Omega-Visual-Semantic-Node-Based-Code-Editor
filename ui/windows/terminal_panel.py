"""ui.windows.terminal_panel

Terminal básica integrada estilo VS Code.
"""
from dearpygui import dearpygui as dpg


def build_terminal_panel() -> int:
    with dpg.window(label="Output Log", width=900, height=220, pos=(0, 540)) as win_id:
        dpg.add_text("> Compilando...")
        dpg.add_input_text(tag="terminal_input", multiline=True, height=160, width=-1)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Limpiar", tag="btn_terminal_clear", callback=lambda: dpg.set_value("terminal_input", ""))
            dpg.add_button(label="Ejecutar", tag="btn_terminal_run", callback=lambda: dpg.set_value("terminal_input", dpg.get_value("terminal_input")+"\n> Ejecutado"))
    # Theme for near-black background
    try:
        with dpg.theme() as _log_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (18, 18, 18, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (230, 230, 230, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (57, 255, 20, 160))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (57, 255, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (80, 255, 80, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (40, 200, 40, 255))
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 4.0)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8.0, 8.0)
        dpg.bind_item_theme(win_id, _log_theme)
    except Exception:
        pass

    # Tema específico de botones: texto negro sobre botón verde
    try:
        with dpg.theme() as _btn_black_text_theme:
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Text, (0, 0, 0, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (57, 255, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (80, 255, 80, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (40, 200, 40, 255))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4.0)
        for tag in ("btn_terminal_clear", "btn_terminal_run"):
            try:
                dpg.bind_item_theme(tag, _btn_black_text_theme)
            except Exception:
                pass
    except Exception:
        pass
    return win_id


def build_terminal_child(parent_id: int, height: int = 220) -> int:
    """Construye la consola de salida dentro de un child_window para el dockspace."""
    with dpg.child_window(height=height) as cid:
        dpg.add_text("> Compilando...")
        dpg.add_input_text(tag="terminal_input", multiline=True, height=height-60, width=-1)
        with dpg.group(horizontal=True):
            dpg.add_button(label="Limpiar", tag="btn_terminal_clear_child", callback=lambda: dpg.set_value("terminal_input", ""))
            dpg.add_button(label="Ejecutar", tag="btn_terminal_run_child", callback=lambda: dpg.set_value("terminal_input", dpg.get_value("terminal_input")+"\n> Ejecutado"))
    try:
        with dpg.theme() as _log_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (18, 18, 18, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (230, 230, 230, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (57, 255, 20, 160))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (57, 255, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (80, 255, 80, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (40, 200, 40, 255))
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 4.0)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8.0, 8.0)
        dpg.bind_item_theme(cid, _log_theme)
    except Exception:
        pass

    # Tema específico de botones en child: texto negro sobre botón verde
    try:
        with dpg.theme() as _btn_black_text_theme:
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Text, (0, 0, 0, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (57, 255, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (80, 255, 80, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (40, 200, 40, 255))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4.0)
        for tag in ("btn_terminal_clear_child", "btn_terminal_run_child"):
            try:
                dpg.bind_item_theme(tag, _btn_black_text_theme)
            except Exception:
                pass
    except Exception:
        pass
    return cid