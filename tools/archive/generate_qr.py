import qrcode
from PIL import Image

url = "https://www.thefourthsheet.com.au/contact.html"

# Create QR code object
qr = qrcode.QRCode(
    version=4,              # size of the QR (1–40); increase if needed
    error_correction=qrcode.constants.ERROR_CORRECT_H,  # high error correction for print
    box_size=10,            # pixel size of each box
    border=4                # border boxes around the code
)

qr.add_data(url)
qr.make(fit=True)

# Generate image (black on white)
img = qr.make_image(fill_color="black", back_color="white")

# Save as high‑quality PNG
img.save("thefourthsheet_contact_qr.png")
