import argparse
import json
import logging
import sys

import cv2

import pyzbar.pyzbar


import CDInventoryDao

from utils import MB, BufferlesCvCapture, save_cd, save_location, Beeper


class G:
    def __init__(self):
        self.dao = None
        self.mb = None
        self.current_location = None
        self.beeper = Beeper()


def check_and_handle_aliased_scan(g: G, barcode_type: str = '', barcode: str = '') -> bool:
    alias = g.dao.get_barcode_alias(barcode_type, barcode)
    logging.info("got alias %s", alias)
    if alias is None:
        return False

    mb_release = g.mb.lookup_by_release_id(alias.musicbrainz_release_id)
    if mb_release is not None:
        save_cd(g.dao, barcode, mb_release, g.current_location)
        g.beeper.happy()
    else:
        g.beeper.sad()
    return True


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--camera', default='/dev/video0')
    parser.add_argument('--max-resolution', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

    logging.info('called with %s', args)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    cam = BufferlesCvCapture(args.camera)

    g = G()
    g.mb = MB()
    g.current_location = None

    with CDInventoryDao.DAO() as dao:
        g.dao = dao
        shape = None
        last_data = None
        while True:
            # Read frame
            frame = cam.read()

            if shape is None:
                shape = frame.shape
                logging.info("shape = %s", shape)

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
                                g.current_location = save_location(g.dao, qrdata.get('id'), qrdata.get('description'))
                            else:
                                ok = False
                        else:
                            ll = barcode.split(',')
                            if len(ll) < 2:
                                ll.append('')
                            location_id, location_description = ll[:2]
                            g.current_location = save_location(g.dao, location_id, location_description)

                        g.beeper.happy() if ok else g.beeper.sad()

                    elif barcode_type == 'EAN13':
                        handled = check_and_handle_aliased_scan(g, barcode_type, barcode)
                        if not handled:
                                mb_release = g.mb.lookup_by_barcode(barcode)
                            if mb_release is not None:
                                logging.info("musicbrainz had %s", mb_release)
                                save_cd(g.dao, barcode, mb_release, g.current_location)
                                g.beeper.happy()
                            else:
                                logging.info("Unable to find barcode '%s' in musicbrainz", barcode)
                                g.beeper.sad()

                    elif barcode_type == 'CODE39':
                        handled = check_and_handle_aliased_scan(g, barcode_type, barcode)
                        if not handled:
                            g.beeper.sad()

                    else:
                        # unknown barcode type
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
