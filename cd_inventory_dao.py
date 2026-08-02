import logging
import sys

import sqlalchemy
import sqlalchemy.orm

from cd_inventory_entities import *

logger = logging.getLogger("dao")

defaultFilename = "CDInventory.db"


def engine(filename: str = '', echo: bool = False):
    if filename == '':
        filename = defaultFilename
    return sqlalchemy.create_engine(f'sqlite:///{filename}', echo=echo)


class DAO:
    def __init__(self, db_filename: str = '', echo: bool = False):
        self.session = None
        self.logger = logging.getLogger('DB')
        self.db_filename = db_filename
        self.echo = echo

    def __enter__(self):
        self.session = sqlalchemy.orm.Session(engine(self.db_filename, echo=self.echo))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.logger.error(f"An error occurred: {exc_val}")
            self.session.rollback()
            self.session = None
            return False  # Returning True suppress
        return True

    def get_location(self, location_id: str = '') -> Optional[Location]:
        query = sqlalchemy.select(Location).where(Location.location_id == location_id)
        rv = self.session.execute(query).scalar_one_or_none()
        return rv

    def get_all_locations(self):
        query = sqlalchemy.select(Location)
        rv = self.session.scalars(query).all()
        return rv

    def get_cd_by_barcode(self, barcode: str = '') -> Optional[CD]:
        query = sqlalchemy.select(CD).where(CD.cd_barcode == barcode)
        rv = self.session.execute(query).scalar_one_or_none()
        return rv

    def get_all_cds(self):
        query = sqlalchemy.select(CD)
        rv = self.session.scalars(query).all()
        return rv

    def get_all_unripped_cds(self):
        query = (
            sqlalchemy.select(CD)
            .outerjoin(MP3, CD.cd_musicbrainz_release_id == MP3.release_id)
            .where(MP3.release_id.is_(None))  # Filters out found records
        )
        rv = self.session.scalars(query).all()
        return rv

    def get_cd_by_musicbrainz_id(self, musicbrainz_id: str = '') -> Optional[CD]:
        query = sqlalchemy.select(CD).where(CD.cd_musicbrainz_release_id == musicbrainz_id)
        rv = self.session.execute(query).scalar_one_or_none()
        return rv

    def get_all_mp3s(self):
        query = sqlalchemy.select(MP3)
        rv = self.session.scalars(query).all()
        return rv

    def get_mp3_by_path(self, path: str = '') -> Optional[MP3]:
        query = sqlalchemy.select(MP3).where(MP3.path == path)
        rv = self.session.execute(query).scalar_one_or_none()
        return rv


# noinspection PyUnusedLocal
def main(argv):
    Base.metadata.create_all(engine())


if __name__ == '__main__':
    main(sys.argv[1:])
