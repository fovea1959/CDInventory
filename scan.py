import argparse
import datetime
import json
import logging
import pickle
import queue
import sys
import threading
import time

from typing import Optional

import cv2
import musicbrainzngs
import pyzbar.pyzbar
import soundfile as sf
import sounddevice as sd

from PIL import Image, ImageDraw

import CDInventoryDao

from CDInventoryEntities import CD, Location


save_funny_scans = True

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

    def happy(self) -> None:
        self.play('audio_data_ping.wav')

    def sad(self) -> None:
        self.play('audio_data_error.wav')


class G:
    def __init__(self):
        self.dao = None
        self.mb = None
        self.current_location = None
        self.beeper = Beeper()


class BufferlessCvCapture:
    def __init__(self, name : str = "/dev/video0", max_resolution: bool = False):
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


class MB:
    def __init__(self):
        musicbrainzngs.set_useragent("MyCDLookupApp", "0.1", "https://github.com")

    @staticmethod
    def lookup_by_barcode(barcode: str = '') -> Optional[dict]:
        query = f'barcode:"{barcode}"'

        if len(barcode) == 13:
            query = query + f' OR barcode:"{barcode[:12]}"'
            query = query + f' OR barcode:"{barcode[1:12]}"'

        if barcode[0] == '0':
            query = query + f' OR barcode:"{barcode[1:]}"'

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
        return None

    def lookup_by_release_id(self, release_id: str = ''):
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


def save_cd(g : G, barcode, mb_cd):
    musicbrainz_id = mb_cd.get('id')
    cd = g.dao.get_cd_by_musicbrainz_id(musicbrainz_id=musicbrainz_id)
    brand_new = cd is None
    logging.info("database contains CD %s", cd)
    if brand_new:
        cd = CD()
        cd.cd_barcode = barcode
    cd.cd_title = mb_cd.get('title')
    cd.cd_musicbrainz_id = musicbrainz_id
    cd.cd_artists = ' / '.join(mb_cd.get('artists'))
    if brand_new:
        g.dao.session.add(cd)
    cd.cd_last_seen = datetime.datetime.now()
    if g.current_location is not None:
        logging.info("current location id %s", g.current_location.location_id)
        cd.cd_location_id = g.current_location.location_id
        logging.info("CD location id set to %s", cd.cd_location_id)
        g.dao.session.commit()
        logging.info("saved CD %s (%s)", cd, cd.cd_location.location_description)


def save_location(g : G, location_id, location_description):
    current_location = g.dao.get_location(location_id)
    logging.info("got location %s", current_location)
    if current_location is None:
        current_location = Location()
        current_location.location_id = location_id
        g.dao.session.add(current_location)
    current_location.location_description = location_description.strip()
    g.dao.session.commit()
    g.current_location = current_location


def check_and_handle_aliased_scan(g : G, barcode_type : str = '', barcode : str = '') -> bool:
    alias = g.dao.get_barcode_alias(barcode_type, barcode)
    logging.info("got alias %s", alias)
    if alias is None:
        return False

    mb_release = g.mb.lookup_by_release_id(alias.musicbrainz_release_id)
    if mb_release is not None:
        save_cd(g, barcode, mb_release)
        g.beeper.happy()
    else:
        g.beeper.sad()
    return True


def save_funny_scan(frame, zbar):
    if not save_funny_scans:
        return
    rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    ts = datetime.datetime.now().astimezone().isoformat()

    with open(f'funny_scan_{ts}.json', 'w') as f:
        json.dump(zbar, f, default=str)

    image = Image.fromarray(rgb_image)

    fn = f'funny_scan_{ts}.png'
    image.save(fn)
    logging.info('saved %s', fn)

    draw = ImageDraw.Draw(image)
    width = 3
    for barcode in zbar:
        rect = barcode.rect
        rect_coordinates = (
            (rect.left, rect.top),
            (rect.left + rect.width, rect.top + rect.height)
        )
        logging.info("rectangle = %s", rect_coordinates)
        draw.rectangle(rect_coordinates, outline='red', width=width)

        polygon = barcode.polygon
        logging.info("polygon = %s", barcode.polygon)

        if len(barcode.polygon) > 1:
            draw.polygon(barcode.polygon, outline='red')
        else:
            x, y = polygon[0]
            gap = 20
            length = 100
            color = "red"

            # Draw Vertical Line (top and bottom parts)
            draw.line([(x, y - length), (x, y - gap)], fill=color, width=width)
            draw.line([(x, y + gap), (x, y + length)], fill=color, width=width)

            # Draw Horizontal Line (left and right parts)
            draw.line([(x - length, y), (x - gap, y)], fill=color, width=width)
            draw.line([(x + gap, y), (x + length, y)], fill=color, width=width)

    fn = f'funny_scan_{ts}_marked.png'
    image.save(fn)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--camera', default='/dev/video0')
    parser.add_argument('--max-resolution', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

    logging.info('called with %s', args)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    cam = BufferlessCvCapture(args.camera)

    g = G()
    g.mb = MB()
    g.current_location = None

    with CDInventoryDao.DAO() as dao:
        g.dao = dao
        shape = None
        last_data = None
        last_scan_time = 0
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
                now = time.time()
                if d != last_data or (now - last_scan_time) > 2:
                    last_scan_time = now
                    last_data = d
                    barcode = d.decode()
                    barcode_type = zbar[0].type
                    logging.info("Got %s: %s", barcode_type, barcode)

                    if barcode_type == 'QRCODE':
                        ok = True
                        if barcode[0] == '{':
                            qrdata = json.loads(barcode)
                            if qrdata.get('type') == 'location':
                                save_location(g, qrdata.get('id'), qrdata.get('description'))
                            else:
                                ok = False
                        else:
                            ll = barcode.split(',')
                            if len(ll) < 2:
                                ll.append('')
                            location_id, location_description = ll[:2]
                            save_location(g, location_id, location_description)

                        g.beeper.happy() if ok else g.beeper.sad()

                    elif barcode_type == 'EAN13':
                        handled = check_and_handle_aliased_scan(g, barcode_type, barcode)
                        save_funny_scan(frame, zbar)
                        if not handled:
                            mb_release = g.mb.lookup_by_barcode(barcode)
                            if mb_release is not None:
                                logging.info ("musicbrainz had %s", mb_release)
                                save_cd(g, barcode, mb_release)
                                g.beeper.happy()
                            else:
                                logging.info ("Unable to find barcode '%s' in musicbrainz", barcode)
                                g.beeper.sad()

                    elif barcode_type == 'CODE39':
                        handled = check_and_handle_aliased_scan(g, barcode_type, barcode)
                        if not handled:
                            save_funny_scan(frame, zbar)
                            g.beeper.sad()

                    elif barcode_type == 'CODE128':
                        save_funny_scan(frame, zbar)

                    else:
                        # unknown barcode type
                        save_funny_scan(frame, zbar)
                        g.beeper.sad()

            # Exit with 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    # Cleanup
    cam.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
