"""Create an image-only PDF fixture for Phase 1's explicit OCR rejection."""

from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def main():
    path = Path(__file__).resolve().parents[1] / "examples" / "scanned_sample.pdf"
    image = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 70), "FICTIONAL IMAGE-ONLY DOCUMENT", fill="black", font_size=32)
    draw.text(
        (40, 150),
        "This text is rasterized. Phase 1 requires OCR to read it.",
        fill="black",
        font_size=24,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=(600, 400), invariant=True)
    pdf.drawImage(ImageReader(image), 0, 100, width=600, height=200)
    pdf.showPage()
    pdf.save()
    print(path)


if __name__ == "__main__":
    main()
