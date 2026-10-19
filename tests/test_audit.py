import json
from types import SimpleNamespace

from ia_tools import audit, boardwars


def test_run_reuses_the_hash_cache(tmp_path, real_dataset):
    url = 'https://cards.boardwars.eu/albums/Core-Box/Command%20Cards/Known.jpg'
    (tmp_path / 'hashes.jsonl').write_text(json.dumps({'url': url, 'sha512': 'ab', 'bytes': 1}) + '\n')
    page = '''<div id="gallerytitle"><h2><span><a class="galleryindexurl" href="/">DB</a> |
        <a href="/Core-Box/" title="Core Box">Core Box</a> | </span> Command Cards</h2></div>
        <div class="image"><img alt="Known" src="/cache/Core-Box/Command%20Cards/Known_275_thumb_ffflogog_whatermark_cc.jpg"></div>'''
    client = SimpleNamespace(get=lambda _: SimpleNamespace(text=page))  # an image download would fail on .content
    report = audit.run(client, real_dataset, tmp_path, start_url=f'{boardwars.BASE_URL}Core-Box/Command%20Cards/',
                       log=lambda *a, **k: None)
    assert [(e['url'], e['sha512']) for e in report['entries']] == [(url, 'ab')]
