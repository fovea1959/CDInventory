from fpdf import FPDF

pdf = FPDF()
pdf.add_page()
pdf.set_font("helvetica", size=12)

# Define your data and image paths
data = [
    ("Item Name", "Visual Preview"),
    ("Logo", "_test_make_qrcode.png"),  # Path to your local image
]

# Create the table
with pdf.table() as table:
    for row_idx, row_data in enumerate(data):
        row = table.row()

        # Insert text in the first column
        row.cell(row_data[0])

        # Insert text for the header row, or an image for the data rows
        if row_idx == 0:
            row.cell(row_data[1])
        else:
            # Inject image directly into the cell
            row.cell(img=row_data[1], img_fill_width=True)

pdf.output("_test_fpdf_image_table.pdf")
