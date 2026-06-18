#!/usr/bin/python3

import datetime
import json
import logging
import queue
import re
import sys
import threading
import time

from logging.handlers import RotatingFileHandler

import tkinter as tk
from tkinter import font as tkfont

import cv2
import PIL
import pyzbar.pyzbar

from PIL import Image, ImageTk

from playwright.sync_api import sync_playwright
from playwright._impl._errors import TargetClosedError

from pythonjsonlogger.json import JsonFormatter

import utils
from CDInventoryDao import DAO
from CDInventoryEntities import CD, Location

from scan_gui_generic_app import CDInventoryGenericApp


class WrongThreadException(Exception):
    pass


class G:
    def __init__(self):
        self.gui: CDInventoryApp | None = None
        self.master: Master | None = None
        self.barcode_reader: CvBarcodeReader | None = None
        self.mb = utils.MB()
        self.die = False


class Browser:
    def __init__(self, g: G | None = None, start_url: str | None = None):
        self.g = g
        self.start_url = start_url

        self.logger = logging.getLogger(self.__class__.__name__)

        self.thread = threading.Thread(target=self.run, daemon=True, name="browser")
        self.thread.start()

    def run(self):
        self.logger.info('starting')
        while not self.g.die:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(user_data_dir="chromium_user_data", headless=False)
                page = browser.new_page()
                context = page.context
                page_or_context = page or context

                '''
                # Track all network requests made by the page
                def on_request(request):
                    self.logger.debug(f"Request: {request.method} -> {request.url}")

                page_or_context.on("request", on_request)
                '''

                # "framenavigated" to reliably capture full page transitions on MusicBrainz
                def on_navigation(frame):
                    self.logger.info(f"Navigated to: {frame.url}")
                    self.g.master.receive_url(frame.url)

                page_or_context.on("framenavigated", on_navigation)

                self.logger.info("Spawning browser for: %s", self.start_url)
                try:
                    page.goto(self.start_url)
                    while (not self.g.die) and (not page.is_closed()):
                        page.wait_for_timeout(1000)
                    self.logger.info("died or browser closed")

                except TargetClosedError:
                    self.logger.info("browser was closed; re-opening")

                except Exception as e:
                    self.logger.error(f"An error occurred: {type(e)} {e}")
                    break

                finally:
                    self.logger.info('closing browser')
                    context.close()

        self.logger.info('finished')

    def done(self):
        self.thread.join()


