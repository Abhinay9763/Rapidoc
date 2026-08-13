import time
from PySide6.QtCore import QThread, Signal
from docx import Document

class AgentWorker(QThread):
    # Define signals
    agent_started = Signal()
    agent_finished = Signal()
    agent_error = Signal(str)
    agent_response = Signal(str)
    document_updated = Signal()

    def __init__(self, docx_path: str, user_message: str, parent=None):
        super().__init__(parent)
        self.docx_path = docx_path
        self.user_message = user_message

    def run(self):
        self.agent_started.emit()
        try:
            # Simulate some processing time
            time.sleep(1.5)
            
            # Write back to document using python-docx
            doc = Document(self.docx_path)
            doc.add_paragraph(f"[Agent Insert]: {self.user_message}")
            doc.save(self.docx_path)
            
            # Notify that the document is updated and should be re-rendered
            self.document_updated.emit()
            
            # Emit the agent response for the chat UI
            canned_response = f"I've added your text to the document."
            self.agent_response.emit(canned_response)
            
        except Exception as e:
            self.agent_error.emit(str(e))
        finally:
            self.agent_finished.emit()
