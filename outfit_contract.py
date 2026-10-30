"""Spatial garment facts shared by UI, catalog import and prompt compilation."""
from __future__ import annotations
import json
import re
from .prompt_contract import content_text, validate_outfit

VERSION = 2
FIELDS = {'schema_version', 'shared', 'front', 'back', 'portrait', 'asymmetries'}
SIDE_WORDS = re.compile(r'\b(?:left|right)\b', re.I)
VIEW_WORDS = re.compile(r'\b(?:front|back|rear|viewer|image)\b|backless', re.I)


def validate_spec(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('Outfit requires shared, front, back, portrait and asymmetries fields')
    if value['schema_version'] != VERSION:
        raise ValueError('Unsupported outfit prompt contract version')
    spec = dict(value)
    for key in ('shared', 'front', 'back', 'portrait'):
        if not isinstance(spec[key], str):
            raise ValueError(f'Outfit {key} must be text')
        spec[key] = spec[key].strip()
        if spec[key]: content_text(spec[key], f'Outfit {key}')
    if not spec['shared'] or not spec['portrait']:
        raise ValueError('Shared garment identity and portrait clothing are required')
    if VIEW_WORDS.search(spec['shared']) or SIDE_WORDS.search(spec['shared']):
        raise ValueError('Shared garment identity cannot contain view or side instructions; use view details or asymmetric features')
    for key, forbidden in [('front', r'\b(?:back|rear)\b'), ('back', r'\bfront\b')]:
        if re.search(forbidden, spec[key], re.I) or SIDE_WORDS.search(spec[key]):
            raise ValueError(f'Outfit {key}: use its own visible details; put left/right features in Asymmetric features')
    if not isinstance(spec['asymmetries'], list) or len(spec['asymmetries']) > 24:
        raise ValueError('Use at most 24 asymmetric features')
    facts = []
    for fact in spec['asymmetries']:
        if not isinstance(fact, dict) or set(fact) != {'description', 'side', 'visible_in'}:
            raise ValueError('Each asymmetric feature requires description, side and visible_in')
        if fact['side'] not in ('left', 'right', 'center', 'both') or fact['visible_in'] not in ('front', 'back', 'both'):
            raise ValueError('Choose a wearer side and the views where the feature is visible')
        description = content_text(fact['description'], 'Asymmetric feature')
        if SIDE_WORDS.search(description) or VIEW_WORDS.search(description):
            raise ValueError('Use the side/view selectors instead of directions in the feature description')
        facts.append(dict(fact, description=description))
    seen = {}
    for fact in facts:
        key = fact['description'].casefold().strip(' .')
        if key in seen and seen[key] != fact['side']:
            raise ValueError('The same feature cannot change wearer side between views; use Both for a symmetric pair')
        seen[key] = fact['side']
    spec['asymmetries'] = facts
    validate_outfit(' '.join([spec['shared'],spec['front'],spec['back'],*(x['description'] for x in facts)]), spec['portrait'])
    return spec


def parse_spec(value: str, portrait: str) -> dict:
    if value.lstrip().startswith('{'):
        spec = validate_spec(json.loads(value))
        if spec['portrait'] != portrait.strip():
            raise ValueError('Portrait clothing and outfit specification disagree; connect both outputs from the same outfit component')
        return spec
    # Old hand-authored simple colors/garments remain usable; directional prose does not.
    return validate_spec(dict(schema_version=VERSION,shared=value,front='',back='',portrait=portrait,asymmetries=[]))


def render_view(spec: dict, view: str) -> str:
    spec = validate_spec(spec)
    if view not in ('front', 'back'): raise ValueError('Unknown garment view')
    parts = [spec['shared']]
    if spec[view]: parts.append(spec[view])
    for fact in spec['asymmetries']:
        if fact['visible_in'] not in ('both', view): continue
        side = fact['side']
        if side == 'both':
            location = 'as a matching symmetric pair on both body sides'
        elif side == 'center':
            location = 'on the body centerline'
        else:
            viewer = ('right' if side == 'left' else 'left') if view == 'front' else side
            location = f'on the wearer\'s {side} side, which appears on the viewer\'s {viewer} in this {view} view'
        parts.append(f'{fact["description"].rstrip(" .;")} {location}.')
    return ' '.join(parts)
