import io
import json

import pytest
from PIL import Image

from ia_tools import mats, settings

PAGE = 'https://www.fantasyflightgames.com/en/products/fantasy-flight-supply/products/anchorhead-cantina-skirmish-map/'
IMAGE = 'https://web.archive.org/web/20200104011458im_/http://images-cdn.fantasyflightgames.com/x/swi45_main.png'


@pytest.fixture
def staging(dataset_copy, tmp_path, monkeypatch):
    if not dataset_copy.path('maps').exists():
        pytest.skip('The checkout has no maps collection (data 2.0.0)')
    monkeypatch.setattr(settings, 'STAGING', tmp_path / 'staging')
    monkeypatch.setattr(settings, 'TINIFY_KEY', None)
    pages = tmp_path / 'staging' / 'wiki' / 'pages'
    pages.mkdir(parents=True)
    dates = {'wave': 'Wave 9', 'announced': 'January 13th, 2017', 'released': 'May 11th, 2017'}
    products = [{'code': 'SWI45', 'title': 'Anchorhead Cantina Skirmish Map'} | dates,
                {'code': 'SWI46', 'title': 'Some Ally Pack'} | dates]
    (pages.parent / 'products.json').write_text(json.dumps({'products': products}), encoding='utf-8')
    wikitext = ('{{Expansion|name=Anchorhead Cantina|type=Skirmish Map|release_date=2 Feb 2017|sku=SWI45|'
                f'link=[{PAGE} Product Page]}}}}')
    (pages / 'anchorhead-cantina-skirmish-map.json').write_text(json.dumps({'parse': {'wikitext': wikitext}}))
    (pages / 'some-ally-pack.json').write_text(json.dumps({'parse': {'wikitext': '{{Expansion|type=Ally Pack}}'}}))
    return dataset_copy


class Client:
    def __init__(self):
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        response = type('Response', (), {'url': 'https://web.archive.org/web/20200104011458/' + PAGE})()
        if url.startswith(mats.WAYBACK):
            response.text = f'<meta property="og:image" content="{IMAGE}"/>'
        else:
            buffer = io.BytesIO()
            Image.new('RGB', (300, 300), 'red').save(buffer, 'PNG')
            response.content = buffer.getvalue()
        return response


def test_mats_come_from_the_wiki_cache(staging):
    found, problems = mats.mats(staging)
    assert problems == []
    assert len(found) == 1
    mat = found[0]
    # The main page's dates, not the mat page's own release date.
    assert {k: mat[k] for k in ('product_code', 'name', 'wave', 'announced_date', 'release_date', 'map')} == \
        {'product_code': 'SWI45', 'name': 'Anchorhead Cantina', 'wave': 9, 'announced_date': '2017-01-13',
         'release_date': '2017-05-11', 'map': 'Anchorhead Bar'}
    assert mat['map_id'] == next(m['id'] for m in staging.records('maps') if m['name'] == 'Anchorhead Bar')


def test_run_stages_images_and_a_manifest_and_fetches_once(staging):
    client = Client()
    manifest, problems = mats.run(client, staging, log=lambda *_: None)
    assert problems == [] and len(client.urls) == 2
    mat = manifest['mats'][0]
    assert mat['image'] == 'sources/anchorhead-cantina.png' and mat['original'] == 'SWI45.png'
    for size in ('large', 'small'):
        with Image.open(mats.out_dir() / size / mat['image']) as image:
            assert image.size == (300, 300)
    assert json.loads((mats.out_dir() / 'manifest.json').read_text(encoding='utf-8')) == manifest

    staged = (mats.out_dir() / 'large' / mat['image']).stat().st_mtime_ns
    mats.run(client, staging, log=lambda *_: None)
    assert len(client.urls) == 2  # the original is cached
    assert (mats.out_dir() / 'large' / mat['image']).stat().st_mtime_ns == staged  # and so are the staged images
