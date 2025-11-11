"""ui.windows.explorer_panel

Explorador de archivos estilo VS Code, conectado al filesystem.
"""
import os
import datetime
from dearpygui import dearpygui as dpg


EXPLORER_TREE_TAG = "explorer_tree_root"


def _open_file_in_editor(path: str):
    """Abre el archivo en una nueva pestaña del editor y actualiza Propiedades."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        # Muestra el error en la terminal si existe
        try:
            dpg.set_value("terminal_input", f"Error abriendo {path}: {e}\n")
        except Exception:
            pass
        return

    # Crear pestaña con contenido
    try:
        with dpg.tab(label=os.path.basename(path), parent="editor_tabbar"):
            dpg.add_input_text(multiline=True, width=-1, height=-1, default_value=content)
    except Exception:
        # Si no existe editor_tabbar, simplemente no hacemos nada
        pass

    # Actualizar panel de propiedades si existe
    nombre = os.path.basename(path)
    tipo = os.path.splitext(nombre)[1].lstrip(".") or "(sin extensión)"
    try:
        mod = os.path.getmtime(path)
        mod_str = datetime.datetime.fromtimestamp(mod).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        mod_str = "—"

    for tag, val in (("prop_title", nombre), ("prop_type", tipo), ("prop_id", path)):
        try:
            dpg.set_value(tag, val)
        except Exception:
            pass
    try:
        dpg.set_value("prop_hint", "Archivo abierto")
    except Exception:
        pass


def _add_dir_node(parent, dir_path: str, depth: int = 0, max_depth: int = 2):
    """Añade nodos de carpeta/archivo al árbol de Explorer."""
    if depth > max_depth:
        return
    label = os.path.basename(dir_path) or dir_path
    with dpg.tree_node(parent=parent, label=label, default_open=(depth == 0)):
        try:
            entries = sorted(os.listdir(dir_path))
        except Exception:
            entries = []
        for name in entries:
            p = os.path.join(dir_path, name)
            if os.path.isdir(p):
                _add_dir_node(dpg.last_item(), p, depth + 1, max_depth)
            else:
                dpg.add_selectable(label=name, callback=lambda s, a, u=p: _open_file_in_editor(u))


def _populate_explorer(root_path: str):
    """Llena el árbol del Explorer con el contenido de la carpeta raíz."""
    if not dpg.does_item_exist(EXPLORER_TREE_TAG):
        return
    children = dpg.get_item_children(EXPLORER_TREE_TAG, slot=0) or []
    for cid in children:
        dpg.delete_item(cid)
    _add_dir_node(EXPLORER_TREE_TAG, root_path, depth=0, max_depth=2)


def build_explorer_panel() -> int:
    with dpg.window(label="World Outliner", width=280, pos=(0, 60)) as win_id:
        dpg.add_text("📁 World Outliner")
        dpg.add_separator()
        with dpg.child_window(tag=EXPLORER_TREE_TAG, border=False):
            pass

    # Theme: negro elegante con acento verde
    try:
        with dpg.theme() as _outliner_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (20, 20, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (230, 230, 230, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (57, 255, 20, 180))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (57, 255, 20, 180))
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 4.0)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8.0, 8.0)
        dpg.bind_item_theme(win_id, _outliner_theme)
    except Exception:
        pass

    # Poblar con la carpeta actual del proyecto
    try:
        _populate_explorer(os.getcwd())
    except Exception:
        pass
    return win_id


def build_explorer_sidebar(parent_id: int) -> int:
    """Construye el contenido del Explorer dentro de la barra lateral (parent window).
    Devuelve el id del contenedor del árbol para futuras operaciones.
    """
    dpg.add_text("Explorer", parent=parent_id)
    dpg.add_separator(parent=parent_id)
    with dpg.child_window(tag=EXPLORER_TREE_TAG, border=False) as tree_id:
        pass

    # Aplicar el mismo tema al parent para coherencia visual
    try:
        with dpg.theme() as _outliner_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (20, 20, 20, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (230, 230, 230, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Border, (57, 255, 20, 160))
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 4.0)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8.0, 8.0)
        dpg.bind_item_theme(parent_id, _outliner_theme)
    except Exception:
        pass

    try:
        _populate_explorer(os.getcwd())
    except Exception:
        pass
    return tree_id