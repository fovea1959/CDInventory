import datetime
import json
import logging
import queue
import threading
import time

import cv2
import musicbrainzngs
import soundfile as sf
import sounddevice as sd

from CDInventoryEntities import CD, Location
from CDInventoryDao import DAO


class Beeper:
    def __init__(self):
        self.stuff = {}
        self.load('audio_data_ping.wav')
        self.load('audio_data_error.wav')

    def load(self, filename):
        self.stuff[filename] = sf.read(filename)

    def play(self, filename):
        data, fs = self.stuff.get(filename)
        sd.play(data, fs)

    def happy(self):
        self.play('audio_data_ping.wav')

    def sad(self):
        self.play('audio_data_error.wav')


class MB:
    def __init__(self):
        musicbrainzngs.set_useragent("MyCDLookupApp", "0.1", "https://github.com")
        self.logger = logging.getLogger(self.__class__.__name__)

    def lookup_by_barcode(self, barcode: str = '') -> dict | None:
        query = f'barcode:"{barcode}"'

        if len(barcode) == 13:
            query = query + f' OR barcode:"{barcode[:12]}"'

        if barcode[0] == '0':
            query = query + f' OR barcode:"{barcode[1:]}"'

        # query = query + f' OR barcode:"5017261210685"'

        self.logger.info("query = '%s'", query)

        result = musicbrainzngs.search_releases(query=query, limit=5)

        if "release-list" in result:
            for release in result["release-list"]:
                album_name = release.get("title")
                artist = release.get("artist-credit-phrase")
                mbid = release.get("id")  # MusicBrainz Identifier

                artists = []
                for ac in release.get("artist-credit", []):
                    if type(ac) is str:  # could be "," or "&"
                        continue
                    artists.append(ac.get('name'))
                release['artists'] = artists

                self.logger.info(f"Match: {album_name} - {artist} (MBID: {mbid})")
                self.logger.debug(json.dumps(release, indent=1))

                return release
        return None

    def lookup_by_release_id(self, release_id: str = ''):
        release = musicbrainzngs.get_release_by_id(release_id, includes=['artists'])
        if release is not None:
            release = release.get('release')
        self.logger.info("got release %s", release)
        if release is not None:
            artists = []
            for ac in release.get("artist-credit", []):
                if type(ac) is str:  # could be "," or "&"
                    continue
                artists.append(ac.get('artist', {}).get('name'))
            release['artists'] = artists
        return release


class BufferlesCvCapture:
    def __init__(self, name: str = "/dev/video0", max_resolution: bool = False):
        self.name = name
        self.should_run = True
        self.running = False
        # Initialize camera
        self.cap = cv2.VideoCapture(name, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            raise Exception("Could not open video.")
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if max_resolution:
            # Set to an impossibly large target
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 100000)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 100000)
            # cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'YUYV'))
        else:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # Verification (Optional: Check if the codec updated successfully)
        fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
        logging.info(f"Current format: {codec}")

        # Read the clipped maximum limits back
        max_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        max_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        logging.info(f"Resolution: {max_w}x{max_h}")

        self.q = queue.Queue()
        t = threading.Thread(target=self._reader, daemon=True, name="Camera")
        t.start()

    # read frames as soon as they are available, keeping only most recent one
    def _reader(self):
        self.running = True
        while self.should_run:
            ret, frame = self.cap.read()
            if not ret:
                raise Exception("Could not read frame.")
            if not self.q.empty():
                try:
                    self.q.get_nowait()  # discard previous (unprocessed) frame
                except queue.Empty:
                    pass
            self.q.put(frame)
        self.running = False

    def read(self):
        im = self.q.get()
        return cv2.flip(im, -1)

    def release(self):
        self.should_run = False
        while self.running:
            time.sleep(0.1)
        self.cap.release()


def save_cd(dao: DAO, barcode, mb_cd, current_location):
    musicbrainz_id = mb_cd.get('id')
    cd = dao.get_cd_by_musicbrainz_id(musicbrainz_id=musicbrainz_id)
    brand_new = cd is None
    logging.info("database contains CD %s", cd)
    if brand_new:
        cd = CD()
        cd.cd_barcode = barcode
    cd.cd_title = mb_cd.get('title')
    cd.cd_musicbrainz_id = musicbrainz_id
    cd.cd_artists = ' / '.join(mb_cd.get('artists'))
    if brand_new:
        dao.session.add(cd)
    cd.cd_last_seen = datetime.datetime.now()
    if current_location is not None:
        logging.info("current location id %s", current_location.location_id)
        cd.cd_location_id = current_location.location_id
        logging.info("CD location id set to %s", cd.cd_location_id)
        dao.session.commit()
        logging.info("saved CD %s (%s)", cd, cd.cd_location.location_description)


def save_location(dao: DAO, location_id, location_description):
    current_location = dao.get_location(location_id)
    logging.info("got location %s", current_location)
    if current_location is None:
        current_location = Location()
        current_location.location_id = location_id
        dao.session.add(current_location)
    current_location.location_description = location_description.strip()
    dao.session.commit()
    return current_location
