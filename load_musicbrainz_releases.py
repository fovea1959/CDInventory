#!/usr/bin/env python3

import argparse
import datetime
import logging
import sys

from sqlalchemy import select

import CDInventoryDao
import utils
from CDInventoryEntities import CD, MusicbrainzRelease, MP3

from utils import MB


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

    logging.info('called with %s', args)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    mb = MB()

    commit_batchsize = 50

    with CDInventoryDao.DAO() as dao:
        stmt = select(CD).outerjoin(
            MusicbrainzRelease, CD.cd_musicbrainz_release_id == MusicbrainzRelease.release_id
        ).where(
            CD.cd_musicbrainz_release_id.is_not(None),
            MusicbrainzRelease.release_id.is_(None)
        )

        cd_release_ids = set()
        missing = dao.session.scalars(stmt).all()
        cd: CD
        for cd in missing:
            logging.info("CD: %s %s", cd.cd_musicbrainz_release_id, cd)
            cd_release_ids.add(cd.cd_musicbrainz_release_id)
        logging.info("CDs were missing %d releases", len(cd_release_ids))

        mp3_release_ids = set()
        stmt = select(MP3)
        my_mp3s = dao.session.scalars(stmt).all()
        mp3: MP3
        for mp3 in my_mp3s:
            mp3_release_ids.add(mp3.release_id)
        logging.info("MP3s have %d releases", len(mp3_release_ids))

        release_ids = cd_release_ids | mp3_release_ids

        logging.info("need to check %d releases", len(release_ids))
        i = 0
        for release_id in release_ids:
            if release_id is None:
                continue
            stmt = select(MusicbrainzRelease).where(MusicbrainzRelease.release_id == release_id)
            release = dao.session.scalars(stmt).one_or_none()

            logging.debug("database search for %s -> %s", release_id, release)

            if (release is None) or args.refresh:
                logging.debug("going to musicbrainz")
                its_new = False
                if release is None:
                    logging.debug("creating MusicbrainzRelease object")
                    release = MusicbrainzRelease()
                    its_new = True

                try:
                    rd = mb.lookup_by_release_id(release_id)
                    if its_new:
                        release.release_id = release_id
                        logging.debug("adding MusicbrainzRelease object to session")
                        dao.session.add(release)
                except Exception:
                    logging.error("could not lookup %s", release_id)
                    continue
                release.release_id = utils.extract_datum(rd, 'id')

                if release.release_id is None:
                    logging.error("no id in %s", rd)
                release.last_downloaded = datetime.datetime.now().astimezone()
                release.json_text = utils.compact_json(rd)
                utils.fill_in_release_from_mb_json(release, rd)
                logging.debug("saving %s", release)

                i += 1

                if i % commit_batchsize == (commit_batchsize - 1):
                    logging.info("commit @ %d...", i)
                    dao.session.commit()

        if i > 0:
            logging.info("committing last of %d...", i)
            dao.session.commit()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
