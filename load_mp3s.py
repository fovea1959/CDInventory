#!/usr/bin/env python3

import argparse
import datetime
import json
import logging
import sys

from dateutil import parser
from sqlalchemy import select

import CDInventoryDao
import utils
from CDInventoryEntities import MP3
from utils import extract_data, extract_datum


def fill_in_mp3_from_dict(mp3: MP3, mp3_dict: dict):
    mp3.path = extract_datum(mp3_dict, 'path')
    mp3.title = extract_datum(mp3_dict, 'TIT2')
    mp3.track_artists = extract_datum(mp3_dict, 'TPE1')
    mp3.album_artists = extract_datum(mp3_dict, 'TPE2')
    mp3.release_id = extract_datum(mp3_dict, '"TXXX(MusicBrainz Album Id)"')
    mp3.release_group_id = extract_datum(mp3_dict, '"TXXX(MusicBrainz Release Group Id)"')
    mp3.track_id = extract_datum(mp3_dict, '"TXXX(MusicBrainz Release Track Id)"')
    # recording_id
    s = extract_datum(mp3_dict, "info.mtime")
    mp3.mtime = parser.parse(s).astimezone()
    # encoded_time
    s = extract_datum(mp3_dict, "TDEN")
    if s is not None:
        mp3.encoded_time = datetime.datetime.fromisoformat(s).astimezone()


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('file')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

    logging.info('called with %s', args)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    commit_batchsize = 50

    with CDInventoryDao.DAO() as dao:
        with open(args.file, 'r') as f:
            data = json.load(f)

        now = datetime.datetime.now().astimezone()

        for i, mp3_dict in enumerate(data):
            if args.limit is not None and i >= args.limit:
                logging.info('hit limit!')
                break

            # logging.info("json had %s", mp3_dict)

            path = extract_datum(mp3_dict, 'path')

            statement = select(MP3).where(MP3.path == path)
            mp3 = dao.session.scalars(statement).first()

            if mp3 is None:
                mp3 = MP3()
                dao.session.add(mp3)

            fill_in_mp3_from_dict(mp3, mp3_dict)
            mp3.updated_time = now
            mp3.json_text = utils.compact_json(mp3_dict)

            if i % commit_batchsize == (commit_batchsize - 1):
                logging.info ("commit...")
                dao.session.commit()

        logging.info("commit...")
        dao.session.commit()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
