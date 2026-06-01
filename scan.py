import logging
import pickle
import sys

import cv2
import pyzbar.pyzbar

import sqlalchemy
import sqlalchemy.orm

import CDInventoryDao

from CDInventoryEntities import CD, Location


class BarcodeStore:
    def __init__(self):
        with open('barcodes.pickle', 'rb') as f:
            self.barcodes = pickle.load(f)

    def find(self, barcode : str = None):
        logging.info ("looking for %s", barcode)
        return self.barcodes.get(barcode)


class DB:
    def __init__(self):
        self.session = None
        self.logger = logging.getLogger('DB')

    def __enter__(self):
        self.session = sqlalchemy.orm.Session(CDInventoryDao.engine())
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.logger.error(f"An error occurred: {exc_val}")
        self.session.rollback()
        self.session = None
        return True  # Returning True suppress

    def get_location(self, location_id : str = None):
        query = sqlalchemy.select(Location).where(Location.location_id == location_id)
        location = self.session.execute(query).scalar_one_or_none()
        return location


def main(argv):
    barcode_store = {}  # BarcodeStore()

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

    with DB() as db:
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
                        current_location = db.get_location(location_id)
                        logging.info("got location %s", current_location)
                        if current_location is None:
                            current_location = Location()
                            current_location.location_id = location_id
                            db.session.add(current_location)
                        current_location.location_description = location_description
                        db.session.commit()
                    elif barcode_type == 'EAN13':
                        if len(d) == 12:
                            d = '0' + d
                        cd = barcode_store.find(d)
                        print(cd)
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