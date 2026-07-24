import time
import queue
import threading
from playwright.sync_api import sync_playwright

# A thread-safe queue to pass URLs from the main thread to the daemon
job_queue = queue.Queue()


def playwright_daemon_worker():
    """This worker runs entirely inside the background daemon thread."""
    print("Daemon thread started.")

    # You MUST initialize sync_playwright inside the thread it will be used in
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        while True:
            # Block until a job becomes available
            url = job_queue.get()

            # None acts as a "poison pill" to break the loop for graceful exit
            if url is None:
                job_queue.task_done()
                break

            try:
                page = context.new_page()
                page.goto(url)
                print(f"[Daemon] Visited: {url} | Title: {page.title()}")
                page.close()
            except Exception as e:
                print(f"[Daemon] Error processing {url}: {e}")
            finally:
                job_queue.task_done()

        browser.close()
    print("Daemon thread shutting down cleanly.")


# --- Usage Example ---
if __name__ == "__main__":
    # 1. Create and start the daemon thread
    daemon_thread = threading.Thread(target=playwright_daemon_worker, daemon=True)
    daemon_thread.start()

    # 2. Push jobs into the queue from the main thread
    print("[Main] Submitting jobs...")
    job_queue.put("https://example.com")
    job_queue.put("https://playwright.dev")

    # 3. Simulate the main thread doing other work
    print("[Main] Doing other work while Playwright runs in background...")
    time.sleep(5)

    # 4. Gracefully shut down the daemon thread
    print("[Main] Requesting daemon shutdown...")
    job_queue.put(None)  # Signal the worker to break its loop
    daemon_thread.join(timeout=5)
    print("[Main] Exiting program.")
