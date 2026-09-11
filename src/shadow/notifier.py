"""Queue native tray notifications so simultaneous events are not overwritten."""
from collections import deque
import logging
import time


class Notifier:
    def __init__(self, icon):
        self.icon = icon
        self.pending = deque(maxlen=100)
        self.last_sent = 0.0

    def send(self, title, message):
        self.pending.append((title, message))

    def tick(self):
        if self.pending and self.icon.visible and time.monotonic() - self.last_sent >= 5:
            title, message = self.pending.popleft()
            try:
                self.icon.notify(message[:250], title[:63])
            except Exception:
                logging.exception("Windows notification failed")
            self.last_sent = time.monotonic()

    def clear(self):
        self.pending.clear()
