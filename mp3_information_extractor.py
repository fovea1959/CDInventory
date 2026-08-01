import base64
import dataclasses
import datetime
import pathlib

import eyed3
import eyed3.id3


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

    def get_information(self, path, last_mtime: datetime.datetime = None):
        mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime)
        if last_mtime is None or mtime > last_mtime:
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
            try:
                rv = rv.decode()
            except:
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
            return dict(owner_id = frame.owner_id.decode(), owner_data = self.ascii_ize(frame.owner_data))
        else:
            return str(type(frame)) + " " + str(frame.render())

    @staticmethod
    def ascii_ize(v):
        return base64.urlsafe_b64encode(v).decode('utf-8').replace('=', '')


def main(argv):
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument('file')
    parser.add_argument('--recursive', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

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
