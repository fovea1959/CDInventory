import argparse
import logging
import pathlib
import random
import sys
import uuid

import qrcode

from fpdf import FPDF, XPos, YPos


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
    parser.add_argument('input')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

    logging.info('called with %s', args)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    with open(args.input, 'r') as f:
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
                uuid4 = RepeatableUuid4(seed=42)
                continue

            row = table.row(min_height=35)

            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            id = str(uuid4.next())
            qr.add_data(id + ',' + description)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            row.cell(img=img.get_image())
            row.cell(id)
            row.cell(description)

    output_filename = pathlib.Path(args.input).with_suffix(".pdf")
    pdf.output(output_filename)
    logging.info("%s successfully created!", output_filename)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
