
#!/usr/bin/env python3
"""CUERPÓSFERA: Reels de divulgación basados en datos revisados.

Python 3.11+, Pillow, requests, ffmpeg/ffprobe, espeak-ng.
Uso: python monitor.py --dry-run | --publish | --check | --list-topics
Los posts se publican por separado: REEL y fotografía JPEG de feed.
No emplea IA para inventar hechos: catálogo curado con fuente, cifra y matices.
Cuenta profesional con Instagram Login; tokens en GitHub Actions Secrets.
Repositorio PUBLICO para servir archivos a Meta desde rama de estado.
"""
from __future__ import annotations
import argparse
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
    'GITHUB_TOKEN', 'IG_ACCESS_TOKEN', 'INSTAGRAM_TOKEN',
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

    @classmethod
    def load(cls):
        version=os.getenv('IG_GRAPH_VERSION','v25.0')
        if not re.fullmatch(r'v\d+\.\d+',version):raise ValueError('IG_GRAPH_VERSION inválida')
        return cls(
            repo=os.getenv('GITHUB_REPOSITORY','').strip(),
            token=os.getenv('GITHUB_TOKEN','').strip(),
            branch=os.getenv('STATE_BRANCH','cuerposfera-state').strip(),
            uid=(os.getenv('IG_USER_ID') or os.getenv('INSTAGRAM_USER_ID') or '').strip(),
            ig_token=(os.getenv('IG_ACCESS_TOKEN') or os.getenv('INSTAGRAM_TOKEN') or '').strip(),
            username=os.getenv('IG_EXPECTED_USERNAME','cuerposfera').strip().lstrip('@').lower(),
            graph_version=version,
            output=Path(os.getenv('OUTPUT_DIR','output')),
            audio=envbool('ENABLE_MUSIC',True),
            public_feed=envbool('PUBLISH_FEED',True),
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


def slide(text,subtitle,label,idx,folder,number=None):
    im=gradient();d=ImageDraw.Draw(im)
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
    out=folder/'voice.wav'
    # Narración offline, sin APIs de terceros ni claves adicionales.
    if shutil.which('espeak-ng'):
        cmd(['espeak-ng','-v','es','-s','148','-a','155','-w',str(out),text],50)
        return out
    log('espeak-ng no instalado: video tendrá textos y música, sin narración')
    return None


def create_video(t,folder):
    folder.mkdir(parents=True,exist_ok=True)
    lines=script_lines(t)
    for idx,(a,b) in enumerate(lines):
        slide(a,b,t['unit'],idx,folder,number=t['number'] if idx==1 else None)
    cover=Image.open(folder/'slide_01.png').convert('RGB')
    cover.save(folder/'feed.jpg',quality=90,optimize=True)
    # Escenas de 7 segundos = 35s, vertical 720x1280, 30 fps.
    listing=folder/'slides.txt'
    listing.write_text(''.join(f"file '{(folder/f'slide_{i:02}.png').resolve()}'\nduration 7\n" for i in range(5))+
                       f"file '{(folder/'slide_04.png').resolve()}'\n",encoding='utf-8')
    background=folder/'silent.mp4'
    cmd(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),
         '-t','35','-vf','fps=30,format=yuv420p','-c:v','libx264','-preset','veryfast','-crf','24',
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
    if voice and track:filters.append('[m][v]amix=inputs=2:duration=first:dropout_transition=0[a]')
    elif track:filters.append('[m]anull[a]')
    elif voice:filters.append('[v]anull[a]')
    else:
        args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
        filters.append('[1:a]anull[a]')
    args+=['-filter_complex',';'.join(filters),'-map','0:v:0','-map','[a]',
           '-c:v','copy','-c:a','aac','-b:a','128k','-ar','48000','-ac','2','-t','35',
           '-movflags','+faststart',str(final)]
    cmd(args,150)
    info=json.loads(cmd(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(final)],20))
    types={s['codec_type']:s for s in info.get('streams',[])}
    if (types.get('video',{}).get('codec_name')!='h264' or
        types.get('audio',{}).get('codec_name')!='aac' or
        types['video'].get('width')!=720 or types['video'].get('height')!=1280):
        raise RuntimeError('Video incompatible con Instagram')
    if final.stat().st_size>45_000_000:raise RuntimeError('MP4 supera 45 MB')
    return final,folder/'feed.jpg'


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
        b=self.req('GET','/'+self.c.uid,params={'fields':'id,username'})
        if str(b.get('id'))!=self.c.uid or b.get('username','').lower()!=self.c.username:
            raise RuntimeError('Cuenta Instagram no coincide con @'+self.c.username)
    def create(self,url,caption_text,kind):
        params={'caption':caption_text}
        if kind=='reel':params.update(media_type='REELS',video_url=url,share_to_feed='false')
        else:params['image_url']=url
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


def execute(args):
    c=Config.load();c.output.mkdir(parents=True,exist_ok=True)
    for t in TOPICS:check_topic(t)
    if args.list_topics:
        for t in TOPICS:print(t['id'],':',t['title'],'[',t['number'],']')
        return
    if args.check:
        for program in ('ffmpeg','ffprobe','espeak-ng'):
            print(program,shutil.which(program) or 'NO INSTALADO')
        print('Fichas verificadas:',len(TOPICS));print('Instagram configurado:',bool(c.uid and c.ig_token))
        return
    publish=args.publish
    if publish:
        gh=GitHub(c);gh.ensure()
        state,sha=gh.state()
        ig=Instagram(c);ig.identity()
        if state['account'] not in (None,c.uid):raise RuntimeError('Estado vinculado a otra cuenta Instagram')
        if state['account'] is None:state['account']=c.uid;sha=gh.save(state,sha)
        # Rotación: elegir la primera ficha que todavía no ha publicado ambos elementos.
        def unfinished(topic):
            item=state['episodes'].get(topic['id'],{})
            kinds=['reel']+(['feed'] if c.public_feed else [])
            statuses=[item.get(k,{}).get('status','pending') for k in kinds]
            # No volver a seleccionar episodios bloqueados solo por resultados inciertos.
            # Se conservan para reconciliación manual, mientras la cola continúa.
            return any(st in ('pending','container') for st in statuses)
        pending=[t for t in TOPICS if unfinished(t)]
        if not pending:
            log('No quedan fichas editoriales nuevas; agrega fichas verificadas a TOPICS.');return
        topic=pending[0]
    else:
        topic=next((t for t in TOPICS if t['id']==args.topic), TOPICS[0])
        gh=ig=state=sha=None
    out=c.output/topic['id'];video,photo=create_video(topic,out)
    write_json(out/'episode.json',{'topic':topic,'caption':caption(topic),'music_source':MUSIC_PAGE,'generated_at':now()})
    log('Archivos listos:',video,photo)
    if not publish:
        log('SIMULACIÓN: no se ha publicado nada');return
    episode=topic['id']
    entry=state['episodes'].setdefault(episode,{'topic_id':episode})
    sha=gh.save(state,sha)
    text=caption(topic)
    # Si una pieza está incierta, no bloquea la otra; tampoco se vuelve a enviar la incierta.
    for kind,path in [('reel',video)]+([('feed',photo)] if c.public_feed else []):
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
    parser.add_argument('--topic',default='azucar',help='ID del tema para --dry-run')
    args=parser.parse_args()
    try:execute(args);return 0
    except Exception as exc:log('ERROR:',redact(exc));return 1

if __name__=='__main__':sys.exit(main())
