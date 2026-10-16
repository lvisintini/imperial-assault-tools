"""Reading the cards.boardwars.eu gallery (a Zenphoto site): albums, their sub-albums and images, and the URL of each
image's original file."""
import re
import time
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import requests
from parsel import Selector
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = 'https://cards.boardwars.eu/'
USER_AGENT = 'ia-tools (imperial-assault-data maintenance; https://github.com/lvisintini/imperial-assault-data)'
REQUEST_INTERVAL = 1.0  # seconds between requests

# Thumbnails live at /cache/<album path>/<name>_275_thumb_ffflogog_whatermark_cc.<ext>?cached=...; the original is
# /albums/<album path>/<name>.<ext>. The 2017–18 crawler used the same rewrite.
THUMB_SUFFIX = re.compile(r'_[0-9]{3}_thumb_[a-zA-Z]{8}_whatermark_cc(?=\.[A-Za-z0-9]+$)')


@dataclass(frozen=True)
class ImageRef:
    path: tuple[str, ...]  # album names from the gallery root, e.g. ('Expansion Boxes', 'Tyrants of Lothal', 'Command Cards')
    name: str              # the image's alt text, usually the card name
    url: str               # the original file


@dataclass
class AlbumPage:
    url: str
    path: tuple[str, ...]
    albums: list[tuple[str, str]]  # (url, name) of each sub-album
    images: list[ImageRef]
    next_page: str | None


def clean_title(title):
    """Album title without the " (2)" Zenphoto appends on later pages."""
    return re.sub(r'\s+\(\d+\)$', '', ' '.join(title.split()))


def original_url(thumbnail_src):
    path = urlsplit(thumbnail_src).path
    if not path.startswith('/cache/'):
        raise ValueError(f'Not a gallery thumbnail: {thumbnail_src}')
    return urljoin(BASE_URL, THUMB_SUFFIX.sub('', '/albums/' + path.removeprefix('/cache/')))


def parse_album_page(html, url):
    page = Selector(text=html)
    heading = page.css('#gallerytitle h2')
    # The breadcrumb: links after the gallery index link, then the current album's name as trailing text.
    crumbs = heading.xpath('.//a[contains(@class, "galleryindexurl")]/following-sibling::a/@title').getall()
    current = clean_title(''.join(heading.xpath('./text()').getall()))
    path = tuple(crumbs) + ((current,) if current else ())

    albums = [
        (urljoin(url, album.css('h3 a::attr(href)').get()), ' '.join(album.css('h3 a::text').get('').split()))
        for album in page.css('div.album')
    ]
    images = [
        ImageRef(path=path, name=' '.join(image.css('img::attr(alt)').get('').split()),
                 url=original_url(image.css('img::attr(src)').get()))
        for image in page.css('div.image')
    ]
    next_page = page.css('ul.pagelist li.next a::attr(href)').get()
    return AlbumPage(url=url, path=path, albums=albums, images=images,
                     next_page=urljoin(url, next_page) if next_page else None)


class Client:
    """A polite HTTP client: one request at a time, at most one per REQUEST_INTERVAL, honouring robots.txt."""

    def __init__(self, session=None, interval=REQUEST_INTERVAL):
        self.session = session or requests.Session()
        self.session.headers['User-Agent'] = USER_AGENT
        retries = Retry(total=4, backoff_factor=5, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        self.interval = interval
        self.last_request = 0.0
        self.robots = None

    def get(self, url):
        if self.robots is None:
            self.robots = urllib.robotparser.RobotFileParser()
            self.robots.parse(self._get(urljoin(BASE_URL, '/robots.txt')).text.splitlines())
        if not self.robots.can_fetch(USER_AGENT, url):
            raise PermissionError(f'robots.txt disallows {url}')
        response = self._get(url)
        response.raise_for_status()
        return response

    def _get(self, url, attempts=4):
        # The adapter retries failed connections; this also covers a connection dropped while reading the body.
        for attempt in range(attempts):
            wait = self.last_request + self.interval * (1 + 4 * attempt) - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                return self.session.get(url, timeout=60)
            except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.Timeout):
                if attempt == attempts - 1:
                    raise
            finally:
                self.last_request = time.monotonic()


def crawl(client, start_url, on_page=None):
    """Yield every image in the album at start_url and all its sub-albums, following pagination."""
    queue, seen = [start_url], set()
    while queue:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        page = parse_album_page(client.get(url).text, url)
        if on_page:
            on_page(page)
        yield from page.images
        queue.extend(album_url for album_url, _ in page.albums)
        if page.next_page:
            queue.append(page.next_page)
