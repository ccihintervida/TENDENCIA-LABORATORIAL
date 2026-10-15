import os, re, sqlite3, hashlib, hmac, secrets, unicodedata, uuid
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
import fitz
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('APP_DATA_DIR', str(ROOT/'dados'))).resolve()
DATA.mkdir(parents=True,exist_ok=True)
FILES=DATA/'arquivos'; FILES.mkdir(exist_ok=True)
DB=DATA/'app.sqlite3'
PASSWORD=os.environ.get('APP_PASSWORD','')
if not PASSWORD: raise RuntimeError('Defina APP_PASSWORD antes de iniciar. Ex.: APP_PASSWORD="senha-forte" uvicorn app:app --host 127.0.0.1 --port 8000')
app=FastAPI(title='Tendência Laboratorial', docs_url=None, redoc_url=None)
tpl=Jinja2Templates(directory=str(ROOT/'templates'))
security=HTTPBasic()

def auth(c:HTTPBasicCredentials=Depends(security)):
    if not (hmac.compare_digest(c.username.encode(),os.environ.get('APP_USER','admin').encode()) and hmac.compare_digest(c.password.encode(),PASSWORD.encode())):
        raise HTTPException(401,'Acesso não autorizado',headers={'WWW-Authenticate':'Basic realm="Sistema Laboratorial"'})
    return True

@contextmanager
def conn():
    db=sqlite3.connect(DB)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
        db.commit()
    finally: db.close()

with conn() as db:
    db.executescript('''CREATE TABLE IF NOT EXISTS pacientes(id INTEGER PRIMARY KEY, nome TEXT NOT NULL, prontuario TEXT NOT NULL UNIQUE, criado_em TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS exames(id INTEGER PRIMARY KEY, paciente_id INTEGER NOT NULL REFERENCES pacientes(id), data_coleta TEXT NOT NULL, arquivo TEXT NOT NULL, nome_original TEXT NOT NULL, criado_em TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'conferir');
    CREATE TABLE IF NOT EXISTS resultados(id INTEGER PRIMARY KEY, exame_id INTEGER NOT NULL REFERENCES exames(id) ON DELETE CASCADE, analito TEXT NOT NULL, valor REAL NOT NULL, unidade TEXT NOT NULL, origem TEXT NOT NULL DEFAULT 'extraido', UNIQUE(exame_id,analito));''')

# Explicit whitelist; do not interpret arbitrary PDF numbers as laboratory values.
TESTS={
 'creatinina':('Creatinina','mg/dL'), 'ureia':('Ureia','mg/dL'), 'lactato':('Lactato','mmol/L'),
 'hemoglobina':('Hemoglobina','g/dL'),'leucocitos':('Leucócitos','/mm³'),'plaquetas':('Plaquetas','/mm³'),
 'sodio':('Sódio','mmol/L'),'potassio':('Potássio','mmol/L'),'magnesio':('Magnésio','mg/dL'),
 'pcr':('PCR','mg/L'),'ph':('pH',''),'pco2':('pCO₂','mmHg'),'hco3':('HCO₃','mmol/L'),
 'glicose':('Glicose','mg/dL')}
ALIAS={
 'creatinina':['creatinina'],'ureia':['ureia'],'lactato':['lactato venoso','lactato arterial','lactato'],
 'hemoglobina':['hemoglobinas','hemoglobina'],'leucocitos':['leucocitos'],'plaquetas':['plaquetas'],
 'sodio':['sodio'],'potassio':['potassio'],'magnesio':['magnesio'],
 'pcr':['proteina c reativa','proteina c-reativa','pcr'],
 'ph':['ph'],'pco2':['pco2'],'hco3':['hco3','hc03','bicarbonato'],'glicose':['glicose']}

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD',s.lower()) if not unicodedata.combining(c))

def number(s):
    s=s.strip().replace(' ','')
    if ',' in s: s=s.replace('.','').replace(',','.')
    elif s.count('.')>1: s=s.replace('.','')
    elif '.' in s and len(s.split('.')[-1])==3 and len(s.split('.')[0])<=3: s=s.replace('.','')
    return float(s)

def date_from(text):
    for pat in [r'Coleta\s*:\s*(\d{2}/\d{2}/\d{4})',r'Dt\.\s*Cadastro\s*:\s*(\d{2}/\d{2}/\d{4})']:
        m=re.search(pat,text,re.I)
        if m:
            try: return datetime.strptime(m.group(1),'%d/%m/%Y').date().isoformat()
            except ValueError: pass
    return None

