"""Turn a boardwars original into the dataset's large and small PNGs.

Same steps as the 2017–18 StandardImageDimension task: RGBA, scaled to fit the type's size, centred on a transparent
canvas of exactly that size. Sizes mirror the data repo's README table (tests/test_images.py ImageTestHelper)."""
import io

from PIL import Image, ImageOps

from ia_tools import settings

SOURCE = {'large': (300, 300), 'small': (300, 300)}
STANDARD = {'large': (476, 740), 'small': (301, 470)}
MINI = {'large': (424, 657), 'small': (293, 454)}
MINI_FLIPPED = {'large': (657, 424), 'small': (454, 293)}
HERO = {'large': (1490, 1186), 'small': (650, 515)}
ANY = None  # skirmish maps keep their size, and the small copy is the same file

SIZES = {
    'sources': SOURCE, 'skirmish-maps': ANY, 'agenda-cards': STANDARD, 'command-cards': MINI,
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


def sizes_for(content_type, back_content_type=None):
    if content_type == 'card-backs':
        return BACK_SIZES[back_content_type]
    return SIZES[content_type]


def fit(image, size):
    """Scale to fit within size (up or down), centred on a transparent canvas of exactly that size."""
    image = ImageOps.contain(image.convert('RGBA'), size, Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', size)
    canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    return canvas


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


def process(original_path, content_type, back_content_type=None):
    """{'large': bytes, 'small': bytes, 'upscaled': bool} for one original."""
    sizes = sizes_for(content_type, back_content_type)
    with Image.open(original_path) as original:
        original.load()
    if sizes is ANY:
        data = encode(original.convert('RGBA'))
        return {'large': data, 'small': data, 'upscaled': False}
    upscaled = original.width < sizes['large'][0] and original.height < sizes['large'][1]
    return {
        'large': encode(fit(original, sizes['large'])),
        'small': encode(fit(original, sizes['small'])),
        'upscaled': upscaled,
    }
