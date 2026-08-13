from PySide6.QtCore import QThread, Signal
from orchestrator import run_full_generation
from logger import log


class AgentWorker(QThread):
    agent_started = Signal()
    agent_finished = Signal()
    agent_error = Signal(str)
    agent_response = Signal(str)
    agent_stream_chat = Signal(str)
    agent_section_changed = Signal(str)
    agent_doc_updated = Signal()   # fires after every incremental docx save
    agent_stats_updated = Signal(dict)

    def __init__(self, docx_path: str, user_message: str, truth_path: str = None, parent=None):
        super().__init__(parent)
        self.docx_path = docx_path
        self.user_message = user_message
        self.truth_path = truth_path  # None = preset; str = uploaded truth.json

    def run(self):
        self.agent_started.emit()
        log.info(f"AgentWorker started — topic: {self.user_message!r}, "
                 f"truth_path: {self.truth_path or 'preset'}")
        try:
            def stream_chat_callback(chunk: str):
                self.agent_stream_chat.emit(chunk)

            def section_callback(section_name: str):
                self.agent_section_changed.emit(section_name)

            def doc_updated_callback():
                self.agent_doc_updated.emit()
                
            def stats_callback(stats: dict):
                self.agent_stats_updated.emit(stats)

            run_full_generation(
                topic=self.user_message,
                docx_path=self.docx_path,
                stream_chat_callback=stream_chat_callback,
                section_callback=section_callback,
                doc_updated_callback=doc_updated_callback,
                stats_callback=stats_callback,
                truth_path=self.truth_path,
            )

            log.info("AgentWorker completed successfully.")
            self.agent_response.emit("\n\n*Generation complete.*")

        except Exception as e:
            log.error(f"AgentWorker error: {e}")
            self.agent_error.emit(str(e))
        finally:
            self.agent_finished.emit()
