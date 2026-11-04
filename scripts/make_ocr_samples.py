"""Generate fictional scan/mixed-page fixtures without a hidden text layer."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def main():
    output = Path(__file__).resolve().parents[1] / "examples"
    image = Image.new("RGB", (1400, 1800), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=38)
    for index, text in enumerate(
        [
            "FICTIONAL SCANNED POLICY - OCR TEST",
            "Cedar Archives retention policy",
            "Signed records must be retained for 7 years.",
            "The records custodian reviews access every 90 days.",
            "This sample contains no real company information.",
        ]
    ):
        draw.text((90, 160 + index * 100), text, fill="black", font=font)
    for mixed in (False, True):
        path = output / ("mixed_policy.pdf" if mixed else "scanned_policy.pdf")
        pdf = canvas.Canvas(str(path), pagesize=(560, 720), invariant=True)
        if mixed:
            pdf.setFont("Helvetica", 14)
            pdf.drawString(40, 650, "FICTIONAL POLICY - NATIVE TEXT PAGE")
            pdf.drawString(40, 610, "Cedar Archives delivers records within 3 working days.")
            pdf.showPage()
        pdf.drawImage(ImageReader(image), 0, 0, width=560, height=720)
        pdf.showPage()
        pdf.save()
        print(path)


if __name__ == "__main__":
    main()
