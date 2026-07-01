import argparse
import json
import logging
import sys

from sqlalchemy import select

import CDInventoryDao
from CDInventoryEntities import MusicbrainzRelease, CD


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int)
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

    logging.info('called with %s', args)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    commit_batchsize = 50

    with CDInventoryDao.DAO() as dao:
        stmt = select(CDInventoryDao.CD, MusicbrainzRelease).outerjoin(
            MusicbrainzRelease,
            CDInventoryDao.CD.cd_musicbrainz_release_id == MusicbrainzRelease.release_id
        )

        results = dao.session.execute(stmt)

        modifications = 0
        for i, result in enumerate(results):
            cd: CD
            release: MusicbrainzRelease
            cd, release = result

            is_dirty = bool(dao.session.new or dao.session.dirty or dao.session.deleted)

            logging.info('%d %d %s', i+1, cd.cd_id, is_dirty)

            if release is None:
                logging.info('%s has no match', cd)
                continue

            logging.info ("'%s' -> '%s'", release.artists, cd.cd_artists)
            cd.cd_artists = release.artists

            modifications += 1

            if modifications % commit_batchsize == 0:
                logging.info("commit @ %d...", modifications)
                dao.session.commit()

        logging.info("commit (final)...")
        dao.session.commit()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
