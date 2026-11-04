"""Create deterministic fictional test data. No real enterprise claims or benchmark results."""

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUTPUT = Path(__file__).resolve().parents[1] / "examples" / "procurement_sample.pdf"


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(OUTPUT), pagesize=A4, invariant=True)
    pages = [
        (
            "Supplier delivery policy",
            [
                "Orion Supplies has a standard delivery window of 14 calendar days.",
                "The delivery window starts when the purchase order is approved.",
                "Express delivery requires written approval from the purchasing manager.",
                "The supplier contact team records the purchase order identifier.",
            ],
        ),
        (
            "Acceptance and review",
            [
                "The acceptance review must be completed within 5 business days.",
                "The operations team checks delivered quantities against the purchase order.",
                "Damaged items must be recorded in the acceptance report.",
                "The report does not specify a policy for international shipping.",
            ],
        ),
    ]
    for number, (title, lines) in enumerate(pages, 1):
        pdf.setFillColor(HexColor("#113a34"))
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(50, 785, "OMNIRAG AI / FICTIONAL RESEARCH FIXTURE")
        pdf.setFont("Helvetica-Bold", 22)
        pdf.drawString(50, 735, title)
        pdf.setFillColor(HexColor("#344653"))
        pdf.setFont("Helvetica", 11)
        y = 680
        for line in lines:
            pdf.drawString(50, y, line)
            y -= 32
        pdf.setFont("Helvetica", 9)
        pdf.drawString(50, 80, "Authored sample data. Not an actual company policy.")
        pdf.drawString(50, 60, f"Page {number}")
        pdf.showPage()
    pdf.save()
    print(OUTPUT)


if __name__ == "__main__":
    main()
