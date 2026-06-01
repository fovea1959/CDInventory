import datetime
import logging
import pickle
import sys

import cv2
import pyzbar.pyzbar

import CDInventoryDao

from CDInventoryEntities import CD, Location


class BarcodeStore:
    def __init__(self):
        with open('barcodes.pickle', 'rb') as f:
            self.barcodes = pickle.load(f)

    def get(self, barcode : str = None):
        if len(barcode) == 12:
            barcode = '0' + barcode
        logging.info ("looking for %s", barcode)
        return self.barcodes.get(barcode)


def main(argv):
    barcode_store = BarcodeStore()

    # Initialize camera
    cap = cv2.VideoCapture(0)
    if False:
        # Set to an impossibly large target
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 100000)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 100000)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'YUYV'))

    # Verification (Optional: Check if the codec updated successfully)
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
    logging.info(f"Current format: {codec}")

    # Read the clipped maximum limits back
    max_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    max_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    logging.info(f"Maximum supported resolution: {max_w}x{max_h}")

    with CDInventoryDao.DAO() as dao:
        shape = None
        last_data = None
        current_location = None
        while True:
            # Read frame
            ret, frame = cap.read()
            if not ret: break

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
                    d = d.decode()
                    barcode_type = zbar[0].type
                    logging.info("Got %s: %s", barcode_type, d)

                    if barcode_type == 'QRCODE':
                        ll = d.split(',')
                        if len(ll) < 2:
                            ll.append('')
                        location_id, location_description = ll[:2]
                        current_location = dao.get_location(location_id)
                        logging.info("got location %s", current_location)
                        if current_location is None:
                            current_location = Location()
                            current_location.location_id = location_id
                            dao.session.add(current_location)
                        current_location.location_description = location_description
                        dao.session.commit()
                    elif barcode_type == 'EAN13':
                        mb_cd = barcode_store.get(d)
                        if mb_cd is not None:
                            logging.info ("musicbrainz had %s", mb_cd)
                            cd = dao.get_cd_by_barcode(d)
                            logging.info("got CD %s", cd)
                            if cd is None:
                                cd = CD()
                                cd.cd_barcode = d
                                cd.cd_title = mb_cd.get('title')
                                cd.cd_musicbrainz_id = mb_cd.get('id')
                                cd.cd_artists = ' / '.join(mb_cd.get('artists'))
                                dao.session.add(cd)
                            cd.cd_last_seen = datetime.datetime.now()
                            logging.info("current location id %s", current_location.location_id)
                            cd.cd_location_id = current_location.location_id
                            logging.info("CD location id set to %s", cd.cd_location_id)
                            logging.info("saving CD %s", cd)
                            dao.session.commit()
                        else:
                            logging.info ("Unable to find %s in musicbrainz", d)
                    else:
                        pass

            # Exit with 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    # Cleanup
    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])