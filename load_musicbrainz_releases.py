import argparse
import json
import logging
import sys

from sqlalchemy import select

import CDInventoryDao
from CDInventoryEntities import CD, MusicbrainzRelease

from utils import MB


class G:
    def __init__(self):
        self.dao = None
        self.mb = None


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int)
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

    logging.info('called with %s', args)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    g = G()
    g.mb = MB()

    with CDInventoryDao.DAO() as dao:
        g.dao = dao

        stmt = select(CD).outerjoin(
            MusicbrainzRelease, CD.cd_musicbrainz_release_id == MusicbrainzRelease.release_id
        ).where(
            CD.cd_musicbrainz_release_id != None,
            MusicbrainzRelease.release_id == None
        )

        missing = dao.session.scalars(stmt).all()
        for m in missing:
            print(m)
            r_json = g.mb.lookup_by_release_id(m.cd_musicbrainz_release_id)
            print(type(r_json), json.dumps(r_json, indent=1))

            release = MusicbrainzRelease()
            release.release_id = 

            break



if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
