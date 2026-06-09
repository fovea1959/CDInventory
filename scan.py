import argparse
import datetime
import json
import logging
import pickle
import queue
import sys
import threading
import time

import cv2
import musicbrainzngs
import pyzbar.pyzbar
import soundfile as sf
import sounddevice as sd

import CDInventoryDao

from CDInventoryEntities import CD, Location


class BufferlesCvCapture:
    def __init__(self, name, max_resolution: bool = False):
        self.name = name
        self.should_run = True
        self.running = False
        # Initialize camera
        self.cap = cv2.VideoCapture("/dev/video2", cv2.CAP_V4L2)
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
        t = threading.Thread(target=self._reader)
        t.daemon = True
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


class BarcodeStore:
    def __init__(self):
        with open('barcodes.pickle', 'rb') as f:
            self.barcodes = pickle.load(f)

    def get(self, barcode : str = None):
        if len(barcode) == 12:
            barcode = '0' + barcode
        logging.info ("looking for %s", barcode)
        return self.barcodes.get(barcode)


class MB:
    def __init__(self):
        musicbrainzngs.set_useragent("MyCDLookupApp", "0.1", "https://github.com")

    def lookup_by_barcode(self, barcode: str = None):
        query = f'barcode:"{barcode}"'

        if len(barcode) == 13:
            query = query + f' OR barcode:"{barcode[:12]}"'

        if barcode[0] == '0':
            query = query + f' OR barcode:"{barcode[1:]}"'

        # query = query + f' OR barcode:"5017261210685"'

        logging.info("query = '%s'", query)

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

                logging.info(f"Match: {album_name} - {artist} (MBID: {mbid})")
                logging.debug(json.dumps(release, indent=1))

                return release

    def lookup_by_release_id(self, release_id: str = None):
        release = musicbrainzngs.get_release_by_id(release_id, includes=['artists'])
        if release is not None:
            release = release.get('release')
        logging.info("got release %s", release)
        if release is not None:
            artists = []
            for ac in release.get("artist-credit", []):
                if type(ac) is str:  # could be "," or "&"
                    continue
                artists.append(ac.get('artist', {}).get('name'))
            release['artists'] = artists
        return release


def save_cd(dao, barcode, mb_cd, current_location):
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


def save_location(dao, location_id, location_description):
    current_location = dao.get_location(location_id)
    logging.info("got location %s", current_location)
    if current_location is None:
        current_location = Location()
        current_location.location_id = location_id
        dao.session.add(current_location)
    current_location.location_description = location_description.strip()
    dao.session.commit()
    return current_location


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-resolution', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

    logging.info('called with %s', args)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    barcode_store = {}  # BarcodeStore()

    cam = BufferlesCvCapture(1)

    mb = MB()
    with CDInventoryDao.DAO() as dao:
        shape = None
        last_data = None
        current_location = None
        while True:
            # Read frame
            frame = cam.read()

            if shape is None:
                shape = frame.shape
                logging.info ("shape = %s", shape)

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
                    logging.info("Got %s: %s", barcode_type, barcode)

                    if barcode_type == 'QRCODE':
                        ok = True
                        if barcode[0] == '{':
                            qrdata = json.loads(barcode)
                            if qrdata.get('type') == 'location':
                                current_location = save_location(dao, qrdata.get('id'), qrdata.get('description'))
                            else:
                                ok = False
                        else:
                            ll = barcode.split(',')
                            if len(ll) < 2:
                                ll.append('')
                            location_id, location_description = ll[:2]
                            current_location = save_location(dao, location_id, location_description)

                        data, fs = sf.read('audio_data_ping.wav') if ok else sf.read('audio_data_error.wav')
                        sd.play(data, fs)
                        # sd.wait()  # Wait until the sound finishes playing

                    elif barcode_type == 'EAN13':
                        mb_release = barcode_store.get(barcode)
                        if mb_release is None:
                            mb_release = mb.lookup_by_barcode(barcode)
                        if mb_release is not None:
                            logging.info ("musicbrainz had %s", mb_release)

                            save_cd(dao, barcode, mb_release, current_location)

                            data, fs = sf.read('audio_data_ping.wav')
                            sd.play(data, fs)
                            # sd.wait()  # Wait until the sound finishes playing
                        else:
                            data, fs = sf.read('audio_data_error.wav')
                            sd.play(data, fs)
                            # sd.wait()  # Wait until the sound finishes playing

                            logging.info ("Unable to find barcode '%s' in musicbrainz", barcode)
                    elif barcode_type == 'CODE39':
                        alias = dao.get_barcode_alias(barcode)
                        logging.info("got alias %s", alias)
                        mb_release = mb.lookup_by_release_id(alias.musicbrainz_release_id)
                        if mb_release is not None:
                            save_cd(dao, barcode, mb_release, current_location)

                            data, fs = sf.read('audio_data_ping.wav')
                            sd.play(data, fs)
                            # sd.wait()  # Wait until the sound finishes playing
                        else:
                            data, fs = sf.read('audio_data_error.wav')
                            sd.play(data, fs)
                            # sd.wait()  # Wait until the sound finishes playing

                    else:
                        # unknown barcode type
                        data, fs = sf.read('audio_data_error.wav')
                        sd.play(data, fs)
                        # sd.wait()  # Wait until the sound finishes playing


            # Exit with 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    # Cleanup
    cam.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
