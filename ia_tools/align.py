"""Align a card to the 2018 templates (assets/templates), so its border sits where the dataset's other cards' do.

The 2018 pipeline (imperial_assault_tools/scripts/first_batch.py) ran OpenCV's ECC against one template per kind of
card, picked by fields that no longer exist. Here every template a type was aligned to is tried and the best
correlation wins. A warp is only used if it is plausible (no big scale, shear or shift) and correlates better than
leaving the card as it is; otherwise the card stays unaligned and the result says so.

Checked against 55 boardwars originals of cards already in the dataset: the aligned card is closer to the 2018 image
for 85% of them (median mean-grey difference 20.4 → 9.3)."""
from functools import cache

import cv2
import numpy
from PIL import Image

from ia_tools import settings

UPGRADES = [f'upgrade-cards/{n}.png' for n in
            ('concussion-grenades', 'dh-17', 'electrostaff', 'energized-hilt', 'laminate-armor', 'sniper-scope')]
CLASSES = ['imperial-class-cards/hutt-mercenaries-guild-hunters.png', 'imperial-class-cards/hutt-mercenaries-most-wanted.png']
FEAT = 'hero-class-cards/davith-elso-embody-the-force.png'
MISSION_BACK = 'card-backs/threat-mission-return-to-hoth.png'

# content type (or (content type, image field)) → templates, relative to assets/templates.
TEMPLATES = {
    'deployment-cards': ['deployment-cards/leia-organa-rebel-commander-campaign.png',
                         'deployment-cards/last-resort-skirmish.png', 'deployment-cards/clawdite-shapeshifter.png'],
    'agenda-cards': ['agenda-cards/jabbas-empire-head-hunting.png',
                     'agenda-cards/stormtrooper-support-strength-of-command.png', 'side-mission-cards/homecoming.png'],
    'command-cards': [f'command-cards/{n}.png' for n in ('a-powerful-influence', 'bodyguard', 'comm-disruption', 'crush',
                                                         'mitigate', 'of-no-importance', 'tough-luck')],
    'companion-cards': ['companion-cards/salacious-b-crumb.png'],
    'condition-cards': ['condition-cards/weakened.png'],
    'supply-cards': ['supply-cards/troop-data.png'],
    'imperial-class-cards': CLASSES,
    'reward-cards': CLASSES + UPGRADES + [FEAT],
    'upgrade-cards': UPGRADES,
    'hero-class-cards': UPGRADES + [FEAT],
    'side-mission-cards': [f'side-mission-cards/{n}.png' for n in ('born-from-death', 'cloud-citys-secret', 'homecoming')],
    'story-mission-cards': ['story-mission-cards/chain-of-command.png'],
    'threat-mission-cards': ['threat-mission-cards/scouring-of-the-homestead.png'],
    'form-cards': ['form-cards/clawdite-shapeshifter-scout.png'],
    ('heroes', 'healthy'): ['heroes/murne-rin-healthy.png'],
    ('heroes', 'wounded'): ['heroes/diala-passil-wounded.png'],
}
# card-backs, by the content type they're the back of.
BACK_TEMPLATES = {
    'side-mission-cards': [MISSION_BACK], 'story-mission-cards': [MISSION_BACK], 'threat-mission-cards': [MISSION_BACK],
    'deployment-cards': ['card-backs/deployment-imperial.png'],
    'heroes': ['card-backs/rebel-hero-gideon-argus.png'],
    'imperial-classes': ['card-backs/imperial-class-inspiring-leadership.png'],
    'upgrade-cards': ['card-backs/rebel-upgrade-tier-1.png'],
    'condition-cards': ['card-backs/condition-focused.png'],
}

PYRAMID_LEVELS = 2       # coarse-to-fine: 1/4, 1/2, then full size
MAX_SCALE_CHANGE = 0.1   # a plausible warp keeps scale within 10%,
MAX_SHEAR = 0.03         # hardly shears,
MAX_SHIFT = 0.06         # and moves the card by at most 6% of its size
MIN_GAIN = 0.01          # and must correlate this much better than the unaligned card


