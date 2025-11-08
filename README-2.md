# Codemind Visual — Editor de Código por Nodos Semánticos (ES)

Codemind Visual es un entorno de desarrollo visual basado en Python que permite estructurar y automatizar código mediante nodos semánticos. Cada nodo representa bloques de código, estructuras lógicas o librerías (p. ej., variables en C++, funciones en Python o módulos personalizados), facilitando la construcción de proyectos complejos de forma visual y ordenada.

## Características principales
- UI moderna con PySide6 (Qt for Python).
- Edición semántica: los nodos interpretan y organizan texto/lógica en tiempo real.
- Integración nativa con Python: los nodos generan y modifican código Python directamente.
- Extensible: soporta nodos personalizados conectados a motores de datos, lógica o gráficos.
- Pensado para IA, ASM y automatización: conecta rutinas complejas sin escribir miles de líneas.
- Registro y trazas integradas para depuración.

## Requisitos
- Python `>= 3.10`
- PySide6 `>= 6.5`
- Windows 10/11 recomendado para perfiles de terminal (PowerShell/CMD/Git Bash).

## Novedades — Versión 1.5.0 Alfa (2025)
- Terminal embebido en nodos de tipo “Terminal” usando `QProcess`, con perfiles: `PowerShell`, `Command Prompt` y `Git Bash`.
- Menú contextual del nodo para abrir/cerrar el terminal embebido con el perfil elegido.
- Ventana de edición del nodo adaptada: cuando el tipo es “Terminal”, se muestra el widget de terminal (no el editor clásico) y se guarda el buffer al cerrar/guardar.
- Integración en el flujo de edición del `NodeItem`: posicionamiento del terminal dentro del área de contenido y sincronización al salir de edición.
- Nodo “Terminal” más elegante en el lienzo: se oculta el texto interno y el overlay del prompt; se muestra solo el título cuando no está en edición.
- Mejoras visuales y de autoajuste (auto‑resize) del contenido.
- Limitación actual: sin soporte completo de PTY/historial con flechas; posible futuro con ConPTY/pywinpty.

Archivo de versión: `version-1.5.0-alpha.txt` (referenciado en `CodemindEditor.spec`).

## Guía rápida
- Ejecuta `main.py` para abrir el editor.
- Crea un nodo “Terminal”.
- Clic derecho sobre el nodo y elige: “Abrir terminal embebido (PowerShell/CMD/Git Bash)”.
- En la ventana de edición del nodo, usa la barra superior para cambiar perfil o cerrar la sesión.
- Presiona Guardar para persistir el buffer del terminal en el contenido del nodo.

## Menú contextual y acciones
- “Abrir terminal embebido (PowerShell)” — inicia PowerShell.
- “Abrir terminal embebido (Command Prompt)” — inicia CMD.
- “Abrir terminal embebido (Git Bash)” — inicia Git Bash (si está instalado).
- “Cerrar terminal embebido” — detiene el proceso y oculta el widget.

## Integración técnica (archivos modificados)
- `core/graph/node_item.py` — clase `EmbeddedTerminal`, integración en `set_editing`, posicionamiento en `_update_content_layout`, limpieza visual en `paint`.
- `core/app/node_content_editor_window.py` — muestra el terminal embebido para nodos “Terminal”, guarda su buffer.
- `core/graph/node_view.py` — acciones de menú contextual para abrir/cerrar el terminal con perfiles.
- `CodemindEditor.spec` — actualizado para usar `version-1.5.0-alpha.txt`.
- `version-1.5.0-alpha.txt` — metadatos de versión del ejecutable.

## Construcción (build)
- Usa el spec de PyInstaller: `CodemindEditor.spec`.
- Compila con: `pyinstaller CodemindEditor.spec`.

## Historial de cambios
- 1.5.0 Alfa (2025)
  - Terminal embebido, perfiles, menú contextual.
  - Ventana de edición adaptada para “Terminal”.
  - Nodo “Terminal” sin texto interno en el lienzo.
  - Ajustes visuales y de auto‑resize.
- 1.0.1 (estable)
  - Base del editor de nodos y conexiones.
  - Renderizado de nodos, puertos, zoom, evaluación del grafo.
  - Ventanas de editor y paneles de apoyo (mapa de código, variables en tiempo real).

## Roadmap sugerido
- Integración PTY (ConPTY/pywinpty) para historial y navegación avanzada.
- Atajos de teclado para abrir/cerrar terminal y cambiar perfiles.
- Preferencias por nodo para recordar perfil/directorio inicial.

## Documentación de aplicación (EN)
- Índice: `Application Documents/README.md`

## Licencia
- Apache License 2.0 — ver `LICENSE`.
- Enlace: `http://www.apache.org/licenses/LICENSE-2.0`.
- Sin garantías implícitas; consulta los términos para permisos y limitaciones.