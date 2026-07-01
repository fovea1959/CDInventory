import argparse
import json
import logging
import sys

from sqlalchemy import select

import CDInventoryDao
import utils
from CDInventoryEntities import MusicbrainzRelease


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
        stmt = select(MusicbrainzRelease)
        all_releases = dao.session.scalars(stmt).all()

        modifications = 0
        release: MusicbrainzRelease
        for i, release in enumerate(all_releases):
            # print(release.json_text)
            utils.fill_in_release_from_mb_json(release, release.raw_data)

            modifications += 1

            if modifications % commit_batchsize == 0:
                logging.info("commit @ %d...", modifications)
                dao.session.commit()

        logging.info("commit @ %d (final)", modifications)
        dao.session.commit()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
