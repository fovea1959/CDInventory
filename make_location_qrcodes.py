import argparse
import json
import logging
import pathlib
import random
import sys
import uuid

import qrcode

from fpdf import FPDF, XPos, YPos

from dateutil import parser
from sqlalchemy import select

import CDInventoryDao
import utils
from CDInventoryEntities import MP3, Location
from utils import extract_data, extract_datum


class CustomPDF(FPDF):
    def header(self):
        pass

    def footer(self):
        pass

    def _xxx_header(self):
        """Creates a reusable header on every page."""
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, "My Document Title", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        self.ln(10) # Line break

    def _xxx_footer(self):
        """Creates a reusable footer with page numbers."""
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", border=0, align="C")


class RepeatableUuid4:
    def __init__(self, seed = None):
        # Initialize a local Random instance to avoid altering global state
        self.rng = random.Random(seed)

    def next(self):
        # Generate a 128-bit random integer
        random_bits = self.rng.getrandbits(128)

        # Construct a UUID4 using the integer
        return uuid.UUID(int=random_bits, version=4)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('inputs', nargs='+')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

    logging.info('called with %s', args)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    all_of_them = []

    with CDInventoryDao.DAO(echo=True) as dao:
        stmt = select(Location)
        results = dao.session.scalars(stmt).all()
        for result in results:
            print(result)

    for filename in args.inputs:
        with open(filename, 'r') as f:
            descriptions = [l.strip() for l in f]

        print(descriptions)

        uuid4 = RepeatableUuid4()   # seed 42 will have start with bdd640fb-0667-4ad1-9c80-317fa3b1799d

        # 1. Initialize the PDF document (Portrait mode, Millimeters, letter size)
        pdf = CustomPDF(orientation="P", unit="mm", format="letter")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)

        with pdf.table(first_row_as_headings=False, col_widths=(1, 3, 3), borders_layout="HORIZONTAL_LINES") as table:
            for description in descriptions:
                description = description.strip()
                if description.startswith('#'):
                    continue

                if description.startswith('!'):
                    description = description[1:].strip()
                    seed = int(description)
                    uuid4 = RepeatableUuid4(seed=seed)
                    continue

                row = table.row(min_height=35)

                if description.startswith('--'):
                    row.cell("--")
                    row.cell('')
                    row.cell('')
                else:
                    qr = qrcode.QRCode(
                        version=None,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10,
                        border=4,
                    )
                    id = str(uuid4.next())
                    logging.info("%s %s", id, description)

                    all_of_them.append((id, description))

                    qr_data = {
                        'type': 'location',
                        'id': id,
                        'description': description
                    }
                    qr.add_data(json.dumps(qr_data))

                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")

                    row.cell(img=img.get_image())
                    row.cell(id)
                    row.cell(description)

        output_filename = pathlib.Path(filename).with_suffix(".pdf")
        pdf.output(output_filename)
        logging.info("%s successfully created!", output_filename)



    with CDInventoryDao.DAO(echo=args.verbose) as dao:
        for id, description in all_of_them:
            # print(id, description)
            location = dao.get_location(id)
            if location is None:
                location = Location()
                location.location_id = id
                dao.session.add(location)
            location.location_description = description
        dao.session.commit()

        stmt = select(Location)

        # 2. Execute and fetch all entities as a Python list
        results = dao.session.scalars(stmt).all()
        for result in results:
            print(result)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