class Master:
    def __init__(self, g: G | None = None):
        self.g = g
        self.logger = logging.getLogger(self.__class__.__name__)
        self.queue = queue.Queue()
        self.dao = DAO()
        self.selected_location: Location | None = None
        self.selected_release: dict | None = None
        self.current_cd: CD | None = None
        self.mb = utils.MB()

        self.thread = threading.Thread(target=self.run, daemon=True, name="master")
        self.thread.start()

    def done(self):
        self.thread.join()

    def run(self):
        self.logger.info('starting')
        with self.dao:
            while not self.g.die:
                try:
                    # Check the queue without blocking the main loop
                    f = self.queue.get(timeout=1)
                    if f is None:
                        self.logger.warning('got None from master queue')
                    else:
                        self.logger.info('got %s from master queue', f)
                        f()

                except queue.Empty:
                    # The queue was empty; do nothing
                    pass
        self.logger.info('finished')

    def _do(self, f):
        self.logger.info('putting %s on the master queue', f)
        self.queue.put(f)

    def check_thread(self):
        current_thread = threading.current_thread()
        if current_thread != self.thread:
            raise WrongThreadException(f"should be on thread {self.thread}, am on {current_thread}")

    def receive_scan(self, barcode_type, barcode):
        self._do(lambda: self._receive_scan(barcode_type, barcode))

    def _receive_scan(self, barcode_type, barcode):
        self.logger.important("master received %s barcode: %s", barcode_type, barcode)
        self.check_thread()
        if barcode_type == 'QRCODE':
            ok = True
            if barcode[0] == '{':
                qrdata = json.loads(barcode)
                if qrdata.get('type') == 'location':
                    self._handle_location_barcode(qrdata.get('id'), qrdata.get('description'))
                else:
                    ok = False
            else:
                ll = barcode.split(',')
                if len(ll) < 2:
                    ll.append('')
                location_id, location_description = ll[:2]
                self._handle_location_barcode(location_id, location_description)

            self.g.gui.happy() if ok else self.g.gui.sad()

        elif barcode_type == 'EAN13':
            badness = utils.check_ean_for_badness(barcode)
            if badness is None:
                self._handle_cd_barcode(barcode)
            else:
                # self.g.gui.toast(f"Bad scan '{barcode}': {badness}")
                self.logger.warning("%s scan '%s' problem: '%s'", barcode_type, barcode, badness)

        elif barcode_type == 'CODE39':
            self._handle_cd_barcode(barcode)

        else:
            # unknown barcode type
            self.logger.warning("can't handle %s scan '%s'", barcode_type, barcode,)
            #self.g.gui.toast(f"Bad {barcode_type} scan '{barcode}'")
            self.g.gui.sad()

    def update_current_cd_from_musicbrainz(self):
        self._do(lambda: self._update_current_cd_from_musicbrainz())

    def _update_current_cd_from_musicbrainz(self):
        if self.current_cd is None or self.selected_release is None:
            self.g.gui.sad()
            return
        self.current_cd.cd_musicbrainz_id = self.selected_release['id']
        self.current_cd.cd_title = self.selected_release['title']
        self.current_cd.cd_artists = ' / '.join(self.selected_release.get('artists', ''))

        self.logger.debug('CD before commit = %s', self.current_cd)
        self.dao.session.commit()
        self.logger.debug('CD after commit = %s', self.current_cd)
        self.logger.verbose("updated from musicbrainz, saved CD", extra={'cd': self.current_cd.to_dict()})

        self.g.gui.set_cd(self.current_cd)

    def _handle_location_barcode(self, location_id, location_description):
        self.selected_location = utils.save_location(self.dao, location_id, location_description)
        self.g.gui.set_location(self.selected_location)

    def _handle_cd_barcode(self, barcode):
        self.current_cd = self.dao.get_cd_by_barcode(barcode)
        if self.current_cd is None:
            self.current_cd = CD()
            self.current_cd.cd_barcode = barcode
            self.dao.session.add(self.current_cd)

        self.current_cd.cd_last_seen = datetime.datetime.now()

        if self.selected_location is not None:
            self.current_cd.cd_location_id = self.selected_location.location_id

        if self.current_cd.cd_musicbrainz_id is not None:
            self.selected_release = self.mb.lookup_by_release_id(self.current_cd.cd_musicbrainz_id)
        else:
            self.selected_release = self.mb.lookup_by_barcode(barcode)

        self.g.gui.set_musicbrainz_release(self.selected_release)

        if self.selected_release is not None:
            self.logger.info("musicbrainz had %s", self.selected_release)
            self._update_current_cd_from_musicbrainz()
            self.g.gui.happy()
        else:
            self.logger.important("Unable to find barcode '%s' in musicbrainz", barcode)
            self.g.gui.sad()

        self.dao.session.commit()
        self.logger.verbose("read barcode, saved CD", extra={'cd': self.current_cd.to_dict()})

        self.g.gui.set_cd(self.current_cd)

    def receive_url(self, url):
        self._do(lambda: self._receive_url(url))

    def _receive_url(self, url):
        self.logger.info("master received URL: %s", url)
        self.check_thread()

        m = re.match(
            r'^https://musicbrainz.org/release/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\??.*$',
            url, flags=re.ASCII | re.IGNORECASE)
        if m:
            release_id = m.group(1)
            searching_release = {'id': '* searching *'}
            self.g.gui.set_musicbrainz_release(searching_release)
            self.selected_release = self.g.mb.lookup_by_release_id(release_id)
            self.g.gui.set_musicbrainz_release(self.selected_release)

    def _handle_location_scan(self, location_id, location_description):
        self.selected_location = utils.save_location(self.dao, location_id, location_description)


