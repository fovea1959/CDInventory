import datetime
import functools
import json
import logging
import queue
import threading
import time

import cv2
import jsonpath_ng
import musicbrainzngs
import soundfile as sf
import sounddevice as sd

from CDInventoryEntities import CD, Location, MusicbrainzRelease
from CDInventoryDao import DAO


class ContentFilter(logging.Filter):
    def __init__(self, banned_words):
        super().__init__()
        self.banned_words = banned_words

    def filter(self, record):
        # record.getMessage() gets the fully formatted string message
        log_message = record.getMessage()

        # Return False to drop the log if any banned word is found
        if any(word in log_message for word in self.banned_words):
            return False
        return True  # Return True to keep the log


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
        musicbrainzngs.set_useragent("CDInventory", "0.1", "dwegscheid@sbcglobal.net")
        musicbrainzngs.set_rate_limit(limit_or_interval=1.5, new_requests=1)
        self.logger = logging.getLogger(self.__class__.__name__)
        # self.logger.setLevel(logging.DEBUG)
        mb_logger = logging.getLogger("musicbrainzngs")
        mb_filter = ContentFilter(banned_words=["uncaught attribute type-id", "uncaught <first-release-date>"])
        mb_logger.addFilter(mb_filter)

    def lookup_by_barcode(self, barcode: str = '') -> dict | None:
        query = f'barcode:"{barcode}"'

        if len(barcode) == 13:
            query = query + f' OR barcode:"{barcode[:12]}"'

        if barcode[0] == '0':
            query = query + f' OR barcode:"{barcode[1:]}"'

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
        release = musicbrainzngs.get_release_by_id(release_id, includes=['artists', 'labels', 'release-groups', 'recordings'])
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


class CvCapture:
    def __init__(self, name: str = "/dev/video0", max_resolution: bool = False):
        self.logger = logging.getLogger(self.__class__.__name__)
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
        self.logger.debug(f"Current format: {codec}")

        # Read the clipped maximum limits back
        max_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        max_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self.logger.debug(f"Resolution: {max_w}x{max_h}")

        self.q = queue.Queue()
        self.thread = threading.Thread(target=self._reader, name="Camera", daemon=True)
        self.thread.start()

    # read frames as soon as they are available, keeping only most recent one
    def _reader(self):
        self.running = True
        self.logger.info("thread starting")
        try:
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
        finally:
            self.logger.info("thread is cleaning up")
            self.q.put(None)  # wake up consumers
            self.cap.release()
            self.logger.info("thread is finished")
            self.running = False

    def read(self):
        try:
            im = self.q.get(timeout=1.0)
            return cv2.flip(im, -1)
        except queue.Empty:
            return None

    def release(self):
        self.logger.info("telling my thread to die...")
        self.should_run = False
        self.logger.info("...waiting for my thread to die...")
        self.thread.join()
        self.logger.info("...thread is dead")


def save_cd(dao: DAO, barcode, mb_cd, current_location):
    musicbrainz_id = mb_cd.get('id')
    cd = dao.get_cd_by_musicbrainz_id(musicbrainz_id=musicbrainz_id)
    brand_new = cd is None
    logging.info("database contains CD %s", cd)
    if brand_new:
        cd = CD()
        cd.cd_barcode = barcode
    cd.cd_title = mb_cd.get('title')
    cd.cd_musicbrainz_release_id = musicbrainz_id
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


def check_ean_for_badness(ean: str) -> str | None:
    # 1. Clean the string by removing dashes and spaces
    clean_code = "".join(ean.split()).replace("-", "")

    # 2. Check if length is valid for EAN-13 or EAN-8 and contains only digits
    if len(clean_code) not in (8, 13):
        return f"invalid length {len(clean_code)}, should be 8 or 13"

    if not clean_code.isdigit():
        return f"non-digit present"

    # 3. Separate payload from the existing check digit
    payload = clean_code[:-1]
    existing_check_digit = int(clean_code[-1])

    # 4. Calculate checksum based on GS1 rules (reverse weights 3 and 1)
    total_sum = 0
    for i, digit in enumerate(reversed(payload)):
        weight = 3 if i % 2 == 0 else 1
        total_sum += int(digit) * weight

    calculated_check_digit = (10 - (total_sum % 10)) % 10

    # 5. Compare calculated check digit with the actual one
    if calculated_check_digit != existing_check_digit:
        return f"bad check digit {existing_check_digit}, should be {calculated_check_digit}"
    return None


class QueueHandler(logging.Handler):
    """Sends logging records to a thread-safe queue."""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(record)


@functools.lru_cache()
def get_compiled_path(expression: str) -> jsonpath_ng.JSONPath:
    try:
        return jsonpath_ng.parse(expression)
    except Exception as e:
        # Reuses the exact same string inside the error handling block
        raise ValueError(f"Failed parsing '{expression}'. Error: {e}")


def extract_data(json_data: dict, path_string: str):
    # This lookup is O(1) if already cached, otherwise it parses and saves it.
    compiled_path = get_compiled_path(path_string)
    return [match.value for match in compiled_path.find(json_data)]

def extract_datum(json_data: dict, path_string: str):
    # This lookup is O(1) if already cached, otherwise it parses and saves it.
    compiled_path = get_compiled_path(path_string)
    rv = [match.value for match in compiled_path.find(json_data)]
    if len(rv) == 0:
        return None
    elif len(rv) > 1:
        raise ValueError(f"{path_string} return too many entries")
    else:
        return rv[0]


def fill_in_release_from_mb_json(release: MusicbrainzRelease, musicbrainz_release_dict: dict):
    release.release_group_id = extract_datum(musicbrainz_release_dict, 'release-group.id')
    release.title = extract_datum(musicbrainz_release_dict, 'title')
    barcode = extract_datum(musicbrainz_release_dict, 'barcode')
    release.barcode = None if barcode is None or len(barcode) == 0 else barcode
    release.artists = extract_datum(musicbrainz_release_dict, 'artist-credit-phrase')

    label_info_list = extract_datum(musicbrainz_release_dict, 'label-info-list')
    ll = []
    for label_info in label_info_list:
        ll_and_cn = []
        label_name = extract_datum(label_info, 'label.name')
        if label_name is not None and label_name != '':
            ll_and_cn.append(label_name)
        catalog_number = extract_datum(label_info, 'catalog-number')
        if catalog_number is not None and catalog_number != '':
            ll_and_cn.append(catalog_number)
        if len(ll_and_cn) > 0:
            ll.append(": ".join(ll_and_cn))
    release.catalog_numbers = "; ".join(ll) if len(ll) > 0 else None

def compact_json(o) -> str:
    return json.dumps(o, sort_keys=True, separators=(',', ':'))
