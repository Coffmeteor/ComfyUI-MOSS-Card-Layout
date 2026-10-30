"""Independent facial geometry, hairstyle, hair color and expression fields."""
from __future__ import annotations
import json
import re
from .prompt_contract import content_text

FIELDS = {'schema_version', 'geometry', 'hair', 'expression'}
EXPRESSION = re.compile(r'\b(?:smil\w*|grin\w*|frown\w*|laugh\w*|teeth|expression|parted|closed|open)\b', re.I)
HAIR_COLORS = re.compile(r'\b(?:(?:dark|light|jet|ash|platinum|golden|reddish)[ -])?(?:black|brown|auburn|blond[e]?|silver|gr[ae]y|white|pink|blue|red|chestnut)\b', re.I)


def validate_face(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('Face requires geometry, hair and expression fields')
    if value['schema_version'] != 2:
        raise ValueError('Unsupported face prompt contract version')
    result = dict(value)
    for key in ('geometry','expression'):
        if not isinstance(value[key],str):raise ValueError(f'Face {key} must be text')
        result[key] = value[key].strip()
        if result[key]:content_text(result[key],f'Face {key}')
    if not result['geometry']:raise ValueError('Describe facial geometry')
    if re.search(r'\bhair\b|hairstyle',result['geometry'],re.I) or EXPRESSION.search(result['geometry']):
        raise ValueError('Face geometry contains hair or expression; move it into its dedicated field')
    hair = value['hair']
    # A simple legacy hairstyle remains readable; new catalog records use explicit style/color.
    if isinstance(hair,str):
        hair={'style':hair.strip(),'color':''}
    if not isinstance(hair,dict) or set(hair) != {'style','color'}:
        raise ValueError('Hair requires separate style and color fields')
    for key in ('style','color'):
        if not isinstance(hair[key],str):raise ValueError(f'Hair {key} must be text')
        if hair[key].strip():content_text(hair[key],f'Hair {key}')
    if isinstance(value['hair'],dict) and HAIR_COLORS.search(hair['style']):
        raise ValueError('Move hair color words out of hairstyle and into Hair color')
    if re.search(r'\b(?:smil\w*|grin\w*|frown\w*|laugh\w*|teeth|mouth|lips|expression)\b',hair['style'],re.I):
        raise ValueError('Hairstyle cannot contain expression')
    result['hair']={k:v.strip() for k,v in hair.items()}
    if re.search(r'\b(?:age|aged|years.old|ethnic\w*|nationality)\b', json.dumps(result),re.I):
        raise ValueError('Face fields contain age or demographic instructions; use character controls')
    if re.search(r'\bclosed\b',result['expression'],re.I) and re.search(r'\b(?:parted|open)\b',result['expression'],re.I):
        raise ValueError('Expression must use one mouth state: closed or parted')
    return result


def parse_face(value: str, hair: str = '') -> dict:
    if value.lstrip().startswith('{'):
        return validate_face(json.loads(value))
    return validate_face(dict(schema_version=2,geometry=value,hair=hair,expression=''))