class CvBarcodeReader:
    def __init__(self, g: G | None = None, name: str = '/dev/video0'):
        self.g = g
        self.cam = utils.CvCapture(name)
        self.logger = logging.getLogger(self.__class__.__name__)

        self.thread = threading.Thread(target=self.run, daemon=True, name="Barcode")
        self.thread.start()

    def run(self):
        self.logger.info("starting")
        shape = None
        last_data = None
        last_scan_time = 0
        try:
            while not self.g.die:
                # Read frame
                frame = self.cam.read()

                if shape is None:
                    shape = frame.shape
                    self.logger.info("shape = %s", shape)

                # Process: Convert to grayscale and blur
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                #cv2.imshow('Gray', gray)

                pil_image = PIL.Image.fromarray(gray)
                self.g.gui.set_image(pil_image)

                zbar = pyzbar.pyzbar.decode(gray)
                if len(zbar) > 0:
                    d = zbar[0].data
                    now = time.time()
                    if d != last_data or (now - last_scan_time > 2):
                        last_scan_time = now
                        last_data = d
                        barcode = d.decode()
                        barcode_type = zbar[0].type
                        self.logger.info("Got %s: %s", barcode_type, barcode)

                        self.g.master.receive_scan(barcode_type, barcode)

                # Exit with 'q'
                #if cv2.waitKey(1) & 0xFF == ord('q'):
                #    break

        finally:
            self.logger.info("cleaning up")
            # Cleanup
            self.cam.release()
            # cv2.destroyAllWindows()
            self.logger.info("finished")

    def done(self):
        self.thread.join()


