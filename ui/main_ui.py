import threading
import asyncio
import json
import websockets
from dearpygui import dearpygui as dpg

from .windows.toolbar import build_toolbar
from .windows.main_window import build_main_window
from .windows.properties_panel import build_properties_panel
from .core.graph import Graph
from .core.nodes import Node, NodeType, NodeRegistry
from .core.links import Link

WS_URL = "ws://127.0.0.1:8000/ws"

# Runtime state
GRAPH = Graph()
REGISTRY = NodeRegistry()
_NODE_COUNTER = 0
_EDITOR_ID = None
_WS_STATUS_ALIAS = "ws_status"
_LAST_SELECTED_NODE_ID = None
_CTRL_DOWN = False
_TOOLBAR_ID = None
_MAIN_WIN_ID = None
_PROPS_WIN_ID = None
_STATUS_WIN_ID = None
_FS_MODE = False
_FS_PREV = {}


def _set_text(item, value):
    dpg.set_value(item, value)


def start_ui():
    dpg.create_context()
    dpg.create_viewport(title="Omega-Visual", width=1200, height=800)
    dpg.setup_dearpygui()

    # Apply global visual theme
    _build_global_theme()

    # Build windows
    toolbar_id = build_toolbar()
    main_win_id, editor_id = build_main_window()
    global _EDITOR_ID
    _EDITOR_ID = editor_id
    props_id = build_properties_panel()
    # Store window ids for fullscreen toggle
    global _TOOLBAR_ID, _MAIN_WIN_ID, _PROPS_WIN_ID
    _TOOLBAR_ID = toolbar_id
    _MAIN_WIN_ID = main_win_id
    _PROPS_WIN_ID = props_id

    # Status labels from toolbar: use alias directly
    ws_label = _WS_STATUS_ALIAS
    # Bottom status bar for logs
    with dpg.window(label="Status", no_move=True, no_resize=True, height=28, pos=(0, 760), width=1200) as status_id:
        log_label = dpg.add_text("Ready", wrap=0)
    global _STATUS_WIN_ID
    _STATUS_WIN_ID = status_id

    # Register default node types
    _register_default_node_types()

    # Wire toolbar actions
    dpg.set_item_callback("btn_new", _on_new_pressed)
    dpg.set_item_callback("btn_duplicate", _on_duplicate_pressed)
    dpg.set_item_callback("btn_save", _on_save_pressed)
    dpg.set_item_callback("btn_load", _on_load_pressed)

    # Configure node editor callbacks (link create/destroy)
    dpg.configure_item(editor_id, callback=_on_link_created, delink_callback=_on_link_deleted)

    # Keyboard handlers (Ctrl+M: fullscreen editor)
    with dpg.handler_registry():
        dpg.add_key_down_handler(dpg.mvKey_Control, callback=_on_ctrl_down)
        dpg.add_key_release_handler(dpg.mvKey_Control, callback=_on_ctrl_up)
        dpg.add_key_press_handler(dpg.mvKey_M, callback=_on_m_pressed)

    # Start WebSocket client thread
    threading.Thread(target=_start_ws_client, args=(ws_label, log_label), daemon=True).start()

    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


# --- WebSocket client ---
def _start_ws_client(ws_label, log_label):
    async def run():
        try:
            async with websockets.connect(WS_URL) as ws:
                _set_text(ws_label, "WS: connected")
                print("Connected to WebSocket Server")
                await ws.send("Hello from GUI!")
                while True:
                    try:
                        msg = await ws.recv()
                        # Try JSON
                        try:
                            evt = json.loads(msg)
                            _handle_server_event(evt)
                            _set_text(log_label, f"Server evt: {evt.get('type')}")
                        except Exception:
                            print("Server:", msg)
                            _set_text(log_label, f"Server: {msg}")
                    except Exception as e:
                        _set_text(ws_label, f"WS error: {e}")
                        break
        except Exception as e:
            _set_text(ws_label, f"WS error: {e}")

    asyncio.run(run())


