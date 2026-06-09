import uuid

import qrcode


qr = qrcode.QRCode(
    version=None,
    error_correction=qrcode.constants.ERROR_CORRECT_L,
    box_size=10,
    border=4,
)
qr.add_data(str(uuid.uuid4()) + ',Office Left #1')
qr.make(fit=True)

img = qr.make_image(fill_color="black", back_color="white")
img.save("_test_make_qrcode.png")
