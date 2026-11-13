
import os
import sys
import uuid
import queue
import threading
import tempfile
import subprocess

from pathlib import Path

import soundfile as sf
import uvicorn

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QComboBox,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QSystemTrayIcon,
    QMenu,
)


# ---------------- RESOURCE PATHS ----------------

def resource_path(relative_path):
    """Find resources in development and in a PyInstaller bundle."""
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)


DOCK_ICON = resource_path(
    "image/KittenVoiceIcons/KittenVoice-Dock.png"
)

MENU_ICON = resource_path(
    "image/KittenVoiceIcons/KittenVoice-MenuBar.png"
)


# ---------------- SETTINGS ----------------

API_HOST = "127.0.0.1"
API_PORT = 8000

api = FastAPI(title="Local Voice App")

speech_queue = queue.Queue()

state = {
    "model": None,
    "voices": [],
    "default_voice": "Bruno",
    "model_ready": threading.Event(),
    "model_started": False,
    "model_error": None,
}


# ---------------- UI SIGNALS ----------------

class Signals(QObject):
    log = Signal(str)
    status = Signal(str)
    voices = Signal(list)


signals = Signals()


# ---------------- API ----------------

class SpeechRequest(BaseModel):
    text: str
    voice: str | None = None


@api.post("/speak", status_code=202)
def speak(request: SpeechRequest):
    text = request.text.strip()

    if not text:
        raise HTTPException(400, "Text cannot be empty")

    speech_queue.put((text, request.voice))

    return {
        "success": True,
        "message": "Text added to speech queue"
    }


@api.get("/health")
def health():
    return {
        "status": "running",
        "model_ready": state["model_ready"].is_set()
        and state["model"] is not None
    }


# ---------------- MODEL LOADING ----------------

def load_model():
    try:
        signals.status.emit("Loading KittenTTS model...")
        signals.log.emit("Loading KittenTTS 2...")

        from kittenml import KittenTTS

        model = KittenTTS(
            "KittenML/kitten-tts-2",
            backend="mlx"
        )

        state["model"] = model
        state["voices"] = list(model.available_voices)

        if state["voices"]:
            state["default_voice"] = (
                "Bruno" if "Bruno" in state["voices"]
                else state["voices"][0]
            )

        signals.voices.emit(state["voices"])
        signals.log.emit("KittenTTS model loaded successfully!")
        signals.status.emit("Model ready")

    except Exception as error:
        state["model_error"] = str(error)
        signals.log.emit(f"Model error: {error}")
        signals.status.emit("Model loading failed")

    finally:
        state["model_ready"].set()


# ---------------- SPEECH WORKER ----------------

def speech_worker():
    while True:
        item = speech_queue.get()

        if item is None:
            break

        text, requested_voice = item

        try:
            state["model_ready"].wait()

            model = state["model"]

            if model is None:
                raise RuntimeError(
                    state["model_error"] or "Model is not available"
                )

            voice = requested_voice or state["default_voice"]

            if voice not in state["voices"]:
                raise ValueError(f"Unknown voice: {voice}")

            signals.log.emit(f"Speaking: {text}")

            audio = model.generate(text, voice=voice)

            audio_path = os.path.join(
                tempfile.gettempdir(),
                f"kitten_{uuid.uuid4().hex}.wav"
            )

            sf.write(audio_path, audio, model.sample_rate)

            subprocess.run(
                ["/usr/bin/afplay", audio_path],
                check=False
            )

            if os.path.exists(audio_path):
                os.remove(audio_path)

            signals.log.emit("Finished speaking.")

        except Exception as error:
            signals.log.emit(f"Speech error: {error}")

        finally:
            speech_queue.task_done()


# ---------------- DESKTOP UI ----------------

