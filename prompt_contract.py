"""Versioned component contract and the sole Character Studio prompt compiler.

Library fields contain appearance data, never layout or generation instructions.
The compiler owns panel roles, framing, inheritance, lighting and privacy scope.
"""
from __future__ import annotations

import json
import re

CONTRACT_VERSION = 2
LOWER_FRAME = re.compile(r'\b(?:skirts?|trousers|pants|jeans|shorts|leggings|tights|stockings|socks|shoes|heels|sandals|sneakers|boots|pumps|loafers|mules|stilettos|pantyhose|slippers|feet|footwear|waist|waistline|hips?|thighs?|knees?|ankles?|calves|calf|hemline|hem|handbags?|bags?|purses?|belts?|briefs|panties|thong|garter|bottoms)\b', re.I)
HEAD_ACCESSORY = re.compile(r'\b(?:hats?|berets?|beanies?|headbands?|earmuffs|sunglasses|eyeglasses|earrings|necklaces?|chokers?|headpiece|headdress|hairpins?|hairband|tiara|crown|caps?|halo)\b', re.I)
PRESENTATION = re.compile(r'ghost[- ]mannequin|\bmannequin\b|\binvisible\b|garment-only|\bfloating\b|\b(?:studio|plain|neutral|gray|grey) background\b|\bbbox\b|\b(?:four|three|\d+)[ -]panels?\b|\bheadless\b|\bneckless\b|{{|}}', re.I)
CONTROL_IN_EXTRA = re.compile(r'\b(?:hairstyle|hair|expression|smiling|smile|serious|cheerful|age|years old|shirt|dress|background|panel|headless|neckless|privacy|bbox)\b', re.I)


def content_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field}: enter a nonempty appearance description')
    value = value.strip()
    conflict = PRESENTATION.search(value)
    if conflict:
        raise ValueError(f'{field}: "{conflict[0]}" belongs to card settings, not a library description')
    return value


def validate_outfit(body: str, portrait: str) -> tuple[str, str]:
    body = content_text(body, 'Body outfit')
    portrait = content_text(portrait, 'Portrait clothing')
    if match := LOWER_FRAME.search(portrait):
        raise ValueError(f'Portrait clothing: remove "{match[0]}"; describe only the neckline, shoulders, upper chest and head accessories')
    if match := HEAD_ACCESSORY.search(body):
        raise ValueError(f'Body outfit: move "{match[0]}" to Portrait clothing; the three body panels have no head or neck')
    return body, portrait


def validate_character(c: dict) -> dict:
    if not isinstance(c, dict):
        raise ValueError('Character settings must be an object')
    required = {'age', 'presentation', 'body_shape', 'hair_style', 'hair_color', 'expression',
                'extra_character_details', 'face_description', 'reference_hair'}
    if missing := required - c.keys():
        raise ValueError(f'Missing character fields: {sorted(missing)}')
    if unknown := c.keys() - required - {'age_mode', 'schema_version'}:
        raise ValueError(f'Unknown character fields: {sorted(unknown)}')
    if c.get('schema_version', CONTRACT_VERSION) != CONTRACT_VERSION:
        raise ValueError('Unsupported Character Studio prompt contract')
    if type(c['age']) is not int or not 18 <= c['age'] <= 100:
        raise ValueError('This anatomical character-card template requires an adult age')
    choices = {
        'age_mode': ('Set age', 'From face selection'),
        'presentation': ('woman', 'man', 'person', 'From face selection'),
        'body_shape': ('slim', 'average', 'athletic', 'curvy', 'broad'),
        'hair_style': ('From face selection', 'Elegant updo', 'Short bob', 'Pixie cut', 'Shoulder-length waves', 'Long straight hair', 'Long loose curls'),
        'hair_color': ('From face selection', 'Black', 'Brown', 'Auburn', 'Blonde', 'Silver', 'Pink', 'Blue'),
        'expression': ('From face selection', 'Calm and relaxed', 'Soft smile', 'Serious', 'Cheerful'),
    }
    c = dict(c, age_mode=c.get('age_mode', 'Set age'), schema_version=CONTRACT_VERSION)
    for key, allowed in choices.items():
        if c[key] not in allowed:
            raise ValueError(f'Invalid {key}: select a supported value')
    for key in ('face_description', 'reference_hair', 'extra_character_details'):
        if not isinstance(c[key], str):
            raise ValueError(f'{key} must be text')
    if match := CONTROL_IN_EXTRA.search(c['extra_character_details']):
        raise ValueError(f'Additional portrait details: use the dedicated control for "{match[0]}"')
    if c['extra_character_details'].strip():
        content_text(c['extra_character_details'], 'Additional portrait details')
    return c


