import tkinter as tk
import threading
import queue
import time


class ThreadedApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Thread-Safe Tkinter")
        self.root.geometry("300x150")

        # 1. Initialize a thread-safe FIFO queue
        self.msg_queue = queue.Queue()

        # 2. Set up simple UI elements
        self.label = tk.Label(root, text="Status: Idle", font=("Arial", 12))
        self.label.pack(pady=20)

        self.btn = tk.Button(root, text="Start Heavy Task", command=self.start_task)
        self.btn.pack(pady=10)

        # 3. Start polling the queue immediately in the main thread
        self.check_queue()

    def start_task(self):
        """Disables the button and launches the background thread."""
        self.btn.config(state="disabled")
        self.label.config(text="Status: Processing...")

        # Target your heavy function and mark the thread as a daemon
        worker = threading.Thread(target=self.background_worker, daemon=True)
        worker.start()

    def background_worker(self):
        """Runs strictly in the background. NO direct Tkinter manipulation here."""
        time.sleep(3)  # Simulating a 3-second network request or heavy calculation
        result = "Task Complete! Data processed successfully."

        # Safely push the result into the queue
        self.msg_queue.put(result)

    def check_queue(self):
        """Runs on the main thread, continuously checking for data."""
        try:
            # Check the queue without blocking the main loop
            message = self.msg_queue.get_nowait()

            # Safely modify the GUI here because we are on the main thread
            self.label.config(text=f"Status: {message}")
            self.btn.config(state="normal")

        except queue.Empty:
            # The queue was empty; do nothing
            pass

        finally:
            # Schedule this loop to run again in 100 milliseconds
            self.root.after(100, self.check_queue)


if __name__ == "__main__":
    root = tk.Tk()
    app = ThreadedApp(root)
    root.mainloop()
