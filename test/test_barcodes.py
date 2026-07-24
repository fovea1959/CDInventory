import argparse
import logging
import sys

from io import BytesIO

from barcode import Code128
from barcode.writer import ImageWriter

from fpdf import FPDF


def make_barcode(i):
    label = f'DEW_CD:{i:05}'

    barcode = BytesIO()
    Code128(label, writer=ImageWriter()).write(barcode)
    return barcode


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args(argv)

    logging.info('called with %s', args)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 1. Initialize the PDF document (Portrait mode, Millimeters, letter size)
    pdf = FPDF(orientation="P", unit="mm", format="letter")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "", 10)

    with pdf.table(first_row_as_headings=False, borders_layout="HORIZONTAL_LINES") as table:
        cd_number = 1
        while cd_number < 100:
            row = table.row(min_height=35)

            row.cell(img=make_barcode(cd_number))
            cd_number += 1
            row.cell(img=make_barcode(cd_number))
            cd_number += 1
            row.cell(img=make_barcode(cd_number))
            cd_number += 1
            row.cell(img=make_barcode(cd_number))
            cd_number += 1

    pdf.output("cd_barcodes.pdf")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
