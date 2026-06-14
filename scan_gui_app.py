#!/usr/bin/python3

import logging
import queue
import sys
import threading

import tkinter as tk

from playwright.sync_api import sync_playwright

from scan_gui_generic_app import CDInventoryGenericApp


class G:
    def __init__(self):
        self.browser_thread = None
        self.browser = None
        self.gui_q = queue.Queue()


class Browser:
    def __init__(self, g: G = None, start_url: str = None):
        self.g = g
        self.start_url = start_url

        self.logger = logging.getLogger(self.__class__.__name__)

    def run(self):
        with sync_playwright() as p:
            # 1. Spawn a visible browser
            browser = p.chromium.launch_persistent_context(user_data_dir="chromium_user_data", headless=False)
            page = browser.new_page()
            context = page.context
            page_or_context = page

            # Track all network requests made by the page
            def on_request(request):
                self.logger.debug(f"Request: {request.method} -> {request.url}")

            page_or_context.on("request", on_request)

            # "framenavigated" to reliably capture full page transitions on MusicBrainz
            def on_navigation(frame):
                self.g.gui_q.put(frame.url)
                self.logger.info(f"Navigated to: {frame.url}")

            page_or_context.on("framenavigated", on_navigation)

            # 4. Open the initial URL
            self.logger.info(f"Spawning browser for: {self.start_url}")
            try:
                page.goto(self.start_url)
                while not page.is_closed():
                    page.wait_for_timeout(1000)

            except Exception as e:
                logging.error(f"An error occurred: {e}")


class CDInventoryApp(CDInventoryGenericApp):
    def __init__(self, master=None, g: G = None):
        super().__init__(master)
        self.g = g
        self.logger = logging.getLogger(self.__class__.__name__)

        self.label_url_text = self.builder.get_variable("label_url_text")

        self.logger.info("__init__ successful")

    def run(self):
        self.check_queue()
        super().run()

    def cb_link_url_and_scan_code(self, event=None):
        self.logger.info('bloop!')

    def check_queue(self):
        """Runs on the main thread, continuously checking for data."""
        try:
            # Check the queue without blocking the main loop
            message = self.g.gui_q.get_nowait()

            # Safely modify the GUI here because we are on the main thread
            self.label_url_text.set(message)

        except queue.Empty:
            # The queue was empty; do nothing
            pass

        finally:
            # Schedule this loop to run again in 100 milliseconds
            self.mainwindow.after(100, self.check_queue)


def main(argv):
    g = G()

    g.browser = Browser(g=g, start_url='https://www.musicbrainz.org')
    g.browser_thread = threading.Thread(target=g.browser.run, daemon=True)
    g.browser_thread.start()

    logging.info("browser started")

    app = CDInventoryApp(g=g)
    app.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    main(sys.argv[1:])