def templates_for(content_type, image_field='image', back_content_type=None):
    if content_type == 'card-backs':
        return BACK_TEMPLATES.get(back_content_type, [])
    if content_type == 'heroes' and image_field not in ('healthy', 'wounded'):  # side unknown (the entry app's preview)
        return TEMPLATES['heroes', 'healthy'] + TEMPLATES['heroes', 'wounded']
    return TEMPLATES.get((content_type, image_field)) or TEMPLATES.get(content_type, [])


def grey(rgba):
    """Grey levels as float32, transparent pixels read as white (the templates' background)."""
    alpha = rgba[:, :, 3:4] / 255.0
    luma = cv2.cvtColor(numpy.ascontiguousarray(rgba[:, :, :3]), cv2.COLOR_RGB2GRAY)[:, :, None]
    return (luma * alpha + 255 * (1 - alpha))[:, :, 0].astype(numpy.float32)


@cache
def template_grey(name):
    """A template's grey levels at its own size: the frame a card aligned to it ends up in."""
    with Image.open(settings.TEMPLATES / name) as template:
        return grey(numpy.asarray(template.convert('RGBA')))


def ecc(reference, image):
    """(correlation, 2x3 affine warp) taking image onto reference, or None when ECC doesn't converge."""
    warp = numpy.eye(2, 3, dtype=numpy.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-5)
    cc = None
    for level in range(PYRAMID_LEVELS, -1, -1):
        scale = 2 ** level
        ref, img = (reference, image) if scale == 1 else (
            cv2.resize(a, None, fx=1 / scale, fy=1 / scale, interpolation=cv2.INTER_AREA) for a in (reference, image))
        step = warp.copy()
        step[:, 2] /= scale
        try:
            cc, step = cv2.findTransformECC(ref, img, step, cv2.MOTION_AFFINE, criteria, None, 5)
        except cv2.error:
            return None
        warp = step.copy()
        warp[:, 2] *= scale
    return cc, warp


def plausible(warp, size):
    linear = warp[:, :2]
    sx, sy = numpy.linalg.norm(linear[:, 0]), numpy.linalg.norm(linear[:, 1])
    shear = abs(float(linear[:, 0] @ linear[:, 1])) / (sx * sy)
    return (abs(sx - 1) < MAX_SCALE_CHANGE and abs(sy - 1) < MAX_SCALE_CHANGE and shear < MAX_SHEAR
            and abs(warp[0, 2]) < MAX_SHIFT * size[0] and abs(warp[1, 2]) < MAX_SHIFT * size[1])


def correlation(a, b):
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / numpy.sqrt((a * a).sum() * (b * b).sum()))


def align(original, size, content_type, image_field='image', back_content_type=None):
    """(RGBA image of exactly size, {'template', 'cc'}) with the card aligned to the best-matching template, or
    (None, None) when none matches well enough.

    As in 2018, the card is warped into the template's own frame (a few pixels smaller than the canvas, e.g. 474x740)
    and centred on a transparent canvas. The warp's uncovered edges repeat the card's edge pixels, not transparency."""
    original = original.convert('RGBA')
    best = None
    for name in templates_for(content_type, image_field, back_content_type):
        reference = template_grey(name)
        frame = (reference.shape[1], reference.shape[0])
        rgba = numpy.asarray(original.resize(frame, Image.Resampling.LANCZOS))  # alignment corrects the stretch
        card = grey(rgba)
        found = ecc(reference, card)
        if not found or not plausible(found[1], frame):
            continue
        if found[0] - correlation(reference, card) > MIN_GAIN and (best is None or found[0] > best[0]):
            best = (found[0], found[1], name, rgba, frame)
    if best is None:
        return None, None
    cc, warp, name, rgba, frame = best
    aligned = cv2.warpAffine(rgba, warp, frame, flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                             borderMode=cv2.BORDER_REPLICATE)
    canvas = Image.new('RGBA', size)
    canvas.paste(Image.fromarray(aligned, 'RGBA'), ((size[0] - frame[0]) // 2, (size[1] - frame[1]) // 2))
    return canvas, {'template': name, 'cc': round(float(cc), 3)}