class VoiceApp(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Kitten Voice")
        self.setWindowIcon(QIcon(DOCK_ICON))
        self.setMinimumSize(480, 520)

        self.server = None
        self.server_thread = None
        self.allow_quit = False

        self.build_ui()

        signals.log.connect(self.add_log)
        signals.status.connect(self.set_status)
        signals.voices.connect(self.update_voices)

        self.setup_tray()

        self.worker = threading.Thread(
            target=speech_worker,
            daemon=True
        )
        self.worker.start()

    # ---------------- MENU BAR ----------------

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)

        self.tray.setIcon(QIcon(MENU_ICON))
        self.tray.setToolTip("Kitten Voice")

        menu = QMenu()

        show_action = QAction("Show Kitten Voice", self)
        show_action.triggered.connect(self.show_window)
        menu.addAction(show_action)

        menu.addSeparator()

        start_action = QAction("Start Listening", self)
        start_action.triggered.connect(self.start_listening)
        menu.addAction(start_action)

        stop_action = QAction("Stop Listening", self)
        stop_action.triggered.connect(self.stop_listening)
        menu.addAction(stop_action)

        menu.addSeparator()

        quit_action = QAction("Quit Kitten Voice", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()

    def quit_app(self):
        self.allow_quit = True

        if self.server:
            self.server.should_exit = True

        speech_queue.put(None)

        self.close()
        QApplication.quit()

    # ---------------- MAIN WINDOW ----------------

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        title = QLabel("Kitten Voice")
        title.setStyleSheet(
            "font-size: 28px; font-weight: bold;"
        )

        subtitle = QLabel(
            "Your local text-to-speech listener"
        )

        self.status_label = QLabel("Not listening")
        self.status_label.setStyleSheet(
            "color: #d69e36; font-weight: bold;"
        )

        self.start_button = QPushButton("Start Listening")
        self.stop_button = QPushButton("Stop Listening")

        self.start_button.clicked.connect(self.start_listening)
        self.stop_button.clicked.connect(self.stop_listening)

        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)

        endpoint_title = QLabel("API ENDPOINT")
        endpoint_title.setStyleSheet(
            "font-weight: bold; color: #999;"
        )

        self.endpoint = QLabel(
            "http://127.0.0.1:8000/speak"
        )

        self.voice_box = QComboBox()
        self.voice_box.addItem("Loading voices...")
        self.voice_box.setEnabled(False)
        self.voice_box.currentTextChanged.connect(
            self.change_voice
        )

        voice_title = QLabel("VOICE")
        log_title = QLabel("ACTIVITY")

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText(
            "Incoming messages will appear here..."
        )

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)
        layout.addSpacing(8)
        layout.addWidget(endpoint_title)
        layout.addWidget(self.endpoint)
        layout.addWidget(voice_title)
        layout.addWidget(self.voice_box)
        layout.addWidget(log_title)
        layout.addWidget(self.log_box)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #17191f;
                color: #eeeeee;
                font-size: 14px;
            }

            QPushButton {
                background: #6655cc;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-weight: bold;
            }

            QPushButton:hover {
                background: #7868dd;
            }

            QPushButton:disabled {
                background: #444;
                color: #999;
            }

            QComboBox, QTextEdit {
                background: #242731;
                border: 1px solid #383b48;
                border-radius: 8px;
                padding: 9px;
                color: white;
            }
        """)

    # ---------------- API SERVER ----------------

    def start_listening(self):
        if self.server_thread and self.server_thread.is_alive():
            self.add_log("Server is already running.")
            return

        self.server = uvicorn.Server(
            uvicorn.Config(
                api,
                host=API_HOST,
                port=API_PORT,
                log_level="warning"
            )
        )

        self.server_thread = threading.Thread(
            target=self.server.run,
            daemon=True
        )
        self.server_thread.start()

        self.status_label.setText(
            "Listening · Loading model if needed..."
        )

        self.start_button.setEnabled(False)
        self.add_log("Starting local API...")

        if not state["model_started"]:
            state["model_started"] = True

            threading.Thread(
                target=load_model,
                daemon=True
            ).start()

    def stop_listening(self):
        if self.server:
            self.server.should_exit = True
            self.server = None

        self.start_button.setEnabled(True)
        self.status_label.setText("Not listening")
        self.add_log("API server stopped.")

    # ---------------- VOICE MANAGEMENT ----------------

    def change_voice(self, voice):
        if voice and voice in state["voices"]:
            state["default_voice"] = voice

    def update_voices(self, voices):
        self.voice_box.clear()
        self.voice_box.addItems(voices)
        self.voice_box.setEnabled(bool(voices))

        if state["default_voice"] in voices:
            self.voice_box.setCurrentText(
                state["default_voice"]
            )

    # ---------------- LOGGING ----------------

    def add_log(self, message):
        self.log_box.append(message)

    def set_status(self, message):
        if self.server is not None:
            self.status_label.setText(
                f"Listening · {message}"
            )
        else:
            self.status_label.setText(message)

    # ---------------- WINDOW CLOSE ----------------

    def closeEvent(self, event):
        if not self.allow_quit:
            self.hide()
            event.ignore()
            return

        if self.server:
            self.server.should_exit = True

        event.accept()


# ---------------- START APP ----------------

if __name__ == "__main__":
    app = QApplication([])

    app.setWindowIcon(QIcon(DOCK_ICON))
    app.setQuitOnLastWindowClosed(False)

    window = VoiceApp()
    window.show()

    app.exec()
