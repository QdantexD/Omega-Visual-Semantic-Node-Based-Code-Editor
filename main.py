import threading
import time
import uvicorn
from ui.main_ui import start_ui


def run_backend():
    uvicorn.run("backend.server:app", host="127.0.0.1", port=8000, log_level="info")


def start_backend_in_thread():
    t = threading.Thread(target=run_backend, daemon=True)
    t.start()
    time.sleep(0.5)


if __name__ == "__main__":
    start_backend_in_thread()
    start_ui()
    