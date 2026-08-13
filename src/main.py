import sys
import os
import threading
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QSplitter, QTextEdit, QLineEdit, 
    QPushButton, QMessageBox, QLabel
)
from PySide6.QtCore import Qt

from doc_viewer import DocViewer
from agent_worker import AgentWorker
from pdf_export import export_to_pdf

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
        main_layout.addWidget(self.splitter)
        
        # Left Pane: Document Viewer
        self.doc_viewer = DocViewer()
        self.splitter.addWidget(self.doc_viewer)
        
        # Right Pane: Chat Interface
        self.chat_panel = QWidget()
        chat_layout = QVBoxLayout(self.chat_panel)
        
        # Chat history
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        chat_layout.addWidget(self.chat_history)
        
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
        
    def on_viewer_loaded(self, ok):
        if ok:
            print("Web view loaded, rendering docx...")
            self.doc_viewer.render_docx(self.docx_path)
        else:
            print("Failed to load web view.")

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
        self.worker.document_updated.connect(self.on_document_updated)
        
        self.worker.start()
        
    def append_chat(self, sender: str, message: str):
        self.chat_history.append(f"<b>{sender}:</b> {message}")
        
    def on_agent_started(self):
        pass # UI already disabled
        
    def on_agent_finished(self):
        self.chat_input.setEnabled(True)
        self.send_button.setEnabled(True)
        self.chat_input.setFocus()
        
    def on_agent_error(self, err_msg: str):
        self.append_chat("System Error", err_msg)
        
    def on_agent_response(self, response: str):
        self.append_chat("Agent", response)
        
    def on_document_updated(self):
        self.doc_viewer.render_docx(self.docx_path)
        
    def export_pdf(self):
        self.export_button.setEnabled(False)
        self.export_button.setText("Exporting...")
        
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets')
        
        def run_export():
            try:
                pdf_path = export_to_pdf(self.docx_path, output_dir)
                # Ensure UI updates happen on main thread using a lambda and QMetaObject.invokeMethod
                # However, for simplicity, since it's a short thread, we can use QApplication.invokeLater or just standard Qt signals.
                # To keep it simple, we'll just show a message box on main thread via a signal or direct call (which can be unsafe, but okay for a stub)
                print(f"Exported to {pdf_path}")
                # We should re-enable the button safely. For Phase 1, calling a basic print is safe.
            except Exception as e:
                print(f"Export Error: {e}")

            
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
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
