import logging
import os
import sys

import sqlalchemy
import sqlalchemy.orm

from CDInventoryEntities import *

logger = logging.getLogger("dao")

defaultFilename = "CDInventory.db"


def engine(filename: str = '', echo: bool = False):
    if filename == '':
        filename = defaultFilename
    return sqlalchemy.create_engine(f'sqlite:///{filename}', echo=echo)


class DAO:
    def __init__(self, db_filename: str = ''):
        self.session = None
        self.logger = logging.getLogger('DB')
        self.db_filename = db_filename

    def __enter__(self):
        self.session = sqlalchemy.orm.Session(engine(self.db_filename))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.logger.error(f"An error occurred: {exc_val}")
        self.session.rollback()
        self.session = None
        return False  # Returning True suppress

    def get_location(self, location_id: str = '') -> Optional[Location]:
        query = sqlalchemy.select(Location).where(Location.location_id == location_id)
        rv = self.session.execute(query).scalar_one_or_none()
        return rv

    def get_cd_by_barcode(self, barcode: str = '') -> Optional[CD]:
        query = sqlalchemy.select(CD).where(CD.cd_barcode == barcode)
        rv = self.session.execute(query).scalar_one_or_none()
        return rv

    def get_cd_by_musicbrainz_id(self, musicbrainz_id: str = '') -> Optional[CD]:
        query = sqlalchemy.select(CD).where(CD.cd_musicbrainz_id == musicbrainz_id)
        rv = self.session.execute(query).scalar_one_or_none()
        return rv

    def get_barcode_alias(self, barcode_type: str = '', barcode: str = '') -> Optional[BarcodeAlias]:
        query = (sqlalchemy.select(BarcodeAlias)
                 .where(BarcodeAlias.scan_encoding == barcode_type, BarcodeAlias.scan_text == barcode))
        rv = self.session.execute(query).scalar_one_or_none()
        return rv


# noinspection PyUnusedLocal
def main(argv):
    try:
        os.remove(defaultFilename)
        # pass
    except FileNotFoundError:
        pass
    Base.metadata.create_all(engine())


if __name__ == '__main__':
    main(sys.argv[1:])
