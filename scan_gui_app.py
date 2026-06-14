#!/usr/bin/python3

import logging
import queue
import sys
import threading

import tkinter as tk

from playwright.sync_api import sync_playwright
from playwright._impl._errors import TargetClosedError

from scan_gui_generic_app import CDInventoryGenericApp


class WrongThreadException(Exception):
    pass


class G:
    def __init__(self):
        self.gui: CDInventoryApp | None = None
        self.master: Master | None = None
        self.die = False


class Master:
    def __init__(self, g: G = None):
        self.g = g
        self.logger = logging.getLogger(self.__class__.__name__)
        self.queue = queue.Queue()

        self.thread = threading.Thread(target=self.run, daemon=True, name="master")
        self.thread.start()

    def run(self):
        while not self.g.die:
            try:
                # Check the queue without blocking the main loop
                f = self.queue.get(timeout=1)
                f()

            except queue.Empty:
                # The queue was empty; do nothing
                pass

    def do(self, f):
        self.queue.put(f)

    def check_thread(self):
        current_thread = threading.current_thread()
        if current_thread != self.thread:
            raise WrongThreadException (f"should be on thread {self.thread}, am on {current_thread}")

    def receive_scan(self, barcode_type, barcode):
        self.check_thread()

    def receive_url(self, url):
        self.check_thread()
        self.g.gui.do(lambda: self.g.gui.label_url_text.set(url))


class Browser:
    def __init__(self, g: G = None, start_url: str = None):
        self.g = g
        self.start_url = start_url

        self.logger = logging.getLogger(self.__class__.__name__)

        thread = threading.Thread(target=self.run, daemon=True, name="playwright_watcher")
        thread.start()

    def run(self):
        while not self.g.die:
            with sync_playwright() as p:
                # 1. Spawn a visible browser
                browser = p.chromium.launch_persistent_context(user_data_dir="chromium_user_data", headless=False)
                page = browser.new_page()
                context = page.context
                page_or_context = page

                '''
                # Track all network requests made by the page
                def on_request(request):
                    self.logger.debug(f"Request: {request.method} -> {request.url}")
    
                page_or_context.on("request", on_request)
                '''

                # "framenavigated" to reliably capture full page transitions on MusicBrainz
                def on_navigation(frame):
                    self.logger.info(f"Navigated to: {frame.url}")
                    self.g.master.do(lambda: self.g.master.receive_url(frame.url))

                page_or_context.on("framenavigated", on_navigation)

                # 4. Open the initial URL
                self.logger.info(f"Spawning browser for: {self.start_url}")
                try:
                    page.goto(self.start_url)
                    while not page.is_closed():
                        page.wait_for_timeout(1000)

                except TargetClosedError:
                    logging.info("browser was closed; re-opening")

                except Exception as e:
                    logging.error(f"An error occurred: {type(e)} {e}")
                    break


class CDInventoryApp(CDInventoryGenericApp):
    def __init__(self, master=None, g: G = None):
        super().__init__(master)
        self.g = g
        g.gui = self
        self.logger = logging.getLogger(self.__class__.__name__)

        self.label_url_text = self.builder.get_variable("label_url_text")

        self.logger.info("__init__ successful")

    def cb_link_url_and_scan_code(self, event=None):
        self.logger.info('bloop!')

    def do(self, f):
        self.mainwindow.after(0, f)


def main(argv):
    g = G()

    g.master = Master(g=g)
    g.browser = Browser(g=g, start_url='https://www.musicbrainz.org')

    logging.info("browser started")

    app = CDInventoryApp(g=g)
    app.run()
    logging.info("tkinter run() is done")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    main(sys.argv[1:])
