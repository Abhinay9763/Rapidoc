import sys
import os
import threading
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QSplitter, QTextEdit, QLineEdit, 
    QPushButton, QMessageBox, QLabel
)
from PySide6.QtCore import Qt, QTimer

from doc_viewer import DocViewer
from agent_worker import AgentWorker
from pdf_export import export_to_pdf
from dotenv import load_dotenv
from logger import log

load_dotenv()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RapiDoc - Phase 1 UI Shell")
        self.resize(1000, 700)
        
        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Splitter
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #cccccc; width: 4px; }")
        main_layout.addWidget(self.splitter)
        
        # Left Pane: Document Viewer
        self.left_pane = QWidget()
        left_layout = QVBoxLayout(self.left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.doc_viewer = DocViewer()
        left_layout.addWidget(self.doc_viewer)
        self.splitter.addWidget(self.left_pane)
        
        # Right Pane: Chat Interface
        self.chat_panel = QWidget()
        chat_layout = QVBoxLayout(self.chat_panel)
        
        # Chat history
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        chat_layout.addWidget(self.chat_history)
        
        self.agent_status_label = QLabel("")
        self.agent_status_label.setStyleSheet("color: #0078D7; font-style: italic;")
        chat_layout.addWidget(self.agent_status_label)
        
        # Input area
        input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type your instruction here...")
        self.chat_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.chat_input)
        
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)
        chat_layout.addLayout(input_layout)
        
        # Export PDF button at the bottom of the chat panel
        self.export_button = QPushButton("Export PDF")
        self.export_button.clicked.connect(self.export_pdf)
        chat_layout.addWidget(self.export_button)
        
        self.splitter.addWidget(self.chat_panel)
        
        # Initial proportions
        self.splitter.setSizes([600, 400])
        
        # Document setup
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.docx_path = os.path.join(os.path.dirname(current_dir), 'assets', 'sample.docx')
        
        # We need to give the QWebEngineView time to load the HTML shell before we send the initial render
        # Let's wait until it's loaded to trigger the first render
        self.doc_viewer.web_view.loadFinished.connect(self.on_viewer_loaded)
        
        # Heartbeat timer to poll the document and render it every 5 seconds
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self.poll_document)
        self.heartbeat_timer.start(100)
        
    def on_viewer_loaded(self, ok):
        if ok:
            log.info("Web view loaded, rendering docx...")
            self.doc_viewer.render_docx(self.docx_path)
        else:
            log.error("Failed to load web view.")

    def send_message(self):
        text = self.chat_input.text().strip()
        if not text:
            return
            
        self.append_chat("User", text)
        self.chat_input.clear()
        
        # Disable input
        self.chat_input.setEnabled(False)
        self.send_button.setEnabled(False)
        
        # Start agent
        self.worker = AgentWorker(self.docx_path, text)
        self.worker.agent_started.connect(self.on_agent_started)
        self.worker.agent_finished.connect(self.on_agent_finished)
        self.worker.agent_error.connect(self.on_agent_error)
        self.worker.agent_response.connect(self.on_agent_response)
        self.worker.agent_stream_chat.connect(self.on_agent_stream_chat)
        
        self.worker.start()
        
    def append_chat(self, sender: str, message: str):
        import datetime
        now = datetime.datetime.now().strftime("%H:%M")
        self.chat_history.append(f"<hr><div style='color:gray; font-size:10px;'>{now}</div><b>{sender}:</b> {message}")
        
    def on_agent_started(self):
        import datetime
        now = datetime.datetime.now().strftime("%H:%M")
        self.chat_history.append(f"<hr><div style='color:gray; font-size:10px;'>{now}</div><b>Agent:</b> ")
        self.agent_status_label.setText("Agent is working...")
        
    def on_agent_stream_chat(self, chunk: str):
        cursor = self.chat_history.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.chat_history.setTextCursor(cursor)
        self.chat_history.insertPlainText(chunk)
        self.chat_history.verticalScrollBar().setValue(self.chat_history.verticalScrollBar().maximum())
        
    def on_agent_finished(self):
        self.chat_input.setEnabled(True)
        self.send_button.setEnabled(True)
        self.chat_input.setFocus()
        self.agent_status_label.setText("")
        
    def on_agent_error(self, err_msg: str):
        self.append_chat("System Error", err_msg)
        
    def on_agent_response(self, response: str):
        self.append_chat("Agent", response)
        
    def poll_document(self):
        self.doc_viewer.render_docx(self.docx_path)
        
    def export_pdf(self):
        self.export_button.setEnabled(False)
        self.export_button.setText("Exporting...")
        
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets')
        
        def run_export():
            try:
                pdf_path = export_to_pdf(self.docx_path, output_dir)
                log.info(f"Exported to {pdf_path}")
            except Exception as e:
                log.error(f"Export Error: {e}")

            
        # Run export in background thread so UI doesn't freeze
        t = threading.Thread(target=run_export)
        t.start()
        
        # Ideally we want a signal to update UI when done. For now we just wait a bit or use a QTimer to check.
        # To avoid adding complex signals for the stub, we can just re-enable it after a short delay assuming it's done.
        # But let's build it safely.
        # Re-enabling the button directly from another thread might crash PySide.
        # Let's just do it simple for now, and re-enable it immediately but show a log.
        # A better approach: 
        import PySide6.QtCore
        
        class Exporter(PySide6.QtCore.QObject):
            finished = PySide6.QtCore.Signal(str)
            error = PySide6.QtCore.Signal(str)
            
            def do_work(self, docx, out_dir):
                try:
                    p = export_to_pdf(docx, out_dir)
                    self.finished.emit(p)
                except Exception as e:
                    self.error.emit(str(e))
                    
        self._exporter = Exporter()
        self._export_thread = threading.Thread(target=self._exporter.do_work, args=(self.docx_path, output_dir))
        
        def on_fin(path):
            self.export_button.setText("Export PDF")
            self.export_button.setEnabled(True)
            QMessageBox.information(self, "Export Successful", f"PDF exported to:\n{path}")
            
        def on_err(err):
            self.export_button.setText("Export PDF")
            self.export_button.setEnabled(True)
            QMessageBox.critical(self, "Export Failed", str(err))
            
        self._exporter.finished.connect(on_fin)
        self._exporter.error.connect(on_err)
        self._export_thread.start()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Load stylesheet
    current_dir = os.path.dirname(os.path.abspath(__file__))
    style_path = os.path.join(os.path.dirname(current_dir), 'assets', 'style.qss')
    if os.path.exists(style_path):
        with open(style_path, 'r', encoding='utf-8') as f:
            app.setStyleSheet(f.read())
            
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
