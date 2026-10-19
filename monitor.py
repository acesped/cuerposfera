#!/usr/bin/env python3
"""CUERPÓSFERA: Reels de divulgación basados en datos revisados.

Python 3.11+, Pillow, requests, ffmpeg/ffprobe, espeak-ng.
Uso: python monitor.py --dry-run | --publish | --check | --list-topics
Los posts se publican por separado: REEL, foto de feed y Story vertical.
No emplea IA para inventar hechos: catálogo curado con fuente, cifra y matices.
Cuenta profesional con Instagram Login; tokens en GitHub Actions Secrets.
Repositorio PUBLICO para servir archivos a Meta desde rama de estado.
"""
from __future__ import annotations
import argparse
import asyncio
import io
import random
import unicodedata
import base64
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
from PIL import Image, ImageDraw, ImageFont

UTC = timezone.utc
BRAND = 'CUERPÓSFERA'
SECRET_NAMES = SECRETS = (
    'X_API_KEY', 'X_API_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_TOKEN_SECRET',
    'GITHUB_TOKEN', 'GH_TOKEN', 'IG_ACCESS_TOKEN', 'INSTAGRAM_TOKEN',
    'GROQ_API_KEY', 'GEMINI_API_KEY', 'OPENROUTER_API_KEY',
)
S = requests.Session()
S.headers.update({'User-Agent': 'Cuerposfera-science-publication/1.0'})

# Cada ficha contiene una cifra verificable, contexto, límites y acción concreta.
# Revisar periódicamente las fichas y sus URLs. No son diagnósticos médicos.
TOPICS = [
    dict(id='azucar', title='¿Cuánta azúcar es demasiada?',
         number='10 %', unit='de la energía diaria',
         hook='EL AZÚCAR TIENE UN LÍMITE',
         fact='La OMS recomienda reducir los azúcares libres a menos del 10 % de las calorías diarias.',
         comparison='En una dieta de 2.000 kcal, ese 10 % equivale a menos de 50 g al día.',
         nuance='Es una referencia para azúcares libres, no para toda la fruta entera. La OMS sugiere menos del 5 % para más beneficios.',
         action='Compara los gramos de azúcar de tu bebida con su etiqueta. Prueba reemplazar una por agua.',
         source='OMS — Healthy diet', source_url='https://www.who.int/news-room/fact-sheets/detail/healthy-diet',
         date_reviewed='2026-10-18', tags='#Azucar #Alimentacion #Bienestar'),
    dict(id='sal', title='La sal que no ves',
         number='< 5 g', unit='de sal por día',
         hook='UNA CUCHARADITA CUENTA',
         fact='La OMS recomienda que los adultos consuman menos de 5 gramos de sal al día.',
         comparison='Son aproximadamente 2 gramos de sodio; gran parte puede provenir de alimentos procesados.',
         nuance='La recomendación es general para adultos; las necesidades individuales deben consultarse con profesionales.',
         action='Mira el sodio por porción en los envases y compara alternativas.',
         source='OMS — Sodium reduction', source_url='https://www.who.int/news-room/fact-sheets/detail/sodium-reduction',
         date_reviewed='2026-10-18', tags='#Sodio #Sal #Habitos'),
    dict(id='movimiento', title='¿Cuánto movimiento necesitas?',
         number='150 min', unit='semanales como mínimo',
         hook='TU SEMANA CABE EN 150 MINUTOS',
         fact='La OMS recomienda a los adultos entre 150 y 300 minutos semanales de actividad física aeróbica moderada.',
         comparison='30 minutos al día durante 5 días suman 150 minutos.',
         nuance='La actividad se adapta a cada persona; algo de actividad suele ser mejor que nada.',
         action='Esta semana agenda 5 caminatas de 30 minutos a un ritmo adecuado para ti.',
         source='OMS — Physical activity', source_url='https://www.who.int/news-room/fact-sheets/detail/physical-activity',
         date_reviewed='2026-10-18', tags='#Movimiento #ActividadFisica #Salud'),
    dict(id='sueno', title='Las horas que tu descanso necesita',
         number='7 h', unit='o más por noche',
         hook='DORMIR NO ES PERDER EL TIEMPO',
         fact='Los CDC indican que los adultos de 18 a 60 años necesitan al menos 7 horas de sueño por noche.',
         comparison='Dormir 5 horas deja 2 horas por debajo de ese mínimo recomendado.',
         nuance='Las necesidades varían según edad y circunstancias; una noche corta no define tu salud.',
         action='Elige una hora regular para acostarte y protege tu tiempo de sueño.',
         source='CDC — About Sleep', source_url='https://www.cdc.gov/sleep/about/index.html',
         date_reviewed='2026-10-18', tags='#Dormir #Sueno #Bienestar'),
    dict(id='azucar_bebidas', title='¿Lees el azúcar de tu bebida?',
         number='4 kcal', unit='por cada gramo de azúcar',
         hook='LO QUE BEBES TAMBIÉN CUENTA',
         fact='Cada gramo de azúcares aporta aproximadamente 4 kilocalorías.',
         comparison='Una bebida que indique 35 g de azúcar aporta cerca de 140 kcal solo de esos azúcares.',
         nuance='35 g es un ejemplo de etiqueta, no una cifra universal para todas las bebidas.',
         action='Lee los gramos de azúcar por envase, no solo por porción.',
         source='USDA — FoodData Central', source_url='https://fdc.nal.usda.gov/',
         date_reviewed='2026-10-18', tags='#Bebidas #Azucar #Datos'),
]


# Fichas adicionales: datos cuantitativos con fuente institucional, sin alarmismo.
def extra_topic(id,title,number,unit,hook,fact,comparison,nuance,action,source,url,tags):
    return dict(id=id,title=title,number=number,unit=unit,hook=hook,fact=fact,
                comparison=comparison,nuance=nuance,action=action,source=source,
                source_url=url,date_reviewed='2026-10-18',tags=tags)

WHO='https://www.who.int/news-room/fact-sheets/detail/healthy-diet'
MOVE='https://www.who.int/news-room/fact-sheets/detail/physical-activity'
SLEEP='https://www.cdc.gov/sleep/about/index.html'
TOPICS += [
    extra_topic('vegetales','¿Cuántas verduras y frutas comes?','400 g','al día, mayores de 10 años','400 GRAMOS PUEDEN CAMBIAR TU PLATO','La OMS recomienda al menos 400 g diarios de frutas y verduras para mayores de 10 años.','Un ejemplo: cuatro porciones de 100 g suman 400 g.','Excluye raíces feculentas de esta recomendación y hay metas diferentes en niños pequeños.','Añade una verdura al almuerzo y una fruta como colación.','OMS — Healthy diet',WHO,'#Frutas #Verduras'),
    extra_topic('fibra','¿Cuánta fibra comes realmente?','25 g','diarios a partir de 10 años','LA FIBRA NO ES INVISIBLE','La OMS aconseja al menos 25 g diarios de fibra alimentaria natural en mayores de 10 años.','Cinco alimentos con 5 g de fibra cada uno sumarían 25 g.','Es una meta poblacional; las necesidades y tolerancia individuales varían.','Incluye legumbres y cereales integrales, incrementando la fibra gradualmente.','OMS — Healthy diet',WHO,'#Fibra #Digestión'),
    extra_topic('grasas_saturadas','¿Cuánta grasa saturada?','10 %','máximo de energía','EL TIPO DE GRASA IMPORTA','La OMS recomienda que las grasas saturadas no superen el 10 % de las calorías totales.','A 2.000 kcal, el 10 % equivale a unas 22 g de grasa saturada.','La cifra no significa eliminar toda la grasa; importa el tipo y el conjunto de la dieta.','Sustituye parte de la mantequilla por aceite vegetal insaturado.','OMS — Healthy diet',WHO,'#Grasas #Corazón'),
    extra_topic('grasas_trans','¿Y las grasas trans?','1 %','máximo de energía','LA ETIQUETA TAMBIÉN HABLA','La OMS recomienda mantener las grasas trans por debajo del 1 % de la energía total.','En 2.000 kcal, equivale a menos de unos 2,2 g de grasas trans al día.','Las grasas trans industriales deben evitarse; no todas las grasas tienen el mismo efecto.','Busca y reduce productos con aceites parcialmente hidrogenados.','OMS — Healthy diet',WHO,'#GrasasTrans #Etiquetas'),
    extra_topic('grasas_totales','¿Cuánta grasa hay en tu día?','30 %','referencia energética','NO TODAS LAS CALORÍAS SON IGUALES','La OMS señala que limitar la grasa total al 30 % o menos de la energía puede ayudar a evitar peso excesivo en adultos.','En un ejemplo de 2.000 kcal, son unas 67 g de grasa.','La calidad de las grasas importa y las necesidades individuales pueden diferir.','Da prioridad a alimentos con grasas insaturadas.','OMS — Healthy diet',WHO,'#Grasas #Nutrición'),
    extra_topic('azucar_optima','El objetivo más exigente para el azúcar','5 %','de energía diaria','¿Y SI BAJAS UN POCO MÁS?','La OMS sugiere reducir los azúcares libres al 5 % o menos de la energía para beneficios adicionales.','En una dieta de 2.000 kcal, equivale a unos 25 g de azúcares libres al día.','Se refiere a azúcares libres, no al azúcar presente naturalmente en fruta entera.','Prueba bebidas sin azúcar añadido y lee etiquetas.','OMS — Healthy diet',WHO,'#Azucar #Etiquetas'),
    extra_topic('sodio','La diferencia entre sodio y sal','2 g','de sodio como referencia','DOS GRAMOS QUE IMPORTAN','La recomendación de menos de 5 g de sal equivale a menos de aproximadamente 2 g de sodio al día.','1 g de sal contiene aproximadamente 400 mg de sodio.','Sodio y sal no son sinónimos; hay que mirar la unidad que muestra la etiqueta.','Compara el sodio entre dos versiones del mismo producto.','OMS — Sodium reduction','https://www.who.int/news-room/fact-sheets/detail/sodium-reduction','#Sodio #Sal'),
    extra_topic('actividad_vigorosa','¿Cuánto ejercicio intenso?','75 min','por semana como mínimo','75 MINUTOS PUEDEN SUMAR','La OMS recomienda como alternativa al ejercicio moderado al menos 75–150 minutos semanales de actividad aeróbica vigorosa para adultos.','Tres sesiones de 25 minutos suman 75 minutos.','La intensidad vigorosa no es apropiada para todas las personas; puede combinarse con actividad moderada.','Elige una intensidad segura y progresa a tu ritmo.','OMS — Physical activity',MOVE,'#Ejercicio #Movimiento'),
    extra_topic('actividad_extra','Más movimiento, más oportunidades','300 min','de actividad moderada','¿Y SI TU SEMANA SE MUEVE MÁS?','La OMS indica un rango de 150 a 300 minutos semanales de actividad aeróbica moderada para adultos.','60 minutos durante cinco días suman 300 minutos.','No es una obligación diaria; pequeñas cantidades también aportan beneficios.','Si ya caminas 30 minutos, prueba añadir 10 cuando puedas.','OMS — Physical activity',MOVE,'#Movimiento #Bienestar'),
    extra_topic('musculos','¿Entrenas tus músculos?','2 días','por semana','TU FUERZA TAMBIÉN CUENTA','La OMS recomienda a los adultos hacer actividades de fortalecimiento muscular al menos dos días a la semana.','Martes y viernes pueden ser tus dos jornadas de fuerza.','Adapta los ejercicios a tu capacidad y condiciones.','Haz una rutina breve de fuerza con técnica adecuada.','OMS — Physical activity',MOVE,'#Fuerza #ActividadFisica'),
    extra_topic('sueno_adolescente','Los adolescentes también necesitan dormir','8–10 h','por noche','DORMIR TAMBIÉN ES CRECER','Los CDC recomiendan de 8 a 10 horas diarias de sueño entre los 13 y 17 años.','Dormir 7 horas está una hora por debajo del límite inferior.','No aplica a adultos ni a niños más pequeños; la calidad del sueño también importa.','Reduce pantallas antes de acostarte y protege una rutina estable.','CDC — About Sleep',SLEEP,'#Sueño #Adolescencia'),
    extra_topic('sueno_escolar','El descanso en edad escolar','9–12 h','por noche','SU DÍA EMPIEZA LA NOCHE ANTERIOR','Los CDC recomiendan entre 9 y 12 horas de sueño a niños de 6 a 12 años.','Ocho horas quedan una hora por debajo del mínimo.','Las necesidades dependen de la edad y no se extrapolan a adultos.','Ayuda a mantener horarios de descanso regulares.','CDC — About Sleep',SLEEP,'#Niños #Sueño'),
    extra_topic('sueno_mayores','Descanso después de los 65','7–8 h','por noche','LA EDAD CAMBIA TUS NECESIDADES','Los CDC señalan entre 7 y 8 horas de sueño para personas de 65 años o más.','Se trata de un intervalo orientativo de dos horas, de 7 a 8.','Las enfermedades y medicamentos pueden afectar el descanso y requieren valoración profesional.','Consulta si el insomnio o la somnolencia diurna persisten.','CDC — About Sleep',SLEEP,'#Sueño #Bienestar'),
    extra_topic('carbohidratos','¿Todos los carbohidratos son iguales?','45–75 %','de energía como rango general','HAY MÁS QUE AZÚCAR','La OMS describe un rango general aproximado del 45 al 75 % de energía procedente de carbohidratos en muchas dietas.','En 2.000 kcal, el 45 % representa 900 kcal.','La cantidad puede variar mucho; prioriza cereales integrales, frutas, verduras y legumbres.','Sustituye un cereal refinado por una opción integral.','OMS — Healthy diet',WHO,'#Carbohidratos #Alimentación'),
    extra_topic('sueno_dato','¿Cuántos adultos duermen poco?','30,5 %','de adultos de EE. UU. en 2024','CASI UNO DE CADA TRES','Una encuesta de los CDC estimó que el 30,5 % de adultos estadounidenses durmió menos de 7 horas en promedio en 2024.','Es aproximadamente 3 de cada 10 adultos encuestados.','Es una estimación de Estados Unidos, no una tasa mundial ni una predicción individual.','Revisa tu horario de sueño y busca consistencia.','CDC — NCHS Data Brief 559','https://www.cdc.gov/nchs/products/databriefs/db559.htm','#Sueño #Estadística'),
]

MUSIC_PAGE = 'https://commons.wikimedia.org/wiki/File:Promise.ogg'
MUSIC_URL = 'https://commons.wikimedia.org/wiki/Special:Redirect/file/Promise.ogg'


def now(): return datetime.now(UTC).isoformat()
def log(*parts): print(now(), *parts, flush=True)
def envbool(name, default=False):
    v=os.getenv(name, str(default)).strip().lower()
    if v not in ('1','0','true','false','yes','no'): raise ValueError('Booleano inválido: '+name)
    return v in ('1','true','yes')

def redact(text):
    text=str(text)
    for name in SECRET_NAMES:
        secret=os.getenv(name,'')
        if secret: text=text.replace(secret,'[REDACTADO]')
    return text[:900]

def write_json(path, data):
    path=Path(path);path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as h:
        tmp=h.name;json.dump(data,h,ensure_ascii=False,indent=2);h.flush();os.fsync(h.fileno())
    os.replace(tmp,path)

@dataclass
class Config:
    repo:str
    token:str
    branch:str
    uid:str
    ig_token:str
    username:str
    graph_version:str
    output:Path
    audio:bool
    public_feed:bool
    public_story:bool

    @classmethod
    def load(cls):
        version=os.getenv('IG_GRAPH_VERSION','v25.0')
        if not re.fullmatch(r'v\d+\.\d+',version):raise ValueError('IG_GRAPH_VERSION inválida')
        return cls(
            repo=os.getenv('GITHUB_REPOSITORY','').strip(),
            token=(os.getenv('GH_TOKEN') or os.getenv('GITHUB_TOKEN') or '').strip(),
            branch=os.getenv('STATE_BRANCH','cuerposfera-state').strip(),
            uid=(os.getenv('IG_USER_ID') or os.getenv('INSTAGRAM_USER_ID') or '').strip(),
            ig_token=(os.getenv('IG_ACCESS_TOKEN') or os.getenv('INSTAGRAM_TOKEN') or '').strip(),
            username=os.getenv('IG_EXPECTED_USERNAME','cuerposfera').strip().lstrip('@').lower(),
            graph_version=version,
            output=Path(os.getenv('OUTPUT_DIR','output')),
            audio=envbool('ENABLE_MUSIC',True),
            public_feed=envbool('PUBLISH_FEED',True),
            public_story=envbool('PUBLISH_STORY',True),
        )


def check_topic(t):
    for f in ('id','title','number','unit','hook','fact','comparison','nuance','action','source','source_url','date_reviewed'):
        if not t.get(f) or not isinstance(t[f],str):raise ValueError('Ficha incompleta: '+str(f))
    u=urlparse(t['source_url'])
    if u.scheme!='https' or not u.netloc:raise ValueError('Fuente sin HTTPS')
    if not re.search(r'\d',t['number']):raise ValueError('Ficha sin dato cuantitativo')
    if len(t['fact'])>350 or len(t['action'])>200:raise ValueError('Texto demasiado extenso')
    return t


def cmd(args, timeout=90):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise RuntimeError(f'{args[0]} falló: {redact(p.stderr[-350:])}')
    return p.stdout
    return p.stdout


def font(size,bold=False):
    names=(['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'] if bold
           else ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'])
    for n in names:
        if Path(n).exists():return ImageFont.truetype(n,size)
    return ImageFont.load_default()


def gradient(w=720,h=1280):
    im=Image.new('RGB',(w,h)); d=ImageDraw.Draw(im)
    for y in range(h):
        r=y/h
        d.line((0,y,w,y),fill=(int(7+13*r),int(23+12*r),int(40+25*r)))
    return im


def fit_lines(draw,text,maxwidth,fnt):
    lines=[];cur=''
    for word in text.split():
        probe=(cur+' '+word).strip()
        if cur and draw.textbbox((0,0),probe,font=fnt)[2]>maxwidth:
            lines.append(cur);cur=word
        else:cur=probe
    if cur:lines.append(cur)
    return lines


def centered(draw,text,y,fnt,fill,limit=640,spacing=14):
    for line in fit_lines(draw,text,limit,fnt):
        bb=draw.textbbox((0,0),line,font=fnt)
        draw.text(((720-(bb[2]-bb[0]))/2,y),line,font=fnt,fill=fill)
        y+=bb[3]-bb[1]+spacing
    return y


IMAGE_HEADERS={'User-Agent':'CuerposferaEducationalBot/1.0 (educational content; github.com)', 'Accept':'application/json'}

def _photo_query(t):
    tid=t['id']
    if any(x in tid for x in ('azucar','gaseosa','bebida')):return 'soft drinks sugar food'
    if any(x in tid for x in ('sal','sodio')):return 'salt food nutrition'
    if any(x in tid for x in ('sueno','descanso')):return 'sleep bedroom person'
    if any(x in tid for x in ('actividad','movimiento','ejercicio')):return 'walking exercise person'
    return 'healthy foods vegetables water wellness'

def _commons_photos(query):
    url='https://commons.wikimedia.org/w/api.php'
    r=requests.get(url,headers=IMAGE_HEADERS,params={'action':'query','format':'json','generator':'search',
          'gsrsearch':'filetype:bitmap '+query,'gsrnamespace':6,'gsrlimit':12,'prop':'imageinfo',
          'iiprop':'url|extmetadata','iiurlwidth':850},timeout=25)
    r.raise_for_status()
    for page in r.json().get('query',{}).get('pages',{}).values():
        info=(page.get('imageinfo') or [{}])[0];meta=info.get('extmetadata',{})
        license=str((meta.get('LicenseShortName') or {}).get('value','')).lower().replace(' ','')
        if not ('cc0' in license or license.startswith('pd-') or license in ('pdm','publicdomain','pd')):continue
        uri=info.get('thumburl') or info.get('url')
        if uri:yield uri,{'title':page.get('title'),'license':license,'source':info.get('descriptionurl')}

def _openverse_photos(query):
    r=requests.get('https://api.openverse.org/v1/images/',headers=IMAGE_HEADERS,
       params={'q':query,'license':'cc0,pdm','page_size':12},timeout=25)
    r.raise_for_status()
    for row in r.json().get('results',[]):
        if str(row.get('license','')).lower() in ('cc0','pdm'):
            uri=row.get('url') or row.get('thumbnail')
            if uri:yield uri,{'title':row.get('title'),'license':row.get('license'),'source':row.get('foreign_landing_url')}

def prepare_photos(t,folder):
    """CC0/PD exclusivamente; si fallan, fondos animados locales."""
    from urllib.parse import urlparse
    import socket,ipaddress
    files=[];credits=[]
    for provider in (_commons_photos,_openverse_photos):
        try:
            for uri,meta in provider(_photo_query(t)):
                if len(files)>=5:break
                u=urlparse(uri)
                if u.scheme!='https' or not u.hostname:continue
                # Descargas de proveedores: no permitir host privado, ni redirects arbitrarios.
                try:
                    addresses=socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM)
                    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):continue
                except (socket.gaierror,ValueError):continue
                try:
                    with requests.get(uri,timeout=25,stream=True,allow_redirects=False) as r:
                        if r.status_code!=200 or not r.headers.get('Content-Type','').lower().startswith('image/'):continue
                        body=bytearray()
                        for chunk in r.iter_content(65536):
                            body.extend(chunk)
                            if len(body)>8_000_000:break
                    if len(body)>8_000_000:continue
                    from PIL import ImageOps
                    with Image.open(io.BytesIO(body)) as raw:
                        if min(raw.size)<420:continue
                        dst=folder/f'photo_{len(files)}.jpg'
                        ImageOps.fit(raw.convert('RGB'),(720,1280)).save(dst,quality=84)
                        files.append(dst);credits.append(meta)
                except (requests.RequestException,OSError,ValueError):continue
            if len(files)>=5:break
        except (requests.RequestException,KeyError,ValueError) as exc:
            log('Fotos:',provider.__name__,'no disponible:',type(exc).__name__)
    write_json(folder/'creditos_imagenes.json',credits)
    return files

def slide(text,subtitle,label,idx,folder,number=None,photo=None):
    if photo:
        from PIL import ImageEnhance
        im=ImageEnhance.Brightness(Image.open(photo).convert('RGB')).enhance(.28)
    else:im=gradient()
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((42,54,678,118),radius=25,fill=(15,68,80),outline=(54,155,157),width=2)
    centered(d,'CUERPÓSFERA',68,font(30,True),(199,250,240))
    d.ellipse((240,170,480,410),fill=(18,62,80),outline=(47,177,170),width=5)
    d.ellipse((300,230,420,350),fill=(31,144,148))
    d.arc((269,198,450,380),45,260,fill=(153,233,207),width=8)
    if number:
        centered(d,number,445,font(89,True),(105,240,204))
        centered(d,label,562,font(25,True),(155,208,219))
        base=665
    else:base=475
    base=centered(d,text,base,font(44,True),(250,251,255),630,18)
    base+=44
    centered(d,subtitle,base,font(26),(199,220,230),620,12)
    d.rectangle((60,1175,660,1178),fill=(50,152,160))
    centered(d,'DATOS REALES  •  HÁBITOS CONSCIENTES',1200,font(21),(165,208,215))
    out=folder/f'slide_{idx:02}.png';im.save(out);return out


def script_lines(t):
    return [
        (t['hook'], '¿Sabías que tus hábitos tienen cifras que casi nunca miramos?'),
        (t['number']+' '+t['unit'],t['fact']),
        ('PONLO EN PERSPECTIVA',t['comparison']),
        ('EL CONTEXTO IMPORTA',t['nuance']),
        ('UNA DECISIÓN HOY',t['action']),
    ]


def music(folder):
    if not envbool('ENABLE_MUSIC',True):return None
    url=os.getenv('REEL_MUSIC_URL',MUSIC_URL)
    host=urlparse(url)
    if host.scheme!='https' or host.hostname not in ('commons.wikimedia.org','upload.wikimedia.org'):
        raise ValueError('REEL_MUSIC_URL debe alojarse en Wikimedia Commons')
    dest=folder/'music.ogg'
    try:
        with S.get(url,timeout=35,stream=True) as r:
            r.raise_for_status();n=0
            with dest.open('wb') as out:
                for ch in r.iter_content(65536):
                    n+=len(ch)
                    if n>12_000_000:raise ValueError('Audio excede 12 MB')
                    out.write(ch)
        info=json.loads(cmd(['ffprobe','-v','error','-show_streams','-of','json',str(dest)],20))
        if not any(s.get('codec_type')=='audio' for s in info.get('streams',[])):raise ValueError('No es audio')
        return dest
    except (requests.RequestException,ValueError,RuntimeError,OSError) as exc:
        log('Música no disponible; se usará silencio:',redact(exc));dest.unlink(missing_ok=True);return None


def narration(text,folder):
    out=folder/'voice.mp3'
    async def speak():
        import edge_tts
        await edge_tts.Communicate(text,voice=os.getenv('CUERPO_VOICE','es-ES-AlvaroNeural'),rate='+25%').save(str(out))
    try:
        asyncio.run(speak())
        if out.stat().st_size<1000:raise RuntimeError('Audio TTS vacío')
        return out
    except Exception as exc:
        if envbool('REQUIRE_VOICE',False):raise RuntimeError('Voz necesaria: '+type(exc).__name__) from None
        log('TTS no disponible; usar texto y música:',type(exc).__name__)
        return None


def create_video(t,folder):
    folder.mkdir(parents=True,exist_ok=True)
    lines=script_lines(t)
    photos=prepare_photos(t,folder) if envbool('ENABLE_PHOTOS',True) else []
    for idx,(a,b) in enumerate(lines):
        slide(a,b,t['unit'],idx,folder,number=t['number'] if idx==1 else None,
              photo=photos[idx%len(photos)] if photos else None)
    cover=Image.open(folder/'slide_01.png').convert('RGB')
    cover.save(folder/'feed.jpg',quality=90,optimize=True)
    # Cinco escenas de 6 segundos = 30s, vertical 720x1280, 30 fps.
    listing=folder/'slides.txt'
    listing.write_text(''.join(f"file '{(folder/f'slide_{i:02}.png').resolve()}'\nduration 6\n" for i in range(5))+
                       f"file '{(folder/'slide_04.png').resolve()}'\n",encoding='utf-8')
    background=folder/'silent.mp4'
    cmd(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),
         '-t','30','-vf','fps=30,format=yuv420p','-c:v','libx264','-preset','veryfast','-crf','24',
         '-movflags','+faststart',str(background)],180)
    voice=narration(' '.join(b for _,b in lines),folder)
    track=music(folder)
    final=folder/'reel.mp4'
    args=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(background)]
    filters=[];inputs=[]
    if voice:
        args+=['-i',str(voice)];inputs.append(f'[{len(inputs)+1}:a]volume=1.7,aresample=48000[v]')
    if track:
        args+=['-stream_loop','-1','-i',str(track)]
        idx=1 if not voice else 2
        filters.append(f'[{idx}:a]volume=0.13,aresample=48000[m]')
    if voice:filters.append(inputs[0])
    if voice and track:filters.append('[m][v]amix=inputs=2:duration=longest:dropout_transition=0[a]')
    elif track:filters.append('[m]anull[a]')
    elif voice:filters.append('[v]anull[a]')
    else:
        args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
        filters.append('[1:a]anull[a]')
    args+=['-filter_complex',';'.join(filters),'-map','0:v:0','-map','[a]',
           '-c:v','copy','-c:a','aac','-b:a','128k','-ar','48000','-ac','2','-t','30',
           '-movflags','+faststart',str(final)]
    cmd(args,150)
    info=json.loads(cmd(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(final)],20))
    types={s['codec_type']:s for s in info.get('streams',[])}
    if (types.get('video',{}).get('codec_name')!='h264' or
        types.get('audio',{}).get('codec_name')!='aac' or
        types['video'].get('width')!=720 or types['video'].get('height')!=1280):
        raise RuntimeError('Video incompatible con Instagram')
    if final.stat().st_size>45_000_000:raise RuntimeError('MP4 supera 45 MB')
    # Reutilizar el video vertical como Story, manteniendo ID de publicación propio.
    return final,folder/'feed.jpg',final


def caption(t):
    return (f"{t['title']}\n\n📊 {t['number']} {t['unit']}\n\n"
            f"{t['fact']}\n\n{t['comparison']}\n\n"
            f"Importante: {t['nuance']}\n\n"
            f"✅ Pruébalo: {t['action']}\n\n"
            f"Fuente: {t['source']}\n{t['source_url']}\n"
            f"Información educativa; no sustituye asesoramiento individual.\n\n"
            f"#Cuerposfera {t.get('tags','')}")[:2200]


class GitHub:
    def __init__(self,c):
        if not c.repo or not re.fullmatch(r'[\w.-]+/[\w.-]+',c.repo):raise ValueError('GITHUB_REPOSITORY inválido')
        if not c.token:raise ValueError('GITHUB_TOKEN ausente')
        self.c=c;self.base='https://api.github.com/repos/'+c.repo
        self.head={'Authorization':'Bearer '+c.token,'Accept':'application/vnd.github+json',
                   'X-GitHub-Api-Version':'2022-11-28'}
    def req(self,method,path,**kw):
        try:return S.request(method,self.base+path,headers=self.head,timeout=40,**kw)
        except requests.RequestException as exc:raise RuntimeError('GitHub: '+type(exc).__name__) from None
    def ensure(self):
        info=self.req('GET','')
        if info.status_code!=200:raise RuntimeError('GitHub repo inaccesible '+str(info.status_code))
        if info.json().get('private') is not False:raise RuntimeError('Meta requiere multimedia accesible por URL pública; repositorio privado no admitido')
        ref=self.req('GET','/git/ref/heads/'+quote(self.c.branch,safe=''))
        if ref.status_code==200:return
        if ref.status_code!=404:raise RuntimeError('GitHub branch HTTP '+str(ref.status_code))
        main=info.json()['default_branch']
        root=self.req('GET','/git/ref/heads/'+quote(main,safe=''))
        if root.status_code!=200:raise RuntimeError('No se encuentra rama principal')
        made=self.req('POST','/git/refs',json={'ref':'refs/heads/'+self.c.branch,'sha':root.json()['object']['sha']})
        if made.status_code!=201:raise RuntimeError('No se creó rama de estado; HTTP '+str(made.status_code))
    def get_file(self,path):
        r=self.req('GET','/contents/'+path,params={'ref':self.c.branch})
        if r.status_code==404:return None,None
        if r.status_code!=200:raise RuntimeError('GitHub GET '+path+' HTTP '+str(r.status_code))
        b=r.json();blob=b.get('content')
        if b.get('encoding')!='base64' or blob is None:
            raise RuntimeError('GitHub no devolvió contenido pequeño para '+path)
        return base64.b64decode(blob),b['sha']
    def put(self,path,data,sha=None):
        body={'message':'cuerposfera content [skip ci]','branch':self.c.branch,'content':base64.b64encode(data).decode()}
        if sha:body['sha']=sha
        r=self.req('PUT','/contents/'+path,json=body)
        if r.status_code not in (200,201):raise RuntimeError('GitHub PUT '+path+' HTTP '+str(r.status_code)+'; NO reintentar automáticamente')
        response=r.json()
        commit=response['commit']['sha'];blob=response['content']['sha']
        if not re.fullmatch('[a-f0-9]{40,64}',commit):raise RuntimeError('Commit sin confirmar')
        return commit,blob
    def state(self):
        raw,sha=self.get_file('state/status.json')
        if raw is None:return {'schema':1,'account':None,'episodes':{}},None
        obj=json.loads(raw)
        if obj.get('schema')!=1 or not isinstance(obj.get('episodes'),dict):raise RuntimeError('Estado corrupto')
        return obj,sha
    def save(self,state,sha):
        state['updated']=now()
        raw=json.dumps(state,ensure_ascii=False,indent=2).encode('utf-8')
        commit,blob=self.put('state/status.json',raw,sha)
        # Confirmación contra commit inmutable para evitar reenvíos ante fallos ambiguos.
        r=self.req('GET','/contents/state/status.json',params={'ref':commit})
        if r.status_code!=200:raise RuntimeError('No se confirmó estado; detener publicaciones')
        b=r.json()
        if b.get('sha')!=blob or base64.b64decode(b.get('content',''))!=raw:
            raise RuntimeError('Estado remoto difiere; detener publicaciones')
        return blob
    def media(self,episode,path):
        raw=Path(path).read_bytes()
        if len(raw)>45_000_000:raise RuntimeError('Archivo excede límite de seguridad 45 MB')
        digest=hashlib.sha256(raw).hexdigest();dst=f'media/{episode}/{digest[:24]}{Path(path).suffix}'
        meta=self.req('GET','/contents/'+dst,params={'ref':self.c.branch})
        if meta.status_code==404:
            commit,_=self.put(dst,raw)
        elif meta.status_code==200:
            # URL por commit, verificando siempre el contenido real que Meta descargará.
            head=self.req('GET','/git/ref/heads/'+quote(self.c.branch,safe=''))
            if head.status_code!=200:raise RuntimeError('No se puede resolver commit de media')
            commit=head.json()['object']['sha']
        else:raise RuntimeError('Consulta multimedia HTTP '+str(meta.status_code))
        url=f'https://raw.githubusercontent.com/{self.c.repo}/{commit}/{dst}'
        for i in range(6):
            try:
                with S.get(url,timeout=35,stream=True) as r:
                    if r.status_code==200:
                        hh=hashlib.sha256();n=0
                        for chunk in r.iter_content(65536):
                            n+=len(chunk)
                            if n>len(raw):break
                            hh.update(chunk)
                        if n==len(raw) and hh.hexdigest()==digest:return url
            except requests.RequestException:pass
            time.sleep(2+i)
        raise RuntimeError('Multimedia GitHub no accesible/verificable para Meta')


class Instagram:
    def __init__(self,c):
        if not c.ig_token or not c.uid.isdigit():raise RuntimeError('Faltan IG_ACCESS_TOKEN/INSTAGRAM_TOKEN e IG_USER_ID/INSTAGRAM_USER_ID')
        self.c=c;self.url=f'https://graph.instagram.com/{c.graph_version}'
        self.headers={'Authorization':'Bearer '+c.ig_token}
    def req(self,method,path,uncertain=False,**kwargs):
        try:
            r=S.request(method,self.url+path,headers=self.headers,timeout=40,allow_redirects=False,**kwargs)
        except requests.RequestException as exc:
            raise RuntimeError(('RESULTADO INCIERTO: ' if uncertain else '')+'Meta '+type(exc).__name__) from None
        try: b=r.json()
        except ValueError:b={}
        if not 200<=r.status_code<300 or (isinstance(b,dict) and b.get('error')):
            e=b.get('error',{}) if isinstance(b,dict) else {}
            msg={k:e.get(k) for k in ('message','type','code','error_subcode','fbtrace_id') if e.get(k) is not None}
            raise RuntimeError(('RESULTADO INCIERTO: ' if uncertain else '')+f'Meta HTTP {r.status_code} {path} '+redact(json.dumps(msg,ensure_ascii=False)))
        if not isinstance(b,dict):raise RuntimeError(('RESULTADO INCIERTO: ' if uncertain else '')+'Meta JSON inválido')
        return b
    def identity(self):
        """Comprueba identidad por usuario en /me y por ID publicador.

        Meta puede devolver identificadores distintos para la misma cuenta.
        El ID configurado debe ser consultable y ser el mismo que devuelve
        GET /{uid}, pero no se exige que sea idéntico a GET /me.id.
        No se realiza ninguna publicación en esta comprobación.
        """
        expected=self.c.username.strip().lstrip('@').casefold()
        me=self.req('GET','/me',params={'fields':'id,username'})
        account=self.req('GET','/'+self.c.uid,params={'fields':'id,username'})
        authorized=str(me.get('username') or '').strip().lstrip('@').casefold()
        resolved=str(account.get('username') or '').strip().lstrip('@').casefold()
        resolved_id=str(account.get('id') or '').strip()
        print('CUENTA AUTORIZADA: @'+(authorized or '(no recibida)'),flush=True)
        print('CUENTA ESPERADA: @'+expected,flush=True)
        print('CUENTA DEL ID CONFIGURADO: @'+(resolved or '(no recibida)'),flush=True)
        print('ID SECRET CONSULTABLE:',resolved_id==self.c.uid,flush=True)
        if not expected or authorized!=expected or resolved!=expected or resolved_id!=self.c.uid:
            raise RuntimeError('Cuenta Instagram no coincide con @'+expected+
                               ' o el ID configurado no se puede validar')
        if str(me.get('id') or '')!=self.c.uid:
            print('NOTA: /me.id y el ID de publicación son distintos; '
                  'ambos resuelven al usuario esperado.',flush=True)
        return account
    def create(self,url,caption_text,kind):
        params={'caption':caption_text}
        if kind=='reel':params.update(media_type='REELS',video_url=url,share_to_feed='false')
        elif kind=='story':params={'media_type':'STORIES','video_url':url}
        elif kind=='feed':params['image_url']=url
        else:raise ValueError('Tipo de publicación no admitido: '+str(kind))
        b=self.req('POST','/'+self.c.uid+'/media',data=params)
        cid=str(b.get('id',''))
        if not cid.isdigit():raise RuntimeError('Meta no devolvió container ID')
        return cid
    def ready(self,cid):
        for i in range(36):
            b=self.req('GET','/'+cid,params={'fields':'status_code,status'})
            st=b.get('status_code')
            if st=='FINISHED':return
            if st in ('ERROR','EXPIRED','PUBLISHED'):raise RuntimeError('Contenedor IG '+str(st))
            if st not in ('IN_PROGRESS','PROCESSING','PENDING'):raise RuntimeError('Estado IG desconocido: '+str(st))
            time.sleep(5)
        raise RuntimeError('Contenedor sigue procesándose; intentar en próxima ejecución')
    def publish(self,cid):
        # Desde este POST, cualquier fallo es ambiguo: nunca reintentar automáticamente.
        b=self.req('POST','/'+self.c.uid+'/media_publish',uncertain=True,data={'creation_id':cid})
        media_id=str(b.get('id',''))
        if not media_id.isdigit():raise RuntimeError('RESULTADO INCIERTO: Meta no confirmó media ID')
        return media_id


def publish_piece(gh,ig,state,sha,episode,kind,url,text):
    entry=state['episodes'][episode];item=entry.setdefault(kind,{'status':'pending'})
    if item['status']=='published':return sha
    if item['status'] in ('uncertain','publishing'):
        log('BLOQUEADO: resultado incierto en',kind,'— revisión manual obligatoria');return sha
    if item['status'] not in ('pending','container'):
        raise RuntimeError('Estado inesperado '+str(item['status']))
    if not item.get('container_id'):
        cid=ig.create(url,text,kind)
        item.update(status='container',container_id=cid,updated=now());sha=gh.save(state,sha)
    cid=item['container_id']
    ig.ready(cid)
    item.update(status='publishing',updated=now());sha=gh.save(state,sha)
    try:mid=ig.publish(cid)
    except Exception as exc:
        item.update(status='uncertain',error=redact(exc),updated=now())
        sha=gh.save(state,sha)
        raise
    item.update(status='published',media_id=mid,error='',updated=now());sha=gh.save(state,sha)
    log(kind,'publicado, ID:',mid)
    return sha



# Igual que AERO_DATOS: descubrimiento de modelos y fallback Groq/Gemini/OpenRouter.
GROQ_URL='https://api.groq.com/openai/v1/chat/completions'
GEMINI_MODELS='https://generativelanguage.googleapis.com/v1beta/models'
OPENROUTER_URL='https://openrouter.ai/api/v1/chat/completions'

ANGLES=(
 '¿Cómo se interpreta este número?', '¿Qué diferencia hay entre recomendación y límite?',
 '¿Por qué importa repetir este hábito?', '¿Qué nos dice la etiqueta?',
 '¿Qué error se repite al interpretar este dato?', '¿Qué puedes cambiar esta semana?',
 '¿Qué significa esta cifra en la vida diaria?', '¿Cómo comparar dos alternativas?',
 '¿Qué detalle suele pasar inadvertido?', '¿Qué cambia según las necesidades individuales?',
 '¿Qué es mito y qué es dato?', '¿Qué significa la recomendación en términos prácticos?',
 '¿Cuál es una acción pequeña y útil?', '¿Qué deberías preguntar antes de consumir?',
 '¿Qué representa este porcentaje?', '¿Cómo evitar conclusiones exageradas?',
 '¿Qué es mejor observar durante una semana?', '¿Qué comparación ayuda a entenderlo?',
 '¿Qué pregunta conviene hacer en el supermercado?', '¿Qué ejemplo se puede calcular?',
 '¿Por qué una sola ocasión no define tu salud?', '¿Qué dato conviene compartir?',
 '¿Cómo se aplica a la rutina cotidiana?', '¿Qué matiz científico no debemos olvidar?',
 '¿Qué decisión sencilla puedes tomar hoy?',
)

def catalog():
    """500 propuestas (20 fichas * 25 enfoques). No son 500 hechos diferentes."""
    if len(TOPICS)!=20:raise RuntimeError('Se esperaban 20 fichas científicas')
    return [dict(id=f'CS-{i*25+j+1:03d}',category=t['title'],
                 title=f'{q} — {t["title"]}',topic_id=t['id'],
                 image_query=t['title'],lesson=t['fact'],source=t['source_url'],
                 angle=q) for i,t in enumerate(TOPICS) for j,q in enumerate(ANGLES)]

def _model_list(provider,key):
    if provider=='groq':
        r=requests.get('https://api.groq.com/openai/v1/models',headers={'Authorization':'Bearer '+key},timeout=25)
        r.raise_for_status();names={x['id'] for x in r.json().get('data',[]) if isinstance(x,dict) and 'id' in x}
        preferred=['llama-3.3-70b-versatile','llama-3.1-8b-instant','openai/gpt-oss-20b']
        configured=os.getenv('GROQ_MODEL','')
        return ([configured] if configured and configured in names else [])+[m for m in preferred if m in names and m!=configured]
    if provider=='gemini':
        r=requests.get(GEMINI_MODELS,headers={'x-goog-api-key':key},params={'pageSize':100},timeout=25)
        r.raise_for_status();names={x.get('name','').removeprefix('models/') for x in r.json().get('models',[]) if 'generateContent' in x.get('supportedGenerationMethods',[])}
        configured=os.getenv('GEMINI_MODEL','').removeprefix('models/')
        preferred=['gemini-2.5-flash-lite','gemini-2.5-flash','gemini-2.0-flash']
        return ([configured] if configured and configured in names else [])+[m for m in preferred if m in names and m!=configured]
    r=requests.get('https://openrouter.ai/api/v1/models',headers={'Authorization':'Bearer '+key},timeout=25)
    r.raise_for_status();options=[]
    for x in r.json().get('data',[]):
        name=x.get('id','');price=x.get('pricing') or {}
        try:free=float(price.get('prompt',1))==0 and float(price.get('completion',1))==0
        except (ValueError,TypeError):free=False
        if name.endswith(':free') and free and int(x.get('context_length') or 0)>=4000:
            options.append(name)
    chosen=os.getenv('OPENROUTER_MODEL','openrouter/free')
    if chosen!='openrouter/free' and not chosen.endswith(':free'):raise ValueError('OpenRouter solo modelos :free')
    return ([chosen] if chosen in options else [])+[m for m in options if m!=chosen][:4]

def _ai_candidates():
    candidates=[]
    for provider,name in [('groq','GROQ_API_KEY'),('gemini','GEMINI_API_KEY'),('openrouter','OPENROUTER_API_KEY')]:
        key=os.getenv(name,'').strip()
        if not key:continue
        try:
            candidates.extend((provider,model,key) for model in _model_list(provider,key)[:4])
        except (requests.RequestException,ValueError,KeyError) as exc:
            log('Modelo no disponible:',provider,type(exc).__name__)
    if not candidates:raise RuntimeError('Configura GROQ_API_KEY, GEMINI_API_KEY u OPENROUTER_API_KEY y comprueba la cuota/modelos')
    return candidates

def _provider_text(provider,model,key,prompt):
    if provider=='gemini':
        r=requests.post(f'{GEMINI_MODELS}/{model}:generateContent',headers={'x-goog-api-key':key},
          json={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'maxOutputTokens':550,'temperature':0.45}},timeout=95)
        r.raise_for_status()
        return '\n'.join(part.get('text','') for c in r.json().get('candidates',[])
                         for part in c.get('content',{}).get('parts',[]) if isinstance(part,dict))
    url=GROQ_URL if provider=='groq' else OPENROUTER_URL
    headers={'Authorization':'Bearer '+key}
    if provider=='openrouter':headers.update({'HTTP-Referer':'https://github.com','X-Title':'Cuerposfera'})
    r=requests.post(url,headers=headers,json={'model':model,'messages':[
      {'role':'system','content':'Eres redactor de divulgación científica. Solo el formato pedido, en español.'},
      {'role':'user','content':prompt}], 'temperature':0.4,'max_tokens':650},timeout=95)
    r.raise_for_status();answer=r.json().get('choices',[{}])[0].get('message',{}).get('content','')
    if isinstance(answer,list):answer=''.join(x.get('text','') for x in answer if isinstance(x,dict))
    return str(answer)

def _normalize(s):
    return ''.join(c for c in unicodedata.normalize('NFKD',s.casefold()) if not unicodedata.combining(c)).strip()