def identity_caption(c: dict, reference: bool) -> str:
    if reference:
        parts = ['Match the facial identity of the supplied reference image 1. Preserve its facial geometry and distinctive features.']
        parts.append('Preserve the apparent adult age of the reference.' if c['age_mode'] == 'From face selection' else f'Show this adult person at age {c["age"]}.')
        parts.append('Preserve the gender presentation of the reference.' if c['presentation'] == 'From face selection' else f'Gender presentation: {c["presentation"]}.')
        for key, label in (('hair_style', 'hairstyle'), ('hair_color', 'hair color'), ('expression', 'expression')):
            parts.append(f'Preserve the {label} of the reference.' if c[key] == 'From face selection' else f'Change only the {label} to: {c[key]}.')
        if c['expression'] == 'From face selection':
            parts.append('Keep whether the mouth is open or closed, whether teeth are visible, and the smile intensity exactly as in the reference.')
    else:
        from .face_contract import parse_face
        face = parse_face(c['face_description'], c['reference_hair'])
        hair = face['hair']['style'] if c['hair_style'] == 'From face selection' else c['hair_style']
        color = face['hair']['color'] if c['hair_color'] == 'From face selection' else c['hair_color']
        if color and c['hair_style'] == 'From face selection' and not face['hair']['color']:
            from .face_contract import HAIR_COLORS
            if HAIR_COLORS.search(hair):
                raise ValueError('Separate hair style and color in the face library before overriding hair color')
        parts = [face['geometry']]
        if hair: parts.append('Hairstyle: ' + hair.rstrip(' .') + '.')
        if color: parts.append('Hair color: ' + color.rstrip(' .') + '.')
        if c['age_mode'] == 'Set age': parts.append(f'Adult age {c["age"]}.')
        if c['presentation'] != 'From face selection': parts.append(f'Adult {c["presentation"]}.')
        expression = face['expression'] if c['expression'] == 'From face selection' else c['expression']
        if expression: parts.append('Expression: ' + expression.rstrip(' .') + '.')
    if c['extra_character_details'].strip():
        parts.append('Additional portrait details: ' + c['extra_character_details'].strip())
    return ' '.join(p.strip() for p in parts if p.strip())


def compile_card(long_edge: int, short_edge: int, privacy_blocks: bool, character: str,
                 outfit_description: str, portrait_clothing: str, lighting: str,
                 reference_identity: bool) -> tuple[str, int, int]:
    from .layout import build_four_view_layout
    from .outfit_contract import parse_spec, render_view
    c = validate_character(json.loads(character))
    outfit = parse_spec(outfit_description, portrait_clothing)
    upper_outfit = outfit['portrait']
    if type(reference_identity) is not bool:
        raise ValueError('reference_identity must be a boolean')
    if lighting not in ('Soft even studio light', 'Soft window light', 'Clean catalog lighting'):
        raise ValueError('Select a supported lighting setting')
    summary = ('Exactly four separate photographs in one horizontal row on matching neutral light-gray studio backgrounds: '
               'identity portrait, front body-proportion reference, clothed front view, clothed back view. '
               'Place every view inside its own bounding box. Only the portrait shows a complete head. '
               'The other three views show the same adult body proportions and matching skin tone, at one shoulder-to-floor scale. '
               'Align their shoulder heights and ground baselines. Keep shoulder, waist and hip widths and limb lengths consistent. '
               'No text, labels or additional people. Natural skin and fabric. ' + lighting + '.')
    portrait = ('One close photographic identity portrait of the same adult person. ' + identity_caption(c, reference_identity) +
                ' Show the complete head and hair with a small margin above the crown, natural head-to-shoulder proportions, '
                'shoulders and upper chest only. The frame ends at the upper chest. Upper clothing and portrait accessories: ' + upper_outfit)
    body_shared = (f'The same adult person with a {c["body_shape"]} build and matching skin tone. '
                   'The head and entire neck are invisible. Keep clear gray background above the complete shoulder silhouette. '
                   'Arms relaxed, both hands and all feet fully inside the region, with space below the soles. ')
    body = ('One straight-on FRONT adult body-proportion reference. ' + body_shared +
            'Neutral nonsexual anatomical reference with no clothing, footwear or accessories. '
            'Bare feet and visible toes touch the baseline. The selected shoes belong only to the two clothed panels. ')
    front = ('One complete straight-on FRONT outfit and body view, with footwear toes facing the camera. ' + body_shared +
             'The garment neckline is hollow, with no throat or neck stump above it. Wear: ' + render_view(outfit, 'front'))
    back = ('One complete straight-on BACK outfit and body view after a 180-degree turn, showing the backs of the heels. ' + body_shared +
            'The garment neckline is hollow, with no throat or neck stump above it. Show the back of the same outfit, '
            'with coherent colors, materials, lengths and footwear. Do not mirror the front photograph or copy its visible chest details onto the rear. '
            'Do not invent rear graphics or fasteners when they are unspecified. Wear: ' + render_view(outfit, 'back'))
    prompt = build_four_view_layout(long_edge, short_edge, privacy_blocks,
        summary_caption=summary, portrait_caption=portrait, body_caption=body,
        front_caption=front, back_caption=back)
    return prompt, long_edge, short_edge
