from PySide6.QtCore import QThread, Signal
from orchestrator import run_full_generation
from logger import log

class AgentWorker(QThread):
    agent_started = Signal()
    agent_finished = Signal()
    agent_error = Signal(str)
    agent_response = Signal(str)
    agent_stream_chat = Signal(str)

    def __init__(self, docx_path: str, user_message: str, parent=None):
        super().__init__(parent)
        self.docx_path = docx_path
        self.user_message = user_message

    def run(self):
        self.agent_started.emit()
        log.info(f"AgentWorker started for topic: {self.user_message}")
        try:
            def stream_chat_callback(chunk: str):
                self.agent_stream_chat.emit(chunk)
                
            run_full_generation(
                topic=self.user_message, 
                docx_path=self.docx_path,
                stream_chat_callback=stream_chat_callback
            )
            
            log.info("AgentWorker completed successfully.")
            self.agent_response.emit("\n\n*Generation complete.*")
            
        except Exception as e:
            log.error(f"AgentWorker error: {e}")
            self.agent_error.emit(str(e))
        finally:
            self.agent_finished.emit()
