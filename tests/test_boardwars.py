from types import SimpleNamespace

import pytest

from ia_tools import boardwars
from tests.conftest import fixture_html

BASE = 'https://cards.boardwars.eu'


def test_original_url_drops_cache_thumbnail_suffix_and_query():
    thumb = '/cache/Core-Box/Command%20Cards/Burst%20Fire_275_thumb_ffflogog_whatermark_cc.jpg?cached=1465239978'
    assert boardwars.original_url(thumb) == f'{BASE}/albums/Core-Box/Command%20Cards/Burst%20Fire.jpg'


def test_original_url_rejects_non_thumbnails():
    with pytest.raises(ValueError):
        boardwars.original_url('/zp-core/images/rss.png')


def test_product_album_page():
    page = boardwars.parse_album_page(fixture_html('product-album.html'), f'{BASE}/Expansion-Boxes/Tyrants-of-Lothal/')
    assert page.path == ('Expansion Boxes', 'Tyrants of Lothal')
    assert ('Command Cards' in [name for _, name in page.albums]) and len(page.albums) == 9
    assert page.albums[0][0].startswith(f'{BASE}/Expansion-Boxes/Tyrants-of-Lothal/')
    assert [i.name for i in page.images] == ['Tyrants of Lothal']
    assert page.next_page is None


def test_card_album_page():
    url = f'{BASE}/Expansion-Boxes/Tyrants-of-Lothal/Command%20Cards/'
    page = boardwars.parse_album_page(fixture_html('command-cards-album.html'), url)
    assert page.path == ('Expansion Boxes', 'Tyrants of Lothal', 'Command Cards')
    assert page.albums == []
    assert page.images[0].name == 'Marked Territory'
    assert page.images[0].url == f'{BASE}/albums/Expansion-Boxes/Tyrants-of-Lothal/Command%20Cards/Marked%20Territory.jpg'


def test_paginated_album_page():
    page = boardwars.parse_album_page(fixture_html('paginated-album.html'), f'{BASE}/Skirmish-Maps/')
    assert page.path == ('Skirmish Maps',)
    assert page.next_page == f'{BASE}/Skirmish-Maps/page/2/'
    assert page.images


def test_crawl_follows_albums_and_pages_once():
    pages = {
        f'{BASE}/a/': '''<div id="gallerytitle"><h2><span><a class="galleryindexurl" href="/">DB</a> | </span> A</h2></div>
            <div class="album"><h3><a href="/a/b/">B</a></h3></div>
            <div class="album"><h3><a href="/a/b/">B again</a></h3></div>
            <ul class="pagelist"><li class="next"><a href="/a/page/2/">next</a></li></ul>''',
        f'{BASE}/a/page/2/': '''<div id="gallerytitle"><h2><span><a class="galleryindexurl" href="/">DB</a> | </span> A</h2></div>
            <div class="image"><img alt="Two" src="/cache/a/Two_275_thumb_ffflogog_whatermark_cc.png"></div>''',
        f'{BASE}/a/b/': '''<div id="gallerytitle"><h2><span><a class="galleryindexurl" href="/">DB</a> |
            <a href="/a/" title="A">A</a> | </span> B</h2></div>
            <div class="image"><img alt="One" src="/cache/a/b/One_275_thumb_ffflogog_whatermark_cc.jpg"></div>''',
    }
    fetched = []

    class FakeClient:
        def get(self, url):
            fetched.append(url)
            return SimpleNamespace(text=pages[url])

    images = list(boardwars.crawl(FakeClient(), f'{BASE}/a/'))
    assert sorted((i.path, i.name) for i in images) == [(('A',), 'Two'), (('A', 'B'), 'One')]
    assert len(fetched) == len(set(fetched)) == 3