def extract(pdf_bytes):
    doc=fitz.open(stream=pdf_bytes,filetype='pdf')
    if doc.page_count>80: raise ValueError('PDF com mais de 80 páginas')
    results={}
    dates=[]
    for page in doc:
        text=page.get_text('text',sort=True)
        d=date_from(text)
        if d: dates.append(d)
        # Detect examination section heading and use ONLY that page's relevant result line.
        # Scope each single-test value to its own section (pages can contain several exams).
        headings=list(re.finditer(r'Exame\s*:\s*([^\n]+)',text,re.I))
        for ix,h in enumerate(headings):
            heading=norm(h.group(1))
            section=text[h.end():headings[ix+1].start() if ix+1<len(headings) else len(text)]
            for key,aliases in ALIAS.items():
                if key in ('ph','pco2','hco3','hemoglobina','leucocitos','plaquetas','sodio','potassio','glicose'):continue
                if not any(re.search(r'\b'+re.escape(a)+r'\b',heading) for a in aliases):continue
                m=re.search(r'(?im)\bresultado[.\s]*:\s*(-?\d[\d.,]*)',section)
                if m:
                    try:results[key]=number(m.group(1))
                    except ValueError:pass
        for key,aliases in ALIAS.items():
            if key in ('creatinina','ureia','lactato','magnesio','pcr'):continue
            for alias in aliases:
                # Some PDF text extractors concatenate the preceding column with the label.
                m=re.search(r'(?i)'+re.escape(alias)+r'[.\s]*:\s*(-?\d[\d.,]*)([^\n]*)',norm(text))
                if not m:continue
                try:val=number(m.group(1))
                except ValueError:continue
                if key=='leucocitos' and val==100:
                    alt=re.search(r'\b(\d{1,3}[.]\d{3}|\d{4,6})\b',m.group(2))
                    if alt:val=number(alt.group(1))
                if key=='plaquetas' and val<1000:continue
                results[key]=val
                break
    doc.close()
    return (dates[0] if dates else None),results

def trend(key, old, new):
    if old is None: return 'Primeiro registro','neutral'
    delta=new-old
    if abs(delta)<=max(abs(old)*0.02,0.001):return 'Sem mudança relevante','neutral'
    # Do not call arbitrary direction clinical improvement. Only clearly directional markers.
    if key in ('creatinina','ureia','lactato','pcr','leucocitos'):
        return ('Aumentou — atenção','bad') if delta>0 else ('Reduziu — avaliar contexto','good')
    return ('Aumentou' if delta>0 else 'Diminuiu'),'neutral'

def get_patient(pid):
    with conn() as db: p=db.execute('SELECT * FROM pacientes WHERE id=?',(pid,)).fetchone()
    if not p:raise HTTPException(404,'Paciente não encontrado')
    return p

def view_patient(request,pid):
    p=get_patient(pid)
    with conn() as db:
        exams=db.execute('SELECT * FROM exames WHERE paciente_id=? ORDER BY data_coleta,id',(pid,)).fetchall()
        rows=db.execute('''SELECT r.*,e.data_coleta,e.id AS eid FROM resultados r JOIN exames e ON e.id=r.exame_id WHERE e.paciente_id=? ORDER BY e.data_coleta,e.id''',(pid,)).fetchall()
    by={}
    for r in rows:by.setdefault(r['analito'],[]).append(r)
    trends=[]
    for k,items in by.items():
        current=items[-1]; previous=items[-2] if len(items)>1 else None
        desc,color=trend(k,previous['valor'] if previous else None,current['valor'])
        trends.append(dict(key=k,name=TESTS[k][0],unit=TESTS[k][1],previous=previous,current=current,desc=desc,color=color))
    trends.sort(key=lambda x:x['name'])
    return tpl.TemplateResponse(request,'patient.html',{'p':p,'exams':exams,'trends':trends,'tests':TESTS,'today':datetime.now().date().isoformat()})

@app.get('/',response_class=HTMLResponse,dependencies=[Depends(auth)])
def index(request:Request,q:str=''):
    with conn() as db:
        ps=db.execute('SELECT * FROM pacientes WHERE nome LIKE ? OR prontuario LIKE ? ORDER BY nome LIMIT 100',('%'+q+'%','%'+q+'%')).fetchall()
    return tpl.TemplateResponse(request,'index.html',{'patients':ps,'q':q})

