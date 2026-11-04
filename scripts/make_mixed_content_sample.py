"""Render the authored Willow native-header/scanned-body PDF for manual testing."""

from evaluate_quality import ROOT, make_pdf, read_fixture


def main():
    fixture = read_fixture(ROOT / "evaluation/mixed_ocr_fixture.json")
    path = ROOT / "examples/mixed_content_policy.pdf"
    path.write_bytes(make_pdf(fixture["documents"][0]))
    print(path)


if __name__ == "__main__":
    main()
