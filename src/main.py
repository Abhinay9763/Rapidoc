import sys
import os
import threading
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QSplitter, QTextEdit, QLineEdit,
    QPushButton, QMessageBox, QLabel, QFileDialog
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal

from doc_viewer import DocViewer
from agent_worker import AgentWorker
from pdf_export import export_to_pdf
from dotenv import load_dotenv
from logger import log

load_dotenv()


class UploadWorker(QThread):
    """Background worker that runs the full upload pipeline."""
    finished = Signal(str)   # emits path to generated truth.json
    error = Signal(str)
    status = Signal(str)     # status messages for the chat

    def __init__(self, template_path: str, output_dir: str, parent=None):
        super().__init__(parent)
        self.template_path = template_path
        self.output_dir = output_dir

    def run(self):
        try:
            from upload_pipeline import run_upload_pipeline
            self.status.emit(f"Parsing template: {os.path.basename(self.template_path)}...")
            truth_path = run_upload_pipeline(self.template_path, self.output_dir)
            self.finished.emit(truth_path)
        except Exception as e:
            log.error(f"Upload pipeline error: {e}")
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RapiDoc")
        self.resize(1200, 750)
        self.active_truth_path = None  # None = preset path; str = uploaded truth.json
        self.current_section = None
        
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
        
        # Bottom buttons row
        bottom_layout = QHBoxLayout()

        self.load_template_button = QPushButton("Load Template")
        self.load_template_button.setObjectName("loadTemplateButton")
        self.load_template_button.clicked.connect(self.load_template)
        bottom_layout.addWidget(self.load_template_button)

        self.export_button = QPushButton("Export PDF")
        self.export_button.clicked.connect(self.export_pdf)
        bottom_layout.addWidget(self.export_button)

        chat_layout.addLayout(bottom_layout)

        # Active template label
        self.template_label = QLabel("Template: Preset")
        self.template_label.setStyleSheet("color: gray; font-size: 11px;")
        chat_layout.addWidget(self.template_label)
        
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
        
        # Start agent — pass active truth path (None = preset)
        self.worker = AgentWorker(self.docx_path, text, truth_path=self.active_truth_path)
        self.worker.agent_started.connect(self.on_agent_started)
        self.worker.agent_finished.connect(self.on_agent_finished)
        self.worker.agent_error.connect(self.on_agent_error)
        self.worker.agent_response.connect(self.on_agent_response)
        self.worker.agent_stream_chat.connect(self.on_agent_stream_chat)
        self.worker.agent_section_changed.connect(self.on_agent_section_changed)

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
        self.current_section = None
        
    def on_agent_error(self, err_msg: str):
        self.append_chat("System Error", err_msg)
        self.current_section = None
        
    def on_agent_response(self, response: str):
        self.append_chat("Agent", response)
        self.current_section = None
        
    def on_agent_section_changed(self, section_name: str):
        self.current_section = section_name

    def poll_document(self):
        self.doc_viewer.render_docx(self.docx_path, self.current_section)

    def load_template(self):
        """Open a .docx file picker, run the upload pipeline, and activate the result."""
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Report Template", current_dir,
            "Word Documents (*.docx)"
        )
        if not path:
            return

        self.load_template_button.setEnabled(False)
        self.load_template_button.setText("Analyzing...")
        self.append_chat("System", f"Loading template: {os.path.basename(path)}")

        templates_dir = os.path.join(current_dir, 'templates')
        self._upload_worker = UploadWorker(path, templates_dir)
        self._upload_worker.status.connect(
            lambda msg: self.agent_status_label.setText(msg)
        )
        self._upload_worker.finished.connect(self._on_template_loaded)
        self._upload_worker.error.connect(self._on_template_error)
        self._upload_worker.start()

    def _on_template_loaded(self, truth_path: str):
        self.active_truth_path = truth_path
        name = os.path.basename(truth_path)
        self.template_label.setText(f"Template: {name}")
        self.append_chat("System", f"Template analyzed successfully. Using: {name}")
        self.agent_status_label.setText("")
        self.load_template_button.setText("Load Template")
        self.load_template_button.setEnabled(True)
        log.info(f"Active truth.json set to: {truth_path}")

    def _on_template_error(self, err: str):
        self.append_chat("System Error", f"Template analysis failed: {err}")
        self.agent_status_label.setText("")
        self.load_template_button.setText("Load Template")
        self.load_template_button.setEnabled(True)
        
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