def _send_graph_snapshot():
    # include positions from UI at save time
    snap = GRAPH.snapshot()
    for n in snap["nodes"]:
        nid = n["id"]
        try:
            pos = dpg.get_item_pos(nid)
            n.setdefault("meta", {})["pos"] = list(pos)
        except Exception:
            pass
    payload = {"type": "graph_snapshot", "payload": snap}

    async def run():
        try:
            async with websockets.connect(WS_URL) as ws:
                await ws.send(json.dumps(payload))
        except Exception as e:
            print("WS send error:", e)

    threading.Thread(target=lambda: asyncio.run(run()), daemon=True).start()


def _build_global_theme():
    try:
        with dpg.theme() as theme_id:
            with dpg.theme_component(dpg.mvAll):
                # Colors
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (22, 24, 28, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (230, 232, 235, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (40, 42, 46, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (55, 57, 60, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (65, 67, 70, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (52, 84, 172, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (62, 94, 182, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (42, 74, 152, 255))
                # Spacing & rounding
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 6.0)
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4.0)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8.0, 6.0)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 8.0, 8.0)
        dpg.bind_theme(theme_id)
    except Exception as e:
        print("Theme build error:", e)


def _send_event(event_type: str, payload: dict):
    data = {"type": event_type, "payload": payload}

    async def run():
        try:
            async with websockets.connect(WS_URL) as ws:
                await ws.send(json.dumps(data))
        except Exception as e:
            print("WS event send error:", e)

    threading.Thread(target=lambda: asyncio.run(run()), daemon=True).start()


# --- Fullscreen toggle helpers ---
def _on_ctrl_down(sender, app_data):
    global _CTRL_DOWN
    _CTRL_DOWN = True


def _on_ctrl_up(sender, app_data):
    global _CTRL_DOWN
    _CTRL_DOWN = False


def _on_m_pressed(sender, app_data):
    if _CTRL_DOWN:
        _toggle_editor_fullscreen()


def _viewport_size() -> tuple[int, int]:
    try:
        w = dpg.get_viewport_client_width()
        h = dpg.get_viewport_client_height()
        if w and h:
            return int(w), int(h)
    except Exception:
        pass
    return 1200, 800


def _toggle_editor_fullscreen():
    global _FS_MODE, _FS_PREV
    try:
        if not _FS_MODE:
            # Save current layout
            def _save_win(win_id, key):
                pos = dpg.get_item_pos(win_id)
                w = dpg.get_item_width(win_id)
                h = dpg.get_item_height(win_id)
                _FS_PREV[key] = {"pos": pos, "size": (w, h), "show": dpg.is_item_shown(win_id)}

            _save_win(_TOOLBAR_ID, "toolbar")
            _save_win(_MAIN_WIN_ID, "main")
            _save_win(_PROPS_WIN_ID, "props")
            _save_win(_STATUS_WIN_ID, "status")

            # Hide ancillary windows
            dpg.configure_item(_TOOLBAR_ID, show=False)
            dpg.configure_item(_PROPS_WIN_ID, show=False)
            dpg.configure_item(_STATUS_WIN_ID, show=False)

            # Maximize main window and editor
            vw, vh = _viewport_size()
            dpg.configure_item(_MAIN_WIN_ID, pos=(0, 0), width=vw, height=vh)
            try:
                dpg.configure_item(_EDITOR_ID, width=vw - 20, height=vh - 20)
            except Exception:
                pass
            _FS_MODE = True
        else:
            # Restore layout
            def _restore(win_id, key):
                prev = _FS_PREV.get(key, {})
                if not prev:
                    return
                pos = prev.get("pos")
                size = prev.get("size")
                show = prev.get("show", True)
                if pos:
                    dpg.configure_item(win_id, pos=tuple(pos))
                if size:
                    w, h = size
                    dpg.configure_item(win_id, width=int(w), height=int(h))
                dpg.configure_item(win_id, show=show)

            _restore(_TOOLBAR_ID, "toolbar")
            _restore(_MAIN_WIN_ID, "main")
            _restore(_PROPS_WIN_ID, "props")
            _restore(_STATUS_WIN_ID, "status")
            _FS_MODE = False
    except Exception as e:
        print("Fullscreen toggle error:", e)


def _handle_server_event(evt: dict):
    t = evt.get("type")
    payload = evt.get("payload", {})
    if t == "node_update":
        node_id = payload.get("id")
        value = payload.get("value")
        if node_id and value is not None:
            try:
                # Update node label to reflect value
                node = GRAPH.nodes.get(node_id)
                base_label = node.title if node else node_id
                dpg.configure_item(node_id, label=f"{base_label} ({value})")
            except Exception as e:
                print("Label update error:", e)
# --- Node registry and creation ---
def _register_default_node_types():
    REGISTRY.register(NodeType("Compute", inputs=["in"], outputs=["out"], color="#66CCFF"))
    REGISTRY.register(NodeType("Data", inputs=[], outputs=["out"], color="#9CCC65"))
    REGISTRY.register(NodeType("Op", inputs=["a", "b"], outputs=["result"], color="#FFCA28"))


def _create_node(type_name: str):
    global _NODE_COUNTER
    nt = REGISTRY.get(type_name)
    if not nt or _EDITOR_ID is None:
        return

    _NODE_COUNTER += 1
    node_id = f"node{_NODE_COUNTER}"

    with dpg.node(label=nt.name, parent=_EDITOR_ID, tag=node_id):
        # inputs
        for inp in nt.inputs:
            with dpg.node_attribute(parent=node_id, attribute_type=dpg.mvNode_Attr_Input, tag=f"{node_id}:in:{inp}"):
                dpg.add_text(inp)
        # outputs
        for outp in nt.outputs:
            with dpg.node_attribute(parent=node_id, attribute_type=dpg.mvNode_Attr_Output, tag=f"{node_id}:out:{outp}"):
                dpg.add_text(outp)
        # Click handler to select node
        with dpg.item_handler_registry() as hreg:
            dpg.add_item_clicked_handler(callback=_on_node_clicked, user_data=node_id)
        dpg.bind_item_handler_registry(node_id, hreg)

    GRAPH.add_node(Node(id=node_id, type=nt.name, title=nt.name, inputs=nt.inputs, outputs=nt.outputs, meta={"color": nt.color}))
    # Send event: node_created
    _send_event("node_created", {
        "id": node_id,
        "name": nt.name,
        "inputs": nt.inputs,
        "outputs": nt.outputs,
    })
    _send_graph_snapshot()
    # Auto-select new node
    _on_node_selected(node_id)


# --- Link management ---
def _on_link_created(sender, app_data):
    try:
        start_attr, end_attr = app_data
        # Draw the link visually
        dpg.add_node_link(start_attr, end_attr, parent=sender)
        # Update graph model
        s_node, _, s_port = start_attr.split(":", 2)
        e_node, _, e_port = end_attr.split(":", 2)
        GRAPH.add_link(Link(start_node=s_node, start_port=s_port, end_node=e_node, end_port=e_port))
        # Send event: link_created
        _send_event("link_created", {
            "from": {"node": s_node, "port": s_port},
            "to": {"node": e_node, "port": e_port},
        })
        _send_graph_snapshot()
    except Exception as e:
        print("Link create error:", e)


def _on_link_deleted(sender, app_data):
    try:
        # app_data is the list of link IDs to delete
        for link_id in app_data:
            conf = dpg.get_item_configuration(link_id)
            start_attr = conf.get("start_attr")
            end_attr = conf.get("end_attr")
            if start_attr and end_attr:
                s_node, _, s_port = str(start_attr).split(":", 2)
                e_node, _, e_port = str(end_attr).split(":", 2)
                # remove matching link from GRAPH
                GRAPH.links = [
                    l for l in GRAPH.links
                    if not (l.start_node == s_node and l.start_port == s_port and l.end_node == e_node and l.end_port == e_port)
                ]
        _send_graph_snapshot()
    except Exception as e:
        print("Link delete error:", e)


def _on_node_drag(sender, app_data):
    try:
        node_id = app_data
        pos = dpg.get_item_pos(node_id)
        # Update graph node meta
        if node_id in GRAPH.nodes:
            GRAPH.nodes[node_id].meta["pos"] = pos
        # Send event: node_moved
        _send_event("node_moved", {"id": node_id, "pos": list(pos)})
    except Exception as e:
        print("Node drag error:", e)


# --- Selection and properties ---
def _on_node_clicked(sender, app_data, user_data):
    node_id = user_data
    _on_node_selected(node_id)


def _on_node_selected(node_id: str):
    global _LAST_SELECTED_NODE_ID
    _LAST_SELECTED_NODE_ID = node_id
    node = GRAPH.nodes.get(node_id)
    if node:
        dpg.set_value("prop_title", node.title or "")
        dpg.set_value("prop_type", node.type)
        dpg.set_value("prop_id", node.id)
        dpg.set_value("prop_inputs", f"Inputs: {', '.join(node.inputs)}")
        dpg.set_value("prop_outputs", f"Outputs: {', '.join(node.outputs)}")
        dpg.set_value("prop_hint", "")


# --- Toolbar actions ---
def _on_new_pressed():
    t = dpg.get_value("node_type") or "Compute"
    _create_node(str(t))


def _on_duplicate_pressed():
    if not _LAST_SELECTED_NODE_ID:
        return
    node = GRAPH.nodes.get(_LAST_SELECTED_NODE_ID)
    if not node:
        return
    _create_node(node.type)
    # offset new node position near last selected
    try:
        pos = dpg.get_item_pos(_LAST_SELECTED_NODE_ID)
        dpg.set_item_pos(f"node{_NODE_COUNTER}", (pos[0] + 40, pos[1] + 40))
    except Exception:
        pass


def _on_save_pressed():
    # write project.json to root
    snap = GRAPH.snapshot()
    for n in snap["nodes"]:
        nid = n["id"]
        try:
            pos = dpg.get_item_pos(nid)
            n.setdefault("meta", {})["pos"] = list(pos)
        except Exception:
            pass
    try:
        with open("project.json", "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=2)
        _set_text(_WS_STATUS_ALIAS, "WS: saved project.json")
    except Exception as e:
        print("Save error:", e)


def _on_load_pressed():
    try:
        with open("project.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("Load error:", e)
        return

    # Clear current editor and graph
    try:
        dpg.delete_item(_EDITOR_ID, children_only=True)
    except Exception:
        pass
    GRAPH.nodes.clear()
    GRAPH.links.clear()

    # Reset counter
    global _NODE_COUNTER
    _NODE_COUNTER = 0

    # Rebuild nodes preserving IDs
    for n in data.get("nodes", []):
        tname = n.get("type", "Compute")
        _create_node(tname)
        nid_new = f"node{_NODE_COUNTER}"
        nid_target = n.get("id", nid_new)
        if nid_target != nid_new:
            try:
                dpg.configure_item(nid_new, tag=nid_target)
            except Exception:
                pass
        # set pos if available
        pos = n.get("meta", {}).get("pos")
        if pos:
            try:
                dpg.set_item_pos(nid_target, tuple(pos))
            except Exception:
                pass

    # Rebuild links
    for l in data.get("links", []):
        s = l.get("from", {})
        e = l.get("to", {})
        s_attr = f"{s.get('node')}:out:{s.get('port')}"
        e_attr = f"{e.get('node')}:in:{e.get('port')}"
        try:
            dpg.add_node_link(s_attr, e_attr, parent=_EDITOR_ID)
            GRAPH.add_link(Link(start_node=s.get('node'), start_port=s.get('port'), end_node=e.get('node'), end_port=e.get('port')))
        except Exception as ex:
            print("Link load error:", ex)
