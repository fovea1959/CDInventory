#!/usr/bin/env python3

import argparse
import datetime
import json
import logging
import sys

from sqlalchemy import select

import cd_inventory_dao
import mp3_information
import utils
from cd_inventory_entities import MP3
from utils import extract_datum


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

    with cd_inventory_dao.DAO() as dao:
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

            mp3_information.fill_in_mp3_from_dict(mp3, mp3_dict)
            mp3.updated_time = now
            mp3.json_text = utils.compact_json(mp3_dict)

            if i % commit_batchsize == (commit_batchsize - 1):
                logging.info("commit...")
                dao.session.commit()

        logging.info("commit...")
        dao.session.commit()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
