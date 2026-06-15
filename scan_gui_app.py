#!/usr/bin/python3

import datetime
import json
import logging
import queue
import re
import sys
import threading

import cv2
import pyzbar.pyzbar

from playwright.sync_api import sync_playwright
from playwright._impl._errors import TargetClosedError

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
        self.barcode_reader: CVBarcodeReader | None = None
        self.mb = utils.MB()
        self.die = False


class Browser:
    def __init__(self, g: G = None, start_url: str = None):
        self.g = g
        self.start_url = start_url

        self.logger = logging.getLogger(self.__class__.__name__)

        self.thread = threading.Thread(target=self.run, daemon=True, name="playwright_watcher")
        self.thread.start()

    def run(self):
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

                self.logger.info(f"Spawning browser for: {self.start_url}")
                try:
                    page.goto(self.start_url)
                    while (not self.g.die) and (not page.is_closed()):
                        page.wait_for_timeout(1000)

                except TargetClosedError:
                    self.logger.info("browser was closed; re-opening")

                except Exception as e:
                    self.logger.error(f"An error occurred: {type(e)} {e}")
                    break

    def done(self):
        self.thread.join()


class Master:
    def __init__(self, g: G = None):
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
        self.logger.info("master received %s barcode: %s", barcode_type, barcode)
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
            self._handle_cd_barcode(barcode)

        elif barcode_type == 'CODE39':
            self._handle_cd_barcode(barcode)

        else:
            # unknown barcode type
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

        self.logger.info('CD before commit = %s', self.current_cd)
        self.dao.session.commit()
        self.logger.info('CD after commit = %s', self.current_cd)

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
            self.logger.info("Unable to find barcode '%s' in musicbrainz", barcode)
            self.g.gui.sad()

        self.dao.session.commit()
        self.g.gui.set_cd(self.current_cd)

    def receive_url(self, url):
        self._do(lambda: self._receive_url(url))

    def _receive_url(self, url):
        self.logger.info("master received URL: %s", url)
        self.check_thread()

        m = re.match(
            r'^https://musicbrainz.org/release/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$',
            url, flags=re.ASCII | re.IGNORECASE)
        if m:
            release_id = m.group(1)
            searching_release = {'id': '* searching *'}
            self.g.gui.set_musicbrainz_release(searching_release)
            self.selected_release = self.g.mb.lookup_by_release_id(release_id)
            self.g.gui.set_musicbrainz_release(self.selected_release)

    def _handle_location_scan(self, location_id, location_description):
        self.selected_location = utils.save_location(self.dao, location_id, location_description)


class CVBarcodeReader:
    def __init__(self, g: G | None = None, name: str = '/dev/video0'):
        self.g = g
        self.cam = utils.BufferlesCvCapture(name)
        self.logger = logging.getLogger(self.__class__.__name__)

        self.thread = threading.Thread(target=self.run, daemon=True, name="Barcode")
        self.thread.start()

    def run(self):
        shape = None
        last_data = None
        try:
            while not self.g.die:
                # Read frame
                frame = self.cam.read()

                if shape is None:
                    shape = frame.shape
                    self.logger.info("shape = %s", shape)

                # Process: Convert to grayscale and blur
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                cv2.imshow('Gray', gray)

                zbar = pyzbar.pyzbar.decode(gray)
                if len(zbar) > 0:
                    d = zbar[0].data
                    if d != last_data:
                        last_data = d
                        barcode = d.decode()
                        barcode_type = zbar[0].type
                        self.logger.info("Got %s: %s", barcode_type, barcode)

                        self.g.master.receive_scan(barcode_type, barcode)

                # Exit with 'q'
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        finally:
            self.logger.info("cleaning up")
            # Cleanup
            self.cam.release()
            cv2.destroyAllWindows()
            self.logger.info("all done")

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

    def __init__(self, master=None, g: G = None):
        super().__init__(master)
        self.g = g
        g.gui = self
        self.logger = logging.getLogger(self.__class__.__name__)

        self.logger.info("__init__ successful")

    def cb_tie_release_to_cd(self, event=None):
        self.logger.info('bloop!')
        self.g.master.update_current_cd_from_musicbrainz()

    def set_text_field(self, name, value):
        self.mainwindow.after(0, lambda: self._set_text_field(name, value))
        
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

    def happy(self):
        pass

    def sad(self):
        pass


def main(argv):
    g = G()

    g.master = Master(g=g)
    g.browser = Browser(g=g, start_url='https://www.musicbrainz.org/search')
    g.barcodeReader = CVBarcodeReader(g=g)

    logging.info("browser started")

    app = CDInventoryApp(g=g)
    app.run()
    g.die = True
    logging.info("tkinter run() is done")

    g.barcodeReader.done()
    g.browser.done()
    g.master.done()

    '''
    QObject::killTimer: Timers cannot be stopped from another thread
    QObject::~QObject: Timers cannot be stopped from another thread
    
    caused by doing opencv2 imshow or waitkey not on main thread.
    
    https://forum.opencv.org/t/qobject-timers-cannot-be-stopped-from-another-thread-when-using-waitkey-function/17903/2
    '''


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s")
    main(sys.argv[1:])
