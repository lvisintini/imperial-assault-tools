"""Turn a boardwars original into the dataset's large and small PNGs.

Same steps as the 2017–18 pipeline: RGBA, scaled to fit the type's size and centred on a transparent canvas of exactly
that size, then aligned to the 2018 templates (align.py), with transparent rounded corners. The small image is made
from the aligned large one. Sizes mirror the data repo's README table (tests/test_images.py ImageTestHelper)."""
import io

from PIL import Image, ImageChops, ImageDraw, ImageOps

from ia_tools import align, settings
from ia_tools.dataset import canonical

SOURCE = {'large': (300, 300), 'small': (300, 300)}
STANDARD = {'large': (476, 740), 'small': (301, 470)}
MINI = {'large': (424, 657), 'small': (293, 454)}
MINI_FLIPPED = {'large': (657, 424), 'small': (454, 293)}
HERO = {'large': (1490, 1186), 'small': (650, 515)}
ANY = None  # skirmish maps keep their size, and the small copy is the same file

SIZES = {
    'sources': SOURCE, 'maps': ANY, 'agenda-cards': STANDARD, 'command-cards': MINI,
    'condition-cards': MINI, 'deployment-cards': STANDARD, 'heroes': HERO, 'hero-class-cards': MINI,
    'imperial-class-cards': MINI, 'supply-cards': MINI, 'story-mission-cards': STANDARD,
    'side-mission-cards': STANDARD, 'reward-cards': MINI, 'companion-cards': STANDARD, 'upgrade-cards': MINI,
    'threat-mission-cards': STANDARD, 'form-cards': MINI_FLIPPED,
}
# card-backs, by the content type they're keyed on (card-backs.content_type).
BACK_SIZES = {
    'agenda-decks': STANDARD, 'command-cards': MINI, 'companion-cards': STANDARD, 'condition-cards': MINI,
    'deployment-cards': STANDARD, 'imperial-classes': MINI, 'heroes': MINI, 'upgrade-cards': MINI,
    'reward-cards': MINI, 'supply-cards': MINI, 'side-mission-cards': STANDARD, 'story-mission-cards': STANDARD,
    'threat-mission-cards': STANDARD, 'form-cards': MINI_FLIPPED,
}


# Corner radius at the large size, in pixels, measured from the dataset's 2018 images (the transparent run along a
# card's edge, matched by simulating this mask); the small size scales it with the width. Types not listed (hero
# sheets, product images, maps) keep square corners, as in 2018.
CARD_RADIUS = 32
RADII = {
    'agenda-cards': CARD_RADIUS, 'deployment-cards': CARD_RADIUS, 'hero-class-cards': CARD_RADIUS,
    'imperial-class-cards': CARD_RADIUS, 'reward-cards': CARD_RADIUS, 'side-mission-cards': CARD_RADIUS,
    'story-mission-cards': CARD_RADIUS, 'threat-mission-cards': CARD_RADIUS, 'upgrade-cards': CARD_RADIUS,
    'form-cards': CARD_RADIUS, 'command-cards': 35, 'companion-cards': 35, 'supply-cards': 27, 'condition-cards': 24,
    'card-backs': 22,
}
SUPERSAMPLE = 4  # the mask is drawn this much bigger and scaled down, for smooth (anti-aliased) corners


def sizes_for(content_type, back_content_type=None):
    """Sizes by type; 1.x names (skirmish-maps) work too."""
    if content_type == 'card-backs':
        return BACK_SIZES[canonical(back_content_type)]
    return SIZES[canonical(content_type)]


def fit(image, size):
    """Scale to fit within size (up or down), centred on a transparent canvas of exactly that size."""
    image = ImageOps.contain(image.convert('RGBA'), size, Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', size)
    canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


def radius_for(content_type, back_content_type, size_name):
    radius = RADII.get(content_type)
    if not radius or size_name == 'large':
        return radius
    sizes = sizes_for(content_type, back_content_type)
    return round(radius * sizes['small'][0] / sizes['large'][0])


def round_corners(image, radius):
    """Transparent rounded corners on the card itself (its non-transparent bounding box)."""
    if not radius:
        return image
    box = image.getchannel('A').getbbox()
    if not box:
        return image
    width, height = box[2] - box[0], box[3] - box[1]
    mask = Image.new('L', (width * SUPERSAMPLE, height * SUPERSAMPLE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mask.width - 1, mask.height - 1), radius=radius * SUPERSAMPLE,
                                           fill=255)
    corners = Image.new('L', image.size, 0)
    corners.paste(mask.resize((width, height), Image.Resampling.BOX), box[:2])  # BOX: exact coverage, edges stay 255
    rounded = image.copy()
    rounded.putalpha(ImageChops.multiply(image.getchannel('A'), corners))
    return rounded


def encode(image):
    """PNG bytes. The dataset's images are palette PNGs from TinyPNG; without a TINIFY_KEY, quantise locally."""
    buffer = io.BytesIO()
    if settings.TINIFY_KEY:
        import tinify

        tinify.key = settings.TINIFY_KEY
        image.save(buffer, 'PNG')
        return tinify.from_buffer(buffer.getvalue()).to_buffer()
    image.quantize(256, method=Image.Quantize.FASTOCTREE).save(buffer, 'PNG', optimize=True)
    return buffer.getvalue()


def prepare(original, content_type, image_field='image', back_content_type=None):
    """(large RGBA image, alignment), corners still square: aligned to a template when one matches (align.py),
    otherwise fitted (centred, aspect kept)."""
    size = sizes_for(content_type, back_content_type)['large']
    aligned, alignment = align.align(original, size, content_type, image_field, back_content_type)
    return (aligned, alignment) if alignment else (fit(original, size), None)


def process(original_path, content_type, back_content_type=None, image_field='image'):
    """{'large': bytes, 'small': bytes, 'upscaled': bool, 'alignment': {'template', 'cc'} | None} for one original."""
    sizes = sizes_for(content_type, back_content_type)
    with Image.open(original_path) as original:
        original.load()
    if sizes is ANY:
        data = encode(original.convert('RGBA'))
        return {'large': data, 'small': data, 'upscaled': False, 'alignment': None}
    upscaled = original.width < sizes['large'][0] and original.height < sizes['large'][1]
    large, alignment = prepare(original, content_type, image_field, back_content_type)
    # Stretched (by under 0.5%), not fitted: the small sizes' aspect differs slightly, and fitting would pad an edge.
    small = large.resize(sizes['small'], Image.Resampling.LANCZOS)
    return {
        'large': encode(round_corners(large, radius_for(content_type, back_content_type, 'large'))),
        'small': encode(round_corners(small, radius_for(content_type, back_content_type, 'small'))),
        'upscaled': upscaled,
        'alignment': alignment,
    }
