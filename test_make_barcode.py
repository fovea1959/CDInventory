import uuid

import barcode
from barcode.writer import ImageWriter

# Or to an actual file:
with open("_test_barcode.png", "wb") as f:
    s = str("Abcd")
    barcode.Code128(s, ImageWriter(format='PNG')).write(f, dict(font_size=10))