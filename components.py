"""Small character controls compiled into the established four-panel contract."""
from __future__ import annotations
import json
import re
from pathlib import Path
from . import wardrobe, user_library
from .layout import build_four_view_layout

TEMPLATE = Path(__file__).parent/'resources/character-card-template.json'


class MOSSOutfitLibrary:
    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {'required':{'outfit_id':('STRING',{'default':'SPR-0048'}),
                            'extra_outfit_details':('STRING',{'default':'','multiline':True})}}
    RETURN_TYPES=('STRING','STRING')
    RETURN_NAMES=('outfit_description','portrait_clothing')
    FUNCTION='build';CATEGORY='MOSS-Image/Character Studio'

    @classmethod
    def IS_CHANGED(cls, **kwargs) -> str:
        return json.dumps(wardrobe.get_entry(kwargs['outfit_id']),sort_keys=True)

    def build(self, outfit_id: str, extra_outfit_details: str) -> tuple[str,str]:
        e=wardrobe.get_entry(outfit_id)
        return e['description']+' '+extra_outfit_details,e['portrait_description']


class MOSSCharacterSettings:
    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {'required':{
            'age_mode':(['Set age','From face selection'],),
            'age':('INT',{'default':25,'min':18,'max':100}),
            'presentation':(['woman','man','person','From face selection'],),
            'body_shape':(['slim','average','athletic','curvy','broad'],),
            'hair_style':(['From face selection','Elegant updo','Short bob','Pixie cut','Shoulder-length waves','Long straight hair','Long loose curls'],),
            'hair_color':(['From face selection','Black','Brown','Auburn','Blonde','Silver','Pink','Blue'],),
            'expression':(['From face selection','Calm and relaxed','Soft smile','Serious','Cheerful'],),
            'extra_character_details':('STRING',{'default':'','multiline':True}),
            'face_description':('STRING',{'forceInput':True}),
            'reference_hair':('STRING',{'forceInput':True})}}
    RETURN_TYPES=('STRING',);RETURN_NAMES=('character',)
    FUNCTION='build';CATEGORY='MOSS-Image/Character Studio'

    def build(self, **values) -> tuple[str]:
        if type(values['age']) is not int or not 18 <= values['age'] <= 100:
            raise ValueError('This anatomical character-card template requires an adult age')
        return (json.dumps(values,ensure_ascii=False),)


class MOSSCharacterCardComposer:
    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {'required':{
            'long_edge':('INT',{'default':1824,'min':256,'max':4096,'step':16}),
            'short_edge':('INT',{'default':1024,'min':256,'max':4096,'step':16}),
            'privacy_blocks':('BOOLEAN',{'default':True}),
            'character':('STRING',{'forceInput':True}),
            'outfit_description':('STRING',{'forceInput':True}),
            'portrait_clothing':('STRING',{'forceInput':True}),
            'lighting':(['Soft even studio light','Soft window light','Clean catalog lighting'],),
            'reference_identity':('BOOLEAN',{'default':False,'tooltip':'Enable only in the face-reference workflow; it must be connected to reference image conditioning.'})}}
    RETURN_TYPES=('STRING','INT','INT');RETURN_NAMES=('layout_json','width','height')
    FUNCTION='build';CATEGORY='MOSS-Image/Character Studio'

    def build(self,long_edge:int,short_edge:int,privacy_blocks:bool,character:str,
              outfit_description:str,portrait_clothing:str,lighting:str,reference_identity:bool) -> tuple[str,int,int]:
        c=json.loads(character);age=c['age'];person=c['presentation'];shape=c['body_shape']
        inherited_age=c.get('age_mode','Set age')=='From face selection'
        inherited_person=person=='From face selection'
        person='person' if inherited_person else person
        subject=f'adult {person}' if inherited_age else f'adult {person}, age {age}'
        if type(age) is not int or not 18<=age<=100: raise ValueError('Adult age required')
        template=json.loads(TEMPLATE.read_text())
        captions={k:v for k,v in template.items() if k.endswith('_caption')}
        for key,value in captions.items():
            value=value.replace('young adult woman, age 25',subject).replace('young adult woman',f'adult {person}').replace('25-year-old adult woman',subject).replace('slim adult female',f'{shape} adult {person}').replace('{{outfit_portrait}}',portrait_clothing).replace('{{outfit}}',outfit_description)
            if person!='woman': value=value.replace('She ','They ').replace(' she ',' they ').replace('Her ','Their ').replace(' her ',' their ')
            value=value.replace('Soft even studio light, natural fabric and skin texture.', 'Natural fabric and skin texture.').replace('Neutral reference photography with soft even studio light.', 'Neutral reference photography.')
            value=value.replace('The two clothed outfit views retain their stockings and high heels;', "The two clothed outfit views retain only the selected outfit's clothing and footwear;")
            captions[key]=value
        if reference_identity:
            # The image is the only source of facial identity. Reconstructed captions
            # are deliberately excluded, including any face-description override.
            appearance=['Match the facial identity of the supplied reference image. Preserve its facial geometry and distinctive features.']
            if inherited_age: appearance.append('Preserve the apparent adult age of the reference.')
            if inherited_person: appearance.append('Preserve the gender presentation of the reference.')
            for key,label in [('hair_style','hairstyle'),('hair_color','hair color'),('expression','expression')]:
                value=c[key]
                appearance.append(f'Preserve the {label} of the reference.' if value=='From face selection' else f'Change only the {label} to: {value}.')
        else:
            face=c['face_description']
            if c['expression']!='From face selection':
                face=' '.join(part for part in re.split(r'(?<=[.!?])\s+',face)
                              if not re.search(r'smil|grin|laugh|frown|parted|teeth',part,re.I))
            hair=c['reference_hair'] if c['hair_style']=='From face selection' else c['hair_style']
            if c['hair_color']!='From face selection':
                hair=re.sub(r'\b(?:dark|light|jet|black|brown|auburn|blond[e]?|silver|gr[ae]y|white|pink|blue|red|chestnut)\b','',hair,flags=re.I)
                hair=f"{c['hair_color']} hair. {hair}"
            appearance=[face,hair]
            if c['expression']!='From face selection': appearance.append(c['expression']+'.')
        captions['portrait_caption']=(f"A straight-on studio headshot of an {subject}. "
            'Head upright and centered, eyes level, shoulders square, looking straight into the lens. '
            +' '.join(appearance)+' '+c['extra_character_details']+' '
            'Show the complete head and hair with clear background above, shoulders and upper chest. '
            'The portrait ends at the upper chest. Upper clothing: '+portrait_clothing+' '+lighting+'.')
        captions['summary_caption']+=' '+lighting+'. '+c['extra_character_details']
        return build_four_view_layout(long_edge,short_edge,privacy_blocks,**captions),long_edge,short_edge
