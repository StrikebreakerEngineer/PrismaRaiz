import threading
from pynput import keyboard

class LoopController:
    def __init__(self, stop_key=keyboard.Key.esc):
        """
        Initializes the background keyboard listener.
        Default stop key is 'ESC'.
        """
        self.keep_running = True
        self.stop_key = stop_key
        self.listener = None

    def start(self):
        """Starts monitoring the keyboard in a background thread."""
        self.keep_running = True
        self.listener = keyboard.Listener(on_press=self._on_press)
        self.listener.start()
        print(f"\n[🚀] Failsafe Active: Press '{str(self.stop_key).split('.')[-1].upper()}' to stop safely.")

    def _on_press(self, key):
        """Internal callback function for keyboard events."""
        if key == self.stop_key:
            print("\n[🛑] Interrupt signal received via keypress.")
            self.keep_running = False
            return False  # Kills the listener thread

    def stop_listener(self):
        """Manually stops the listener thread if needed."""
        if self.listener and self.listener.is_alive():
            self.listener.stop()
