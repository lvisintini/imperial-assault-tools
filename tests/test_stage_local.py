import io
import json
import zipfile

import pytest

from ia_tools import stage_local
from tests.conftest import png_bytes


def tts_zip(path, decks):
    """A TTS saved object: one card per (face url, back url), with each image cached under Mods/Images."""
    cards = [{'Name': 'CardCustom', 'CardID': n * 100, 'Nickname': '',
              'CustomDeck': {str(n): {'FaceURL': face, 'BackURL': back, 'NumWidth': 1, 'NumHeight': 1}}}
             for n, (face, back) in enumerate(decks)]
    save = {'ObjectStates': [{'Name': 'Deck', 'ContainedObjects': cards}]}
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('Cards.json', json.dumps(save))
        for n, url in enumerate(sorted({u for pair in decks for u in pair})):
            archive.writestr('Mods/Images/' + ''.join(c for c in url if c.isalnum()) + '.png',
                             png_bytes((60, 90), color=(n, 0, 0, 255)))
    return path


def test_tts_cards_are_faces_then_distinct_backs(tmp_path):
    save = tts_zip(tmp_path / 'save.zip', [('http://x/f1/', 'http://x/b1/'), ('http://x/f2/', 'http://x/b1/'),
                                           ('http://x/f3/', 'http://x/b2/')])
    cards = stage_local.tts_cards(save)
    assert [(name, back) for name, _, _, back in cards] == [
        ('Card 1', False), ('Card 2', False), ('Card 3', False),
        ('Back A, of cards 1 and 2', True), ('Back B, of card 3', True)]


def test_stage_writes_a_manifest_ia_enter_reads(tmp_path, real_dataset):
    save = tts_zip(tmp_path / 'save.zip', [('http://x/f1/', 'http://x/b1/')])
    staging, manifest = stage_local.run(real_dataset, 'test', 'command-cards', tts=save, root=tmp_path / 'staging',
                                        log=lambda *_: None)
    face, back = manifest['items']
    assert face['guess'] == {'content_type': 'command-cards', 'back_content_type': None, 'hints': {}}
    assert back['guess'] == {'content_type': 'card-backs', 'back_content_type': 'command-cards', 'hints': {}}
    assert (staging.dir / face['file']).read_bytes()[:4] == b'\x89PNG'
    assert json.loads(staging.manifest_path.read_text())['items'][0]['width'] == 60


def test_stage_refuses_unknown_products(tmp_path, real_dataset):
    save = tts_zip(tmp_path / 'save.zip', [('http://x/f1/', 'http://x/b1/')])
    with pytest.raises(ValueError, match='not one existing source'):
        stage_local.run(real_dataset, 'test', 'command-cards', tts=save, product='No Such Product',
                        root=tmp_path / 'staging', log=lambda *_: None)