def _candidate_hook(raw):
    raw=raw.strip()
    try:
        data=json.loads(raw.strip('`').removeprefix('json').strip());v=data.get('hook','')
    except (json.JSONDecodeError,AttributeError):
        hit=re.search(r'^\s*(?:GANCHO|HOOK)\s*:\s*(.*?)\s*$',raw,re.I|re.M)
        v=hit.group(1) if hit else raw.splitlines()[0] if raw else ''
    v=re.sub(r'\s+',' ',str(v)).strip(' "“”')
    if not 12<=len(v)<=65 or re.search(r'\d',v):raise ValueError('Gancho inválido o contiene número no aprobado')
    if any(k in _normalize(v) for k in ('cura','garantiz','muerte segura','veneno','toxina mortal')):raise ValueError('Gancho alarmista')
    return v

def creative_episode(fact,state,angle=''):
    used={_normalize(x.get('hook','')) for x in state.get('episodes',{}).values() if x.get('topic_id')==fact['id']}
    prompt=(f'MARCA: CUERPÓSFERA. Tema: {fact["title"]}. Enfoque: {angle}. '
      f'Dato científico aprobado, NO modificar: {fact["fact"]} '
      f'Contexto aprobado: {fact["nuance"]}. '
      'Genera SOLO una frase GANCHO: de 12 a 65 caracteres, intrigante, sin números, '
      'sin otras afirmaciones científicas, sin diagnósticos ni alarmismo. '
      'No repitas frases previas: '+repr(list(used)[-30:])+'. Responde GANCHO: ...')
    last=''
    for provider,model,key in _ai_candidates():
        try:
            hook=_candidate_hook(_provider_text(provider,model,key,prompt))
            if _normalize(hook) in used:raise ValueError('Gancho duplicado')
            result=dict(fact);result['hook']=hook;result['ai_model']=provider+':'+model
            return result
        except (requests.RequestException,ValueError,KeyError,IndexError,TypeError) as exc:
            last=f'{provider}/{model}: {type(exc).__name__}';log('IA no usable:',last)
    raise RuntimeError('No se obtuvo gancho válido; NO publicar. '+last)

def pick_fact(state):
    """Rotate the least-covered scientific topic, not the same fixed episode."""
    counts={t['id']:0 for t in TOPICS}
    for entry in state['episodes'].values():
        if entry.get('topic_id') in counts:counts[entry['topic_id']]+=1
    return min(TOPICS,key=lambda t:(counts[t['id']],t['id']))


def next_episode(fact,state):
    variant=creative_episode(fact,state)
    # Collision-resistant ID; uniqueness retained across the permanent state.
    ident=hashlib.sha256((fact['id']+'|'+variant['hook'].casefold()).encode()).hexdigest()[:18]
    eid=fact['id']+'-'+ident
    if eid in state['episodes']:raise RuntimeError('Guion duplicado detectado; no publicar')
    return eid,variant


def execute(args):
    c=Config.load();c.output.mkdir(parents=True,exist_ok=True)
    for t in TOPICS:check_topic(t)
    if args.list:
        for e in catalog():print(e['id'],e['title'])
        return
    if args.list_topics:
        for t in TOPICS:print(t['id'],':',t['title'],'[',t['number'],']')
        return
    if args.check:
        for program in ('ffmpeg','ffprobe','espeak-ng'):
            print(program,shutil.which(program) or 'NO INSTALADO')
        print('Fichas verificadas:',len(TOPICS));print('Instagram configurado:',bool(c.uid and c.ig_token))
        return
    publish=args.publish
    if args.check_instagram:
        Instagram(c).identity();log('Instagram verificado');return
    if publish:
        gh=GitHub(c);gh.ensure()
        state,sha=gh.state()
        ig=Instagram(c);ig.identity()
        if state['account'] not in (None,c.uid):raise RuntimeError('Estado vinculado a otra cuenta Instagram')
        if state['account'] is None:state['account']=c.uid;sha=gh.save(state,sha)
        # First resume any incomplete episode before creating new content.
        # An uncertain post is never resent, even across workflow executions.
        kinds=['reel']+(['feed'] if c.public_feed else [])+(['story'] if c.public_story else [])
        active=[]
        for key,entry in state['episodes'].items():
            statuses=[entry.get(k,{}).get('status','pending') for k in kinds]
            if any(v in ('pending','container') for v in statuses):
                if 'topic' in entry:
                    active.append((key,entry['topic']))
                else:
                    old=next((t for t in TOPICS if t['id']==entry.get('topic_id')),None)
                    if old is None:raise RuntimeError('Estado anterior sin ficha recuperable: '+key)
                    entry['topic']=old
                    sha=gh.save(state,sha)
                    active.append((key,old))
        if active:
            episode,topic=active[0]
        else:
            fact=pick_fact(state)
            episode,topic=next_episode(fact,state)
            state['episodes'][episode]={'topic_id':fact['id'],'topic':topic,'hook':topic['hook'],
                                        'created':now()}
            sha=gh.save(state,sha)  # reserve episode BEFORE rendering/publication
    else:
        topic=next((t for t in TOPICS if t['id']==args.topic), TOPICS[0])
        gh=ig=state=sha=None
    out=c.output/(episode if publish else topic['id']);video,photo,story=create_video(topic,out)
    write_json(out/'episode.json',{'topic':topic,'caption':caption(topic),'music_source':MUSIC_PAGE,'generated_at':now()})
    log('Archivos listos:',video,photo)
    if not publish:
        log('SIMULACIÓN: no se ha publicado nada');return
    entry=state['episodes'][episode]
    sha=gh.save(state,sha)
    text=caption(topic)
    # Si una pieza está incierta, no bloquea la otra; tampoco se vuelve a enviar la incierta.
    for kind,path in [('reel',video)]+([('feed',photo)] if c.public_feed else [])+([('story',story)] if c.public_story else []):
        item=entry.get(kind,{})
        if item.get('status') in ('published','uncertain','publishing'):
            log('Omitido',kind,':',item.get('status'));continue
        url=gh.media(episode,path)
        sha=publish_piece(gh,ig,state,sha,episode,kind,url,text)
    log('Ciclo terminado',episode)


def main():
    parser=argparse.ArgumentParser()
    m=parser.add_mutually_exclusive_group()
    m.add_argument('--publish',action='store_true',help='Publicar realmente en Instagram')
    m.add_argument('--dry-run',action='store_true',help='Renderizar sin publicar (predeterminado)')
    m.add_argument('--check',action='store_true',help='Verificar dependencias y catálogo')
    m.add_argument('--list-topics',action='store_true')
    m.add_argument('--list',action='store_true')
    m.add_argument('--check-instagram',action='store_true')
    parser.add_argument('--topic',default='azucar',help='ID del tema para --dry-run')
    args=parser.parse_args()
    try:execute(args);return 0
    except Exception as exc:log('ERROR:',redact(exc));return 1

if __name__=='__main__':sys.exit(main())
