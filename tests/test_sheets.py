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
