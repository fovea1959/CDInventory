from fpdf import FPDF, XPos, YPos


class CustomPDF(FPDF):
    def header(self):
        """Creates a reusable header on every page."""
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 10, "My Document Title", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        self.ln(10) # Line break

    def footer(self):
        """Creates a reusable footer with page numbers."""
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", border=0, align="C")


# 1. Initialize the PDF document (Portrait mode, Millimeters, letter size)
pdf = CustomPDF(orientation="P", unit="mm", format="letter")
pdf.set_auto_page_break(auto=True, margin=15)
pdf.add_page()

# 2. Add structured text
pdf.set_font("Helvetica", "B", 12)
pdf.cell(0, 10, "Section 1: Introduction", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

pdf.set_font("Helvetica", "", 10)
intro_text = (
    "This is a sample PDF document generated using Python and the fpdf2 library. "
    "It demonstrates how easily you can arrange textual information alongside "
    "visual graphics to create professional dynamic reports or automated invoices."
)
pdf.multi_cell(0, 6, intro_text)
pdf.ln(5)

# 3. Add an image
# Parameters: (file_path, x_coordinate, y_coordinate, width)
# Leaving y out or setting x/y positions dynamically prevents overlapping.
image_path = "_test_make_qrcode.png"  # Replace with your actual file path
pdf.image(image_path, x=10, y=pdf.get_y(), w=100)
pdf.ln(10)

# 4. Save the completed PDF file
pdf.output("_test_fpdf2.pdf")
print("PDF successfully created!")