@app.post('/pacientes',dependencies=[Depends(auth)])
def create(nome:str=Form(...),prontuario:str=Form(...)):
    nome=nome.strip();prontuario=prontuario.strip()
    if not nome or not prontuario or len(nome)>180 or len(prontuario)>80:raise HTTPException(400,'Nome/prontuário inválido')
    with conn() as db:
        try:
            cur=db.execute('INSERT INTO pacientes(nome,prontuario,criado_em) VALUES(?,?,?)',(nome,prontuario,datetime.now().isoformat()))
            pid=cur.lastrowid
        except sqlite3.IntegrityError:raise HTTPException(409,'Prontuário já cadastrado')
    return RedirectResponse(f'/pacientes/{pid}',303)

@app.get('/pacientes/{pid}',response_class=HTMLResponse,dependencies=[Depends(auth)])
def patient(request:Request,pid:int):return view_patient(request,pid)

@app.post('/pacientes/{pid}/upload',dependencies=[Depends(auth)])
async def upload(pid:int,arquivo:UploadFile=File(...),data_coleta:str=Form('')):
    get_patient(pid)
    if not arquivo.filename.lower().endswith('.pdf'):raise HTTPException(400,'Envie um arquivo PDF')
    data=await arquivo.read(15*1024*1024+1)
    if len(data)>15*1024*1024 or not data.startswith(b'%PDF-'):raise HTTPException(400,'PDF inválido ou maior que 15 MB')
    try: detected,values=extract(data)
    except Exception as e:raise HTTPException(400,'Não foi possível ler este PDF: '+str(e))
    d=data_coleta or detected
    if not d:raise HTTPException(400,'Informe a data da coleta')
    try: datetime.strptime(d,'%Y-%m-%d')
    except ValueError:raise HTTPException(400,'Data inválida')
    name=str(uuid.uuid4())+'.pdf'
    path=FILES/name
    path.write_bytes(data)
    try:
        with conn() as db:
            cur=db.execute('INSERT INTO exames(paciente_id,data_coleta,arquivo,nome_original,criado_em) VALUES(?,?,?,?,?)',(pid,d,name,Path(arquivo.filename).name[:200],datetime.now().isoformat()))
            for k,v in values.items():db.execute('INSERT INTO resultados(exame_id,analito,valor,unidade) VALUES(?,?,?,?)',(cur.lastrowid,k,v,TESTS[k][1]))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return RedirectResponse(f'/pacientes/{pid}?importado=1',303)

@app.get('/exames/{eid}/arquivo',dependencies=[Depends(auth)])
def download(eid:int):
    with conn() as db:e=db.execute('SELECT * FROM exames WHERE id=?',(eid,)).fetchone()
    if not e:raise HTTPException(404)
    return FileResponse(FILES/e['arquivo'],media_type='application/pdf',filename=e['nome_original'])

@app.post('/exames/{eid}/resultados',dependencies=[Depends(auth)])
def edit_result(eid:int,analito:str=Form(...),valor:str=Form(...)):
    with conn() as db:
        e=db.execute('SELECT * FROM exames WHERE id=?',(eid,)).fetchone()
        if not e:raise HTTPException(404)
        if analito not in TESTS:raise HTTPException(400,'Analito não suportado')
        try:v=number(valor)
        except ValueError:raise HTTPException(400,'Valor inválido')
        if not -10000<v<10000000:raise HTTPException(400,'Valor fora do limite')
        db.execute('''INSERT INTO resultados(exame_id,analito,valor,unidade,origem) VALUES(?,?,?,?,?) ON CONFLICT(exame_id,analito) DO UPDATE SET valor=excluded.valor,origem='conferido' ''',(eid,analito,v,TESTS[analito][1],'conferido'))
    return RedirectResponse(f'/pacientes/{e["paciente_id"]}',303)

@app.post('/exames/{eid}/confirmar',dependencies=[Depends(auth)])
def confirm(eid:int):
    with conn() as db:
        e=db.execute('SELECT * FROM exames WHERE id=?',(eid,)).fetchone()
        if not e:raise HTTPException(404)
        db.execute("UPDATE exames SET status='conferido' WHERE id=?",(eid,))
    return RedirectResponse(f'/pacientes/{e["paciente_id"]}',303)

@app.post('/exames/{eid}/excluir',dependencies=[Depends(auth)])
def delete(eid:int):
    with conn() as db:
        e=db.execute('SELECT * FROM exames WHERE id=?',(eid,)).fetchone()
        if not e:raise HTTPException(404)
        db.execute('DELETE FROM resultados WHERE exame_id=?',(eid,))
        db.execute('DELETE FROM exames WHERE id=?',(eid,))
    (FILES/e['arquivo']).unlink(missing_ok=True)
    return RedirectResponse(f'/pacientes/{e["paciente_id"]}',303)
