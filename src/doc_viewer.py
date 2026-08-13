import os
import base64
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl
from logger import log

class DocViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.web_view = QWebEngineView()
        self.layout.addWidget(self.web_view)
        
        # Load the local HTML shell
        # Ensure we use an absolute file path for QUrl
        current_dir = os.path.dirname(os.path.abspath(__file__))
        preview_html_path = os.path.join(os.path.dirname(current_dir), 'assets', 'preview.html')
        
        # Replace backslashes with forward slashes for the file URL on Windows
        preview_html_path = preview_html_path.replace('\\', '/')
        self.web_view.setUrl(QUrl(f"file:///{preview_html_path}"))

    def render_docx(self, path: str):
        if not os.path.exists(path):
            log.error(f"Error: Docx file not found: {path}")
            return
            
        try:
            import time
            docx_bytes = None
            for attempt in range(5):
                try:
                    with open(path, "rb") as f:
                        docx_bytes = f.read()
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.5)
                    
            if not docx_bytes:
                return
                
            # Base64 encode
            b64_data = base64.b64encode(docx_bytes).decode('utf-8')
            
            # Execute JS to render
            js_code = f"if (typeof renderDocx !== 'undefined') {{ renderDocx('{b64_data}'); }}"
            self.web_view.page().runJavaScript(js_code)
        except Exception as e:
            log.error(f"Failed to render docx: {e}")
