import os
from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parent.parent

# The imperial-assault-data checkout the tools read from and import into.
DATA_ROOT = Path(os.environ.get('IA_DATA_ROOT', TOOLS_ROOT.parent / 'imperial-assault-data')).resolve()

# Downloads and work in progress, one folder per product (git-ignored).
STAGING = Path(os.environ.get('IA_STAGING', TOOLS_ROOT / 'staging')).resolve()

# SHA-512s of every boardwars original handled so far: the 2017–18 batches, plus whatever ia import adds.
SEEN_HASHES = TOOLS_ROOT / 'crawler' / 'original-images-sha512.txt'
# Originals deliberately not kept (rule sheets, duplicate backs, ...), so audits stop flagging them.
SKIPPED_HASHES = TOOLS_ROOT / 'known-skipped-sha512.txt'

# Cards from the 2018 dataset that new cards are aligned to (ia_tools/align.py).
TEMPLATES = TOOLS_ROOT / 'assets' / 'templates'

# TinyPNG only on request (IA_TINYPNG=1, with TINIFY_KEY): images are quantised locally by default (2026-11-10: the
# maintainer dropped TinyPNG; its files came out about twice the size of the local encoding's).
TINIFY_KEY = os.environ.get('TINIFY_KEY') if os.environ.get('IA_TINYPNG') == '1' else None
PORT = int(os.environ.get('IA_PORT', '8001'))
