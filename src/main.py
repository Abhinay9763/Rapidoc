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
        self.resize(1300, 800)
        self.active_truth_path = None
        self.current_section = None

        # ── Central widget ──────────────────────────────────────────
        central_widget = QWidget()
        central_widget.setObjectName("centralWidget")
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Header bar ──────────────────────────────────────────────
        header = QWidget()
        header.setObjectName("headerPanel")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 0, 18, 0)

        title_block = QVBoxLayout()
        title_block.setSpacing(1)
        app_title = QLabel("⚡ RapiDoc")
        app_title.setObjectName("appTitle")
        app_subtitle = QLabel("AI-powered document generation")
        app_subtitle.setObjectName("appSubtitle")
        title_block.addWidget(app_title)
        title_block.addWidget(app_subtitle)
        header_layout.addLayout(title_block)
        header_layout.addStretch()

        # Template badge in header
        self.template_label = QLabel("No template loaded")
        self.template_label.setObjectName("templateBadge")
        header_layout.addWidget(self.template_label)

        root_layout.addWidget(header)

        # ── Main content (splitter) ─────────────────────────────────
        self.splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(self.splitter)

        # ── LEFT: Document Viewer ───────────────────────────────────
        left_pane = QWidget()
        left_pane.setObjectName("viewerPane")
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Viewer header strip
        viewer_header = QWidget()
        viewer_header.setObjectName("viewerHeader")
        vh_layout = QHBoxLayout(viewer_header)
        vh_layout.setContentsMargins(14, 0, 14, 0)
        viewer_title = QLabel("DOCUMENT PREVIEW")
        viewer_title.setObjectName("viewerTitle")
        vh_layout.addWidget(viewer_title)
        vh_layout.addStretch()

        self.doc_viewer = DocViewer()
        left_layout.addWidget(viewer_header)
        left_layout.addWidget(self.doc_viewer)
        self.splitter.addWidget(left_pane)

        # ── RIGHT: Chat Pane ────────────────────────────────────────
        chat_pane = QWidget()
        chat_pane.setObjectName("chatPane")
        chat_layout = QVBoxLayout(chat_pane)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        # Section progress strip
        section_strip = QWidget()
        section_strip.setObjectName("viewerHeader")   # reuse same look
        section_strip_layout = QHBoxLayout(section_strip)
        section_strip_layout.setContentsMargins(14, 0, 14, 0)
        self.agent_status_label = QLabel("")
        self.agent_status_label.setObjectName("statusLabel")
        section_strip_layout.addWidget(self.agent_status_label)
        section_strip_layout.addStretch()
        chat_layout.addWidget(section_strip)

        # Chat history
        self.chat_history = QTextEdit()
        self.chat_history.setObjectName("chatHistory")
        self.chat_history.setReadOnly(True)
        chat_layout.addWidget(self.chat_history, stretch=1)

        # Input area
        input_area = QWidget()
        input_area.setObjectName("inputArea")
        input_layout = QHBoxLayout(input_area)
        input_layout.setContentsMargins(12, 10, 12, 10)
        input_layout.setSpacing(8)

        self.chat_input = QLineEdit()
        self.chat_input.setObjectName("chatInput")
        self.chat_input.setPlaceholderText("Describe your document topic here...")
        self.chat_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.chat_input)

        self.send_button = QPushButton("Generate")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)
        chat_layout.addWidget(input_area)

        # Toolbar (load/export)
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 8, 12, 8)
        toolbar_layout.setSpacing(8)

        self.load_template_button = QPushButton("📂  Load Template")
        self.load_template_button.setObjectName("loadTemplateButton")
        self.load_template_button.clicked.connect(self.load_template)
        toolbar_layout.addWidget(self.load_template_button)

        self.export_button = QPushButton("⬇  Export PDF")
        self.export_button.setObjectName("exportButton")
        self.export_button.clicked.connect(self.export_pdf)
        toolbar_layout.addWidget(self.export_button)

        toolbar_layout.addStretch()
        chat_layout.addWidget(toolbar)

        self.splitter.addWidget(chat_pane)

        # Proportions: 65% viewer, 35% chat
        self.splitter.setSizes([845, 455])

        # ── Document setup ──────────────────────────────────────────
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.docx_path = os.path.join(os.path.dirname(current_dir), 'assets', 'sample.docx')

        self.doc_viewer.web_view.loadFinished.connect(self.on_viewer_loaded)

        # Heartbeat: re-render every 750ms (not 100ms — far less CPU spam)
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self.poll_document)
        self.heartbeat_timer.start(750)

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
        self.worker.agent_doc_updated.connect(self.on_doc_updated)

        self.worker.start()
        
    def append_chat(self, sender: str, message: str):
        import datetime
        now = datetime.datetime.now().strftime("%H:%M")
        self.chat_history.append(f"<hr><div style='color:gray; font-size:10px;'>{now}</div><b>{sender}:</b> {message}")
        
    def on_agent_started(self):
        import datetime
        now = datetime.datetime.now().strftime("%H:%M")
        self.chat_history.append(f"<hr><div style='color:#4f46e5; font-size:10px;'>{now}</div><b style='color:#a5b4fc'>⚡ RapiDoc:</b> ")
        self.agent_status_label.setText("⚡ Generating...")
        # Stop the heartbeat — the doc_updated signal will drive renders instead
        self.heartbeat_timer.stop()
        
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
        self.agent_status_label.setText("✅ Generation complete")
        self.current_section = None
        # Restart the heartbeat now that generation is done
        self.heartbeat_timer.start(750)

    def on_doc_updated(self):
        """Called after every incremental docx save during streaming — re-renders immediately."""
        self.doc_viewer.render_docx(self.docx_path, self.current_section)
        
    def on_agent_error(self, err_msg: str):
        self.append_chat("System Error", err_msg)
        self.current_section = None
        
    def on_agent_response(self, response: str):
        self.append_chat("Agent", response)
        self.current_section = None
        
    def on_agent_section_changed(self, section_name: str):
        self.current_section = section_name
        self.agent_status_label.setText(f"✍ Writing: {section_name}")

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
        self.append_chat("System", f"🔍 Analyzing template: {os.path.basename(path)}...")

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
        # Show a human-friendly name — strip the UUID hash suffix
        basename = os.path.basename(truth_path).replace(".truth.json", "")
        # e.g. "uploaded_20260814_011206_baf03dad" → "Uploaded 2026-08-14"
        parts = basename.split("_")
        if len(parts) >= 2 and parts[0] == "uploaded":
            date_part = parts[1]
            friendly = f"Template: {date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
        else:
            friendly = f"Template: {basename}"
        self.template_label.setText(friendly)
        self.append_chat("System", f"✅ Template analyzed. Ready to generate.")
        self.agent_status_label.setText("")
        self.load_template_button.setText("📂  Load Template")
        self.load_template_button.setEnabled(True)
        log.info(f"Active truth.json set to: {truth_path}")

    def _on_template_error(self, err: str):
        self.append_chat("System Error", f"❌ Template analysis failed: {err}")
        self.agent_status_label.setText("")
        self.load_template_button.setText("📂  Load Template")
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
