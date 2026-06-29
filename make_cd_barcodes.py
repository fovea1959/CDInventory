import argparse
import logging
import sys

from io import BytesIO

from barcode import Code128
from barcode.writer import ImageWriter

from fpdf import FPDF

class G:
    def __init__(self, rows=4, cols=3):
        self.rows = rows
        self.cols = cols
        self.height = 2.5
        self.width = 2.5
        self.duplex = True


def make_code128_barcode(label):
    barcode = BytesIO()
    Code128(label, writer=ImageWriter()).write(barcode)
    return barcode


def chunks_of_n(things, n):
    return [things[i:i + n] for i in range(0, len(things), n)]


def make_page(g, pdf, rows_of_images):
    pdf.add_page()
    with pdf.table(v_align='MIDDLE', min_row_height=g.height, col_widths=g.width, first_row_as_headings=False) as table:
        for row_of_images in rows_of_images:
            row = table.row()
            for cell_image in row_of_images:
                if cell_image is None:
                    row.cell('')
                else:
                    row.cell(img=cell_image)


def make_pages(g, pdf, page_of_images):
    if len(page_of_images) != g.rows * g.cols:
        raise ValueError(f"can only do {g.rows * g.cols} images per page")
    rows_of_images = chunks_of_n(page_of_images, g.cols)
    make_page(g, pdf, rows_of_images)

    if g.duplex:
        for row_of_images in rows_of_images:
            row_of_images.reverse()
        make_page(g, pdf, rows_of_images)


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--end', type=int, required=True)
    args = parser.parse_args(argv)

    logging.info('called with %s', args)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    g = G()

    images = []
    for cd_number in range(args.start, args.end+1):
        label = f'DW_CD:{cd_number:06}'
        images.append(make_code128_barcode(label))
    # pad the list
    images = images + [None] * (-len(images) % (g.rows * g.cols))

    pdf = FPDF(orientation="P", unit="in", format="letter")
    pdf.set_auto_page_break(auto=False)
    pdf.set_left_margin(0.5)
    pdf.set_top_margin(0.5)
    pdf.set_font("Helvetica", "", 10)

    pages_of_images = chunks_of_n(images, g.rows * g.cols)

    for page_of_images in pages_of_images:
        make_pages(g, pdf, page_of_images)

    pdf.output("cd_barcodes.pdf")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
