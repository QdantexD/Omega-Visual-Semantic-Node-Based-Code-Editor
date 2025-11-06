from PySide6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QSyntaxHighlighter, QPainter, QTextFormat
from PySide6.QtCore import Qt, QSize
import re

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor
    def sizeHint(self):
        return QSize(self._editor.lineNumberAreaWidth(), 0)
    def paintEvent(self, event):
        self._editor.lineNumberAreaPaintEvent(event)

class TextEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        # Flag anti-reentrancia para el pintado de números de línea
        self._painting_line_numbers = False
        # Fuente monoespaciada para código
        font = QFont("Courier", 11)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)

        # Área de números de línea
        self.lineNumberArea = LineNumberArea(self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.updateLineNumberAreaWidth(0)
        self.highlightCurrentLine()

        # Texto de placeholder
        self.setPlaceholderText("Escribe tu código aquí...")

        # Distancia de tabulación
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(' ') * 4)  # 4 espacios

        # Habilitar autoscroll al final (útil para logs o nodos que imprimen)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

        # Estilo profesional oscuro y elegante (paleta uniforme)
        self.setStyleSheet(
            "QPlainTextEdit {"
            " background-color: #0f172a;"  # slate-900
            " color: #e2e8f0;"              # text gris claro
            " border: 1px solid #334155;"   # slate-700
            " selection-background-color: #1e293b;"  # azul profundo para selección
            "}"
        )

    def lineNumberAreaWidth(self):
        digits = 1
        max_ = max(1, self.blockCount())
        while max_ >= 10:
            max_ //= 10
            digits += 1
        space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height())

    def lineNumberAreaPaintEvent(self, event):
        # Evitar reentrancia: si ya estamos pintando, salimos
        if getattr(self, '_painting_line_numbers', False):
            return
        self._painting_line_numbers = True
        painter = QPainter(self.lineNumberArea)
        try:
            # Fondo de números de línea más oscuro
            painter.fillRect(event.rect(), QColor("#0b1220"))
            block = self.firstVisibleBlock()
            blockNumber = block.blockNumber()
            top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
            bottom = top + self.blockBoundingRect(block).height()
            while block.isValid() and top <= event.rect().bottom():
                if block.isVisible() and bottom >= event.rect().top():
                    number = str(blockNumber + 1)
                    # Color de texto de números de línea más sobrio
                    painter.setPen(QColor("#64748b"))
                    painter.drawText(0, int(top), int(self.lineNumberArea.width()) - 6, int(self.fontMetrics().height()), Qt.AlignRight, number)
                block = block.next()
                top = bottom
                bottom = top + self.blockBoundingRect(block).height()
                blockNumber += 1
        finally:
            # Asegurar que no queden dos QPainter activos sobre el mismo dispositivo
            try:
                painter.end()
            except Exception:
                pass
            self._painting_line_numbers = False

    def highlightCurrentLine(self):
        selections = []
        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            # Resaltado de línea actual sutil
            sel.format.setBackground(QColor("#0b1220"))
            sel.format.setProperty(QTextFormat.FullWidthSelection, True)
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            selections.append(sel)
        self.setExtraSelections(selections)

class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent)
        # Paleta neón
        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor("#7df9ff"))  # cian eléctrico
        self.keyword_format.setFontWeight(QFont.Bold)

        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#ff6be6"))  # rosa neón

        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#39ff14"))  # verde neón

        self.builtin_format = QTextCharFormat()
        self.builtin_format.setForeground(QColor("#ffd166"))  # ámbar

        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor("#64748b"))  # comentario discreto

        # Patrones
        self.keyword_pattern = re.compile(r"\b(def|class|import|from|as|if|else|elif|return|for|while|try|except|with|lambda|yield|pass|break|continue|in|is|not|and|or)\b")
        self.builtin_pattern = re.compile(r"\b(print|len|range|dict|list|set|tuple|int|str|float|bool|type|enumerate|zip|map|filter|sum|min|max|abs)\b")
        self.string_pattern = re.compile(r"(\"[^\"]*\"|'[^']*')")
        self.number_pattern = re.compile(r"\b\d+(?:\.\d+)?\b")
        self.comment_pattern = re.compile(r"#.*")

    def highlightBlock(self, text):
        # Comentarios
        for m in self.comment_pattern.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.comment_format)

        # Strings
        for m in self.string_pattern.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.string_format)

        # Números
        for m in self.number_pattern.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.number_format)

        # Keywords
        for m in self.keyword_pattern.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.keyword_format)

        # Builtins
        for m in self.builtin_pattern.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self.builtin_format)
