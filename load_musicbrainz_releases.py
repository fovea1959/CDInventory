import argparse
import datetime
import json
import logging
import sys

from sqlalchemy import select

import CDInventoryDao
import utils
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

    commit_batchsize = 50

    with CDInventoryDao.DAO() as dao:
        g.dao = dao

        stmt = select(CD).outerjoin(
            MusicbrainzRelease, CD.cd_musicbrainz_release_id == MusicbrainzRelease.release_id
        ).where(
            CD.cd_musicbrainz_release_id.is_not(None),
            MusicbrainzRelease.release_id.is_(None)
        )

        missing = dao.session.scalars(stmt).all()
        for i, m in enumerate(missing):
            if args.limit is not None and i >= args.limit:
                logging.info('hit limit!')
                break

            logging.info("database had %s", m)
            rd = g.mb.lookup_by_release_id(m.cd_musicbrainz_release_id)
            rj = utils.compact_json(rd)

            # print(type(musicbrainz_release_dict), json.dumps(musicbrainz_release_dict, indent=1))
            #with open("load_musicbrainz.json", "w") as file:
            #    json.dump(musicbrainz_release_dict, file, indent=1, sort_keys=True)

            release = MusicbrainzRelease()
            release.release_id = utils.extract_datum(rd, 'id')
            release.last_downloaded = datetime.datetime.now().astimezone()
            release.json_text = rj
            utils.fill_in_release_from_mb_json(release, rd)
            dao.session.add(release)

            if i % commit_batchsize == (commit_batchsize - 1):
                logging.info ("commit...")
                dao.session.commit()

        logging.info("commit...")
        dao.session.commit()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
