import re
from pathlib import Path

from PIL import Image

from ia_tools import sheets

SOURCES = [{'name': 'Han Solo'}, {'name': 'General Weiss'}, {'name': 'Twin Shadows'}, {'name': "Jabba's Realm"}]


def scans(root, folder, *names):
    (root / folder).mkdir(parents=True)
    for n, name in enumerate(names):
        Image.new('RGB', (30, 39), (n * 100, 0, 0)).save(root / folder / name)


def test_pages_follow_their_numbers():
    names = ['Scan.png', 'Scan (2).png', 'Scan-1.png', 'Scan (12).png', 'Scan(3).png']
    assert [sheets.page_number(Path(name)) for name in names] == [0, 2, 1, 12, 3]


def test_folders_name_their_products(tmp_path):
    scans(tmp_path, 'han solo', 'Scan (2).png', 'Scan.png')
    scans(tmp_path, 'Weiss', 'Scan (6).png', 'Scan (5).png')
    scans(tmp_path, "jabba's realm skirmish", 'Scan (2).png', 'Scan.png')
    made, problems = sheets.plan(tmp_path, SOURCES)
    assert problems == []
    assert [(s['name'], s['file'], s['pages']) for s in made] == [
        ('General Weiss Rules Sheet', 'general-weiss-rules-sheet.pdf', ['Scan (5).png', 'Scan (6).png']),
        ('Han Solo Rules Sheet', 'han-solo-rules-sheet.pdf', ['Scan.png', 'Scan (2).png']),
        ("Jabba's Realm Skirmish Rules Sheet", 'jabbas-realm-skirmish-rules-sheet.pdf', ['Scan.png', 'Scan (2).png']),
    ]


def test_problems_stop_the_run(tmp_path):
    scans(tmp_path, 'nobody', 'Scan.png', 'Scan (2).png')
    scans(tmp_path, 'han solo', 'Scan.png')
    made, problems = sheets.run(tmp_path, SOURCES, out=tmp_path / 'out')
    assert len(problems) == 2 and not (tmp_path / 'out').exists()


def test_run_writes_two_page_pdfs_and_a_manifest(tmp_path):
    scans(tmp_path / 'scans', 'han solo', 'Scan (2).png', 'Scan.png')
    made, problems = sheets.run(tmp_path / 'scans', SOURCES, out=tmp_path / 'out', log=lambda *_: None)
    pdf = (tmp_path / 'out' / 'han-solo-rules-sheet.pdf').read_bytes()
    assert problems == [] and pdf.startswith(b'%PDF') and len(re.findall(rb'/Type\s*/Page\b(?!s)', pdf)) == 2
    assert (tmp_path / 'out' / 'manifest.json').exists() and made[0]['bytes'] == len(pdf)


def strips_pdf(path, pages):
    """A PDF drawn like Microsoft Print to PDF's: each page 1 inch square, flipped (y down), and drawn in horizontal
    strips, one solid JPEG each (72 x 36 px, so 72 DPI)."""
    import io

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject, StreamObject

    writer = PdfWriter()
    for colors in pages:
        page = writer.add_blank_page(72, 72)
        xobjects, content = DictionaryObject(), ['1 0 0 -1 0 72 cm']
        for i, color in enumerate(colors):
            jpeg = io.BytesIO()
            Image.new('RGB', (72, 36), color).save(jpeg, 'JPEG', quality=95)
            image = StreamObject()
            image._data = jpeg.getvalue()
            image.update({NameObject(k): v for k, v in {
                '/Type': NameObject('/XObject'), '/Subtype': NameObject('/Image'), '/Width': NumberObject(72),
                '/Height': NumberObject(36), '/ColorSpace': NameObject('/DeviceRGB'),
                '/BitsPerComponent': NumberObject(8), '/Filter': NameObject('/DCTDecode')}.items()})
            xobjects[NameObject(f'/Im{i}')] = writer._add_object(image)
            content.append(f'q 72 0 0 -36 0 {36 * (i + 1)} cm /Im{i} Do Q')
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/XObject'): xobjects})
        stream = DecodedStreamObject()
        stream.set_data(' '.join(content).encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    with open(path, 'wb') as file:
        writer.write(file)


def test_a_folder_can_hold_a_two_page_pdf(tmp_path):
    (tmp_path / 'han solo').mkdir()
    strips_pdf(tmp_path / 'han solo' / 'Han.pdf', [['red'], ['blue']])
    (tmp_path / 'Weiss').mkdir()
    strips_pdf(tmp_path / 'Weiss' / 'Weiss.pdf', [['red']])
    scans(tmp_path, 'twin shadows skirmish', 'Scan.png', 'Scan (2).png')
    strips_pdf(tmp_path / 'twin shadows skirmish' / 'Extra.pdf', [['red'], ['blue']])
    made, problems = sheets.plan(tmp_path, SOURCES)
    assert [(s['file'], s['pages']) for s in made] == [('han-solo-rules-sheet.pdf', ['Han.pdf#1', 'Han.pdf#2'])]
    assert problems == ['Weiss: a sheet is one PDF of 2 pages, with no scans beside it',
                        'twin shadows skirmish: a sheet is one PDF of 2 pages, with no scans beside it']


def test_pdf_pages_are_rebuilt_from_their_strips(tmp_path):
    strips_pdf(tmp_path / 'sheet.pdf', [[(220, 20, 20), (20, 20, 220)]])
    image, dpi = sheets.pdf_page(tmp_path / 'sheet.pdf', 1)
    assert image.size == (72, 72) and dpi == 72
    top, bottom = image.getpixel((36, 10)), image.getpixel((36, 60))
    assert top[0] > 180 > top[2] and bottom[2] > 180 > bottom[0]  # the first strip on top, upright
    assert image.getpixel((36, 35))[0] > 180 and image.getpixel((36, 36))[2] > 180  # no seam between them