class CDInventoryApp(CDInventoryGenericApp):
    TV_MUSICBRAINZ_RELEASE_ID = 'tv_musicbrainz_release_id'
    TV_MUSICBRAINZ_RELEASE_TITLE = 'tv_musicbrainz_release_title'
    TV_MUSICBRAINZ_RELEASE_ARTIST = 'tv_musicbrainz_release_artist'
    TV_CD_BARCODE = 'tv_cd_barcode'
    TV_CD_LOCATION_ID = 'tv_cd_location_id'
    TV_CD_LOCATION = 'tv_cd_location'
    TV_CD_RELEASE_ID = 'tv_cd_release_id'
    TV_CD_RELEASE_TITLE = 'tv_cd_release_title'
    TV_CD_RELEASE_ARTIST = 'tv_cd_release_artist'
    TV_LOCATION = 'tv_location'
    TV_LOCATION_ID = 'tv_location_id'

    def __init__(self, master=None, g: G = None, log_queue: queue.Queue = None, logging_formatter=None):
        super().__init__(master)
        self.g = g
        g.gui = self
        self.logger = logging.getLogger(self.__class__.__name__)

        self.running = False

        self.image_canvas = self.builder.get_object('image_canvas', master)
        self.tk_image = None

        self.log_text = self.builder.get_object('log_text', master)
        current_font = tkfont.Font(font=self.log_text.cget("font"))
        bold_font = tkfont.Font(family=current_font.actual("family"), size=current_font.actual("size"), weight="bold")
        self.log_text.tag_configure("warning", foreground="red")
        self.log_text.tag_configure("error", foreground="red", font=bold_font)
        self.log_queue = log_queue
        self.logging_formatter = logging_formatter if logging_formatter \
            else logging.Formatter('%(levelname)s %(name)s %(message)s')
        self.mainwindow.after(100, self.poll_log_queue)

        self.logger.info("__init__ successful")

    def center_window(self):
        # Force an update of idle tasks to get accurate dimensions before mapping
        self.mainwindow.update_idletasks()

        # Get screen dimensions
        screen_width = self.mainwindow.winfo_screenwidth()
        screen_height = self.mainwindow.winfo_screenheight()

        # Get window dimensions
        win_width = self.mainwindow.winfo_width()
        win_height = self.mainwindow.winfo_height()

        # Calculate X and Y coordinates
        x = (screen_width // 2) - (win_width // 2)
        y = (screen_height // 2) - (win_height // 2)

        # Set the geometry
        self.mainwindow.geometry(f'{win_width}x{win_height}+{x}+{y}')

    def run(self):
        self.running = True
        self.logger.info("centering window")
        self.center_window()
        self.logger.info("starting")
        super().run()
        self.running = False
        self.g.die = True
        self.logger.info("finished")

    def cb_tie_release_to_cd(self, event=None):
        self.g.master.update_current_cd_from_musicbrainz()

    def _do(self, f):
        if self.running:
            self.mainwindow.after(0, f)

    def set_text_field(self, name, value):
        self._do(lambda: self._set_text_field(name, value))
        
    def _set_text_field(self, name, value):
        string_var = self.builder.get_variable(name)
        string_var.set(value)
        
    def set_location(self, location: Location | None = None):
        if location is None:
            self.set_text_field(self.TV_LOCATION_ID, '')
            self.set_text_field(self.TV_LOCATION, '')
        else:
            self.set_text_field(self.TV_LOCATION_ID, location.location_id)
            self.set_text_field(self.TV_LOCATION, location.location_description)

    def set_cd(self, cd: CD | None = None):
        if cd is None:
            self.set_text_field(self.TV_CD_BARCODE, '')
            self.set_text_field(self.TV_CD_RELEASE_ID, '')
            self.set_text_field(self.TV_CD_RELEASE_TITLE, '')
            self.set_text_field(self.TV_CD_RELEASE_ARTIST, '')
            self.set_text_field(self.TV_CD_LOCATION_ID, '')
            self.set_text_field(self.TV_CD_LOCATION, '')
        else:
            self.set_text_field(self.TV_CD_BARCODE, cd.cd_barcode)
            self.set_text_field(self.TV_CD_RELEASE_ID, cd.cd_musicbrainz_id or '')
            self.set_text_field(self.TV_CD_RELEASE_TITLE, cd.cd_title or '')
            self.set_text_field(self.TV_CD_RELEASE_ARTIST, cd.cd_artists or '')
            self.set_text_field(self.TV_CD_LOCATION_ID, cd.cd_location_id or '')
            if cd.cd_location is not None:
                self.set_text_field(self.TV_CD_LOCATION, cd.cd_location.location_description or '')
            else:
                self.set_text_field(self.TV_CD_LOCATION, '')

    def set_musicbrainz_release(self, release: dict | None = None):
        if release is None:
            self.set_text_field(self.TV_MUSICBRAINZ_RELEASE_ID, '')
            self.set_text_field(self.TV_MUSICBRAINZ_RELEASE_TITLE, '')
            self.set_text_field(self.TV_MUSICBRAINZ_RELEASE_ARTIST, '')
        else:
            self.set_text_field(self.TV_MUSICBRAINZ_RELEASE_ID, release.get('id'))
            self.set_text_field(self.TV_MUSICBRAINZ_RELEASE_TITLE, release.get('title'))
            self.set_text_field(self.TV_MUSICBRAINZ_RELEASE_ARTIST, release.get('artists'))

    def set_image(self, image):
        # self.logger.info("calling set_image")
        self._do(lambda: self._set_image(image))
        # self.logger.info("set_image done")

    def _set_image(self, image):
        # self.logger.info("calling _set_image")

        img_width, img_height = image.size
        canvas_width = self.image_canvas.winfo_width()
        canvas_height = self.image_canvas.winfo_height()

        # 3. Calculate the maximum scaling factor to maintain aspect ratio
        ratio = min(canvas_width / img_width, canvas_height / img_height)
        new_width = int(img_width * ratio)
        new_height = int(img_height * ratio)

        # 4. Resize the PIL image using the calculated dimensions
        resized_img = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(resized_img)

        center_x = canvas_width // 2
        center_y = canvas_height // 2

        self.image_id = self.image_canvas.create_image(
            center_x, center_y, image=self.tk_image, anchor=tk.CENTER
        )

        # self.logger.info("_set_image done")

    def toast(self, message: str = '', duration=2500):
        self._do(lambda: self._toast(message, duration))

    def _toast(self, message, duration):
            # Create a borderless popup window
            toast = tk.Toplevel(self.mainwindow)
            toast.overrideredirect(True)

            # Style the window
            toast.config(bg="#333333")
            label = tk.Label(toast, text=message, fg="white", bg="#333333", padx=15, pady=10, font=("Arial", 10))
            label.pack()

            # Position the toast window relative to the main window
            self.mainwindow.update_idletasks()
            x = self.mainwindow.winfo_x() + (self.mainwindow.winfo_width() // 2) - (toast.winfo_reqwidth() // 2)
            y = self.mainwindow.winfo_y() + self.mainwindow.winfo_height() - 70
            toast.geometry(f"+{x}+{y}")

            # Automatically close the toast window after the delay
            toast.after(duration, toast.destroy)

    def happy(self):
        pass

    def sad(self):
        pass

    def poll_log_queue(self):
        """Checks the queue and writes records to the text widget."""
        while True:
            try:
                # Look for records without blocking the GUI loop
                record = self.log_queue.get_nowait()
            except queue.Empty:
                break
            else:
                # Format and append message to widget
                message = self.logging_formatter.format(record)

                self.log_text.configure(state='normal')
                tag = record.levelname.lower()
                self.log_text.insert(tk.END, message + '\n', tag)
                self.log_text.configure(state='disabled')

                # Autoscroll to the absolute bottom
                self.log_text.yview(tk.END)

        # Re-queue this polling method after 100 milliseconds
        self.mainwindow.after(100, self.poll_log_queue)


VERBOSE_LEVEL_NUM = 15
IMPORTANT_LEVEL_NUM = 25


def verbose(self, message, *args, **kws):
    if self.isEnabledFor(VERBOSE_LEVEL_NUM):
        # Yes, logger._log is a semi-private API, but this is the standard way
        self._log(VERBOSE_LEVEL_NUM, message, args, **kws)


def important(self, message, *args, **kws):
    if self.isEnabledFor(IMPORTANT_LEVEL_NUM):
        # Yes, logger._log is a semi-private API, but this is the standard way
        self._log(IMPORTANT_LEVEL_NUM, message, args, **kws)


def setup_custom_log_level():
    logging.addLevelName(VERBOSE_LEVEL_NUM, "VERBOSE")
    logging.Logger.verbose = verbose
    logging.addLevelName(IMPORTANT_LEVEL_NUM, "IMPORTANT")
    logging.Logger.important = important


def main(argv):
    setup_custom_log_level()

    logger = logging.getLogger('')
    logger.setLevel(VERBOSE_LEVEL_NUM)

    file_handler = RotatingFileHandler(
        "app.log",
        maxBytes=(10 * 1024 * 1024),
        backupCount=5
    )
    file_handler.setFormatter(JsonFormatter(
        fmt="{levelname} {message} {name} {asctime} {threadName} {levelno}", style="{"
    ))
    file_handler.setLevel(VERBOSE_LEVEL_NUM)
    logger.addHandler(file_handler)

    log_queue = queue.Queue()
    queue_handler = utils.QueueHandler(log_queue=log_queue)
    queue_handler.setLevel(IMPORTANT_LEVEL_NUM)
    logger.addHandler(queue_handler)

    logger.debug("debug")
    logger.verbose("verbose")
    logger.info("info")
    logger.important("important")
    logger.warning("warning")
    logger.error("error")

    g = G()

    g.master = Master(g=g)
    g.browser = Browser(g=g, start_url='https://www.musicbrainz.org/search')
    g.barcodeReader = CvBarcodeReader(g=g)

    app = CDInventoryApp(g=g, log_queue=log_queue)
    app.run()

    logging.info('waiting for barcodeReader thread...')
    g.barcodeReader.done()
    logging.info('...barcodeReader thread done')
    logging.info('waiting for browser thread...')
    g.browser.done()
    logging.info('...browser thread done')
    logging.info('waiting for master thread')
    g.master.done()
    logging.info('...master thread done')
    logging.info('all done!')


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(levelname)-8s l=%(name)-15s %(message)s")
    #                    format="%(levelname)-8s l=%(name)-15s t=%(threadName)-10s %(message)s")
    main(sys.argv[1:])
