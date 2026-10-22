"""The data-entry app's HTTP server (standard library only). Serves the page, the staged originals, previews of the
processed images, existing dataset images for comparison, and a small JSON API that reads and writes entries.json."""
import io
import json
import mimetypes
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from ia_tools import edits, images, importer
from ia_tools.dataset import Dataset
from ia_tools.enter import api
from ia_tools.staging import Staging

STATIC = Path(__file__).parent / 'static'
lock = threading.Lock()


def safe_join(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise PermissionError(relative)
    return path


class Handler(BaseHTTPRequestHandler):
    dataset: Dataset = None  # set by serve()

    def log_message(self, format, *args):
        pass

    # Responses

    def send_json(self, value, status=HTTPStatus.OK):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, content_type=None):
        if not path.is_file():
            return self.send_error(HTTPStatus.NOT_FOUND)
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', content_type or mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_png(self, image):
        buffer = io.BytesIO()
        image.save(buffer, 'PNG')
        body = buffer.getvalue()
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', 'image/png')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(length) or b'null')

    # Routing

    def do_GET(self):
        url = urlsplit(self.path)
        parts = [unquote(p) for p in url.path.strip('/').split('/') if p]
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            match parts:
                case []:
                    return self.send_file(STATIC / 'index.html')
                case ['static', *rest]:
                    return self.send_file(safe_join(STATIC, '/'.join(rest)))
                case ['api', 'products']:
                    return self.send_json([self.product_summary(s) for s in Staging.all()])
                case ['api', 'products', slug]:
                    return self.send_json(self.product(Staging(slug)))
                case ['originals', slug, *rest]:
                    staging = Staging(slug)
                    return self.send_file(safe_join(staging.dir, '/'.join(rest)))
                case ['preview', slug, key]:
                    return self.preview(Staging(slug), key, query)
                case ['data-images', size, *rest] if size in ('large', 'small'):
                    return self.send_file(safe_join(self.dataset.root / 'images' / size, '/'.join(rest)))
            self.send_error(HTTPStatus.NOT_FOUND)
        except PermissionError:
            self.send_error(HTTPStatus.FORBIDDEN)

    def do_PUT(self):
        parts = [unquote(p) for p in urlsplit(self.path).path.strip('/').split('/') if p]
        body = self.read_json()
        match parts:
            case ['api', 'products', slug, 'product']:
                return self.update(Staging(slug), lambda e: e.__setitem__('product', body), body)
            case ['api', 'products', slug, 'items', key]:
                return self.update(Staging(slug), lambda e: e['items'].__setitem__(key, body), body)
            case ['api', 'products', slug, 'extra', key]:
                return self.update(Staging(slug), lambda e: e.setdefault('extra', {}).__setitem__(key, body), body)
            case ['api', 'products', slug, 'edits', key]:
                staging = Staging(slug)
                with lock:
                    entries = staging.entries()
                    entries.setdefault('edits', {})[key] = body
                    staging.save_entries(entries)
                return self.send_json({'saved': True} | self.edit_preview(staging, key, body))
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_DELETE(self):
        parts = [unquote(p) for p in urlsplit(self.path).path.strip('/').split('/') if p]
        match parts:
            case ['api', 'products', slug, 'extra', key]:
                return self.update(Staging(slug), lambda e: e.setdefault('extra', {}).pop(key, None), None)
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parts = [unquote(p) for p in urlsplit(self.path).path.strip('/').split('/') if p]
        match parts:
            case ['api', 'products', slug, 'edits', key, 'preview']:
                return self.send_json(self.edit_preview(Staging(slug), key, self.read_json()))
            case ['api', 'products', slug, 'check']:
                try:
                    plan = importer.plan(Staging(slug), self.dataset)
                except importer.ImportProblems as problems:
                    return self.send_json({'ok': False, 'problems': problems.problems})
                return self.send_json({'ok': True, 'summary': importer.summary(plan),
                                       'records': [{'key': p.key, 'content_type': p.content_type, 'record': p.record}
                                                   for p in plan['pending']]
                                       + [{'key': p['key'], 'content_type': p['content_type'], 'record': after}
                                          for p, after, _ in plan['edits']]})
        self.send_error(HTTPStatus.NOT_FOUND)

    # Handlers

    def product_summary(self, staging):
        manifest, entries = staging.manifest(), staging.entries()
        proposals = manifest.get('edits', [])
        return {'slug': staging.slug, 'product': manifest['product'], 'items': len(manifest['items']) + len(proposals),
                'decided': sum(1 for i in manifest['items'] if i['key'] in entries['items'])
                + sum(1 for e in proposals if e['key'] in entries.get('edits', {}))}

    def product(self, staging):
        manifest, entries = staging.manifest(), staging.entries()
        return {
            'slug': staging.slug,
            'manifest': manifest,
            'entries': entries,
            'suggestions': {i['key']: api.suggest(i, manifest, self.dataset, entries) for i in manifest['items']},
            'forms': api.forms(self.dataset),
            'quantities': self.dataset.has_quantities(),
            'records': api.records_index(self.dataset),
            'references': self.references(),
            'entry_types': api.entry_types(self.dataset),
            'extra_types': [t for t in api.EXTRA_TYPES if t in self.dataset.content_types()],
            'edit_records': {e['key']: edits.find(self.dataset, e['content_type'], e['id'])
                             for e in manifest.get('edits', [])},
        }

    def edit_preview(self, staging, key, decision):
        """What applying a proposed edit would do: image moves and problems."""
        proposal = next((e for e in staging.manifest().get('edits', []) if e['key'] == key), None)
        if proposal is None:
            return {'problems': [f'No proposed edit {key}'], 'images': {}}
        if decision.get('action') != 'apply':
            return {'problems': [], 'images': {}}
        _, moves, problems = edits.preview(self.dataset, proposal, decision)
        return {'problems': problems, 'images': {field: list(move) for field, move in moves.items()}}

    def references(self):
        """content type → an existing image path, to compare new cards against."""
        refs = {}
        for content_type in api.entry_types(self.dataset) + ['sources']:
            fields = importer.image_fields(self.dataset, content_type)
            record = next((r for r in self.dataset.records(content_type) if fields and r.get(fields[0])), None)
            if record:
                refs[content_type] = record[fields[0]]
        for back in self.dataset.records('card-backs'):
            refs.setdefault(f"card-backs:{self.dataset.back_type(back)}", back['image'])
        return refs

    def preview(self, staging, key, query):
        item = staging.items().get(key)
        if not item:
            return self.send_error(HTTPStatus.NOT_FOUND)
        try:
            sizes = images.sizes_for(query.get('type'), query.get('back') or None)
        except KeyError:
            return self.send_error(HTTPStatus.BAD_REQUEST)
        from PIL import Image
        with Image.open(staging.dir / item['file']) as original:
            original.load()
        if sizes is None:
            return self.send_png(original.convert('RGBA'))
        content_type, back = query.get('type'), query.get('back') or None
        large, _ = images.prepare(original, content_type, query.get('field') or 'image', back)
        return self.send_png(images.round_corners(large, images.radius_for(content_type, back, 'large')))

    def update(self, staging, change, entry):
        if entry:
            api.normalise_entry(entry, self.dataset)  # in place, so `change` stores the normalised entry
        with lock:
            entries = staging.entries()
            change(entries)
            staging.save_entries(entries)
        self.send_json({'saved': True, 'problems': api.check_entry(entry, self.dataset) if entry else []})


def serve(port, open_browser=True):
    Handler.dataset = Dataset()
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = f'http://localhost:{port}/'
    print(f'Data entry on {url} (Ctrl+C to stop)')
    if open_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
