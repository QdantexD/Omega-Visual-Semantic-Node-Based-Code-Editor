# Omega-Visual — Semantic Node‑Based Code Editor

Codemind Visual is a Python‑powered visual development environment where you structure and automate code through intelligent semantic nodes. Each node represents a code block, logical construct, or a predefined library (e.g., C++ variables, Python functions, custom modules) so you can build complex projects visually, organized, and at scale.

## Highlights
- Built with PySide6 (Qt for Python) — fast, modern UI.
- Semantic code editing — nodes interpret and organize text or logic in real time.
- Native Python integration — nodes generate and modify Python code directly.
- Extensible — add custom node types and plug them into logic, graphics, or data engines.
- Designed for AI, ASM, and automation — connect complex routines without hand‑writing thousands of lines.
- Built‑in logging and traceback — ideal for debugging and error analysis.

## Requirements
- Python `>= 3.10`
- PySide6 `>= 6.5`
- Windows 10/11 recommended for terminal profiles (PowerShell/CMD/Git Bash)

## What’s New in 1.5.0 Alpha (2025)
- Embedded terminal inside “Terminal” nodes using `QProcess`, with profiles: `PowerShell`, `Command Prompt`, and `Git Bash`.
- Context menu actions to open/close the embedded terminal with the selected profile.
- Node Content Editor window adapted: when the node type is “Terminal”, it displays the terminal widget instead of the classic editor and saves the terminal buffer on Save/Close.
- Integration in `NodeItem` editing flow: terminal proxy is positioned inside the content area and synchronized when leaving edit mode.
- Cleaner “Terminal” node on the canvas: inner text and prompt overlay are hidden — only the title remains when not editing.
- Visual tweaks and more consistent auto‑resize behavior for content layout.
- Current limitations: no full PTY/history navigation; potential future work with ConPTY/pywinpty.

Version file: `version-1.5.0-alpha.txt` (referenced in `CodemindEditor.spec`).

## Quick Start
- Run `main.py` and open the Blueprint editor.
- Create a “Terminal” node, right‑click it and choose “Open embedded terminal (PowerShell/CMD/Git Bash)”.
- Use the top bar in the Node Content Editor to switch terminal profiles or close the session.
- Press Save to persist terminal output back to the node content.

## Building the App
- PyInstaller spec is provided: `CodemindEditor.spec`.
- The executable metadata uses `version-1.5.0-alpha.txt`.
- Build with: `pyinstaller CodemindEditor.spec`.

## Documentation
- Detailed guide (EN): `docs/shortcuts-and-benefits-1.5.0-alpha-en.md`
- Spanish guide (ES): `docs/atajos-y-beneficios-1.5.0-alpha-es.md`
- Application Documents (EN): `Application Documents/README.md`

## Previous Release — 1.0.1
- Base structure for node editor and connections.
- Node rendering, port connections, zoom, and graph evaluation.
- Editor windows and support panels (code map, realtime variables).
- Version file: `version-1.0.1.txt`.

## License
Apache License 2.0

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at:

    http://www.apache.org/licenses/LICENSE-2.0

No warranties implied. See the License for the specific language governing permissions and limitations.
