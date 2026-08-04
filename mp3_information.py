import base64
import dataclasses
import datetime
import logging
import pathlib

import eyed3
import eyed3.core
import eyed3.id3
from dateutil import parser
from eyed3.id3.frames import TextFrame, DateFrame

from cd_inventory_entities import MP3
from utils import extract_datum, compact_json

logger = logging.getLogger(__name__)


class ListOnCollisionDict(dict):
    def __setitem__(self, key, value):
        if key in self:
            current_value = self[key]
            # Convert existing single item into a list if it isn't one already
            if not isinstance(current_value, list):
                super().__setitem__(key, [current_value, value])
            else:
                current_value.append(value)
        else:
            # First insertion: store as a single, raw value
            super().__setitem__(key, value)


class MP3InfoExtractor:
    def __init__(self, root_dir: pathlib.Path = None):
        self.root_path = pathlib.Path(root_dir).absolute() if root_dir is not None else None

    def get_information(self, path, mtime: datetime.datetime = None):
        audio_file = eyed3.core.load(path)
        if audio_file and audio_file.info and audio_file.tag:
            r_path = path = pathlib.Path(audio_file.path)
            if self.root_path is not None:
                try:
                    r_path = path.relative_to(self.root_path)
                except ValueError:
                    pass

            info = dataclasses.asdict(audio_file.info)
            info['vbr'], info['bitrate'] = audio_file.info.bit_rate
            if mtime is None:  # don't need to refetch if we already know it
                mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime)
            info['mtime'] = mtime

            j = ListOnCollisionDict(
                    path=str(r_path),
                    info=info,
                    tag_version='.'.join(str(i) for i in audio_file.tag.version),
                    )

            for frame_id in audio_file.tag.frame_set:
                frame_set = audio_file.tag.frame_set[frame_id]
                for f in frame_set:
                    k = frame_id.decode()
                    if isinstance(f, eyed3.id3.frames.UserTextFrame):
                        k = k + "(" + f.description + ")"
                    if isinstance(f, eyed3.id3.frames.UniqueFileIDFrame):
                        k = k + "(" + f.owner_id.decode() + ")"
                    if isinstance(f, eyed3.id3.frames.DescriptionLangTextFrame):
                        k = k + "(" + f.description + ")[" + f.lang.decode() + "]"
                    j[k] = self.v(f)
            return j
        return None

    def v(self, frame):
        if isinstance(frame, eyed3.id3.frames.DescriptionLangTextFrame):
            return frame.text
        elif isinstance(frame, eyed3.id3.frames.TextFrame):
            return frame.text
        elif isinstance(frame, eyed3.id3.frames.UrlFrame):
            return frame.url
        elif isinstance(frame, eyed3.id3.frames.UniqueFileIDFrame):
            rv = frame.uniq_id
            # noinspection PyBroadException
            try:
                rv = rv.decode()
            except Exception:
                pass
            return rv
        elif isinstance(frame, eyed3.id3.frames.ImageFrame):
            rv = dict(mime_type=frame.mime_type, length=len(frame.image_data))
            pt = frame.picture_type
            try:
                pt = frame.picTypeToString(pt)
            except ValueError:
                pass
            rv['picture_type'] = pt
            if len(frame.description) > 0:
                rv['description'] = frame.description
            return rv
        elif isinstance(frame, eyed3.id3.frames.MusicCDIdFrame):
            return self.ascii_ize(frame.toc)
        elif isinstance(frame, eyed3.id3.frames.PrivateFrame):
            return dict(owner_id=frame.owner_id.decode(), owner_data=self.ascii_ize(frame.owner_data))
        else:
            return str(type(frame)) + " " + str(frame.render())

    @staticmethod
    def ascii_ize(v):
        return base64.urlsafe_b64encode(v).decode('utf-8').replace('=', '')


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
    if isinstance(s, datetime.datetime):
        mp3.mtime = s
    elif isinstance(s, str):
        mp3.mtime = parser.parse(s).astimezone()
    elif s is None:
        mp3.mtime = None
    else:
        raise ValueError(f"Can't extract info.mtime from {mp3_dict}")
    # encoded_time
    s = extract_datum(mp3_dict, "TDEN")
    if s is not None:
        mp3.encoded_time = datetime.datetime.fromisoformat(s).astimezone()
    mp3.json_text = compact_json(mp3_dict, default=str)


'''
class FixedEyeD3CoreDate(eyed3.core.Date):
    def __str__(self):
        # behaviour
        s = "%d" % self.year
        if self.month:
            s += "-%s" % str(self.month).rjust(2, '0')
            if self.day:
                s += "-%s" % str(self.day).rjust(2, '0')
                if self.hour is not None:
                    s += "T%s" % str(self.hour).rjust(2, '0')
                    if self.minute is not None:
                        s += ":%s" % str(self.minute).rjust(2, '0')
                        if self.second is not None:
                            s += ":%s" % str(self.second).rjust(2, '0')
        return s


def setDateFrame(tag, frame_id, date_val):
    if frame_id in tag.frame_set:
        tag.frame_set[frame_id][0].date = date_val
    else:
        tag.frame_set[frame_id] = DateFrame(frame_id, date_val)
'''


def set_encoded_time(path: pathlib.Path, mtime: datetime.datetime):
    s_mtime = mtime.isoformat()
    logger.important("%s -> %s %s", path, s_mtime, mtime)

    audio_file = eyed3.core.load(path)
    if audio_file.tag is None:
        audio_file.initTag(version=(2, 4, 0))
    else:
        audio_file.tag.version = eyed3.id3.ID3_V2_4

    audio_file.tag.user_text_frames.set(s_mtime, description=u"original_mtime")

    # eyeD3 after commit c9246fff91a74001ac278295003cc2cc3b8946f4 does not output seconds from a eyed3.core.Date
    # stick to version 0.9.7 for right now
    eyed3_date = eyed3.core.Date.parse(s_mtime[:19])
    logger.info('%s -> eyed3 %s', s_mtime, eyed3_date)
    audio_file.tag.encoding_date = eyed3_date
    # this is what we tried to do to force it
    #eyed3_date_val = FixedEyeD3CoreDate(year=mtime.year, month=mtime.month, day=mtime.day, hour=mtime.hour, minute=mtime.minute, second=mtime.second)
    #setDateFrame(audio_file.tag, b'TDEN', eyed3_date_val)

    # audio_file.tag.frame_set[b"TDEN"][0].date = s_mtime
    audio_file.tag.save()


def main(argv):
    import argparse
    import json
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('file')
    arg_parser.add_argument('--recursive', action='store_true')
    arg_parser.add_argument('--verbose', action='store_true')
    args = arg_parser.parse_args(argv)

    logging.info('called with %s', args)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    path = pathlib.Path(args.file)
    logging.info("looking at %s", path)
    if not path.exists:
        raise FileNotFoundError(path)
    if path.is_dir():
        logging.debug("%s is a directory", path)
        x = MP3InfoExtractor(path)
        rv = []
        if args.recursive:
            for dirpath, dirname, filenames in path.walk():
                for f1 in filenames:
                    p1 = dirpath / f1
                    j = x.get_information(p1)
                    if j is not None:
                        rv.append(j)
        else:
            for p1 in path.iterdir():
                logging.debug("looking at %s", p1)
                if p1.is_file():
                    j = x.get_information(p1)
                    if j is not None:
                        rv.append(j)
    else:
        logging.debug("%s is a file", path)
        x = MP3InfoExtractor()
        rv = x.get_information(path)
    print(json.dumps(rv, indent=1, sort_keys=True, default=str))


if __name__ == '__main__':
    import logging
    import sys
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
