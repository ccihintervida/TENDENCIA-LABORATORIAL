import streamlit as st
from clinical_rules import analyze
import pandas as pd
import pdfplumber, io, re, json, hashlib, hmac
from datetime import date, datetime
st.set_page_config(page_title='Tendência Laboratorial | DEMO',page_icon='🧪',layout='wide')
st.title('🧪 Tendência Laboratorial')
st.warning('AMBIENTE DE DEMONSTRAÇÃO — use SOMENTE dados fictícios. Não envie exames ou dados identificáveis de pacientes reais.')
if 'logged' not in st.session_state: st.session_state.logged=False
if not st.session_state.logged:
    with st.form('login'):
        username=st.text_input('Usuário'); password=st.text_input('Senha',type='password'); submit=st.form_submit_button('Entrar')
    try: expected_user=st.secrets['APP_USER']; expected_pass=st.secrets['APP_PASSWORD']
    except Exception:
        st.error('Configure APP_USER e APP_PASSWORD nos Secrets da hospedagem.');st.stop()
    if submit:
        if hmac.compare_digest(username,expected_user) and hmac.compare_digest(password,expected_pass):
            st.session_state.logged=True;st.rerun()
        else: st.error('Login inválido')
    st.stop()
if 'patients' not in st.session_state: st.session_state.patients={}
if 'records' not in st.session_state: st.session_state.records=[]
if st.sidebar.button('Sair'): st.session_state.logged=False;st.rerun()
page=st.sidebar.radio('Menu',['Pacientes','Enviar exame PDF','Tendência','Backup / restaurar'])
METRICS={'creatinina':('mg/dL','menor'), 'ureia':('mg/dL','menor'),'hemoglobina':('g/dL','contexto'),'leucócitos':('/mm³','contexto'),'plaquetas':('/mm³','contexto'),'lactato':('mmol/L','menor'),'sódio':('mEq/L','contexto'),'potássio':('mEq/L','contexto'),'magnésio':('mg/dL','contexto'),'pcr':('mg/L','menor'),'bicarbonato':('mmol/L','contexto'),'ph':('','contexto'),'pco2':('mmHg','contexto'),'glicose':('mg/dL','contexto'),'cálcio ionizado':('mmol/L','contexto')}

import unicodedata
from datetime import datetime

# Leitura conservadora: só usa linhas com resultado claramente associado ao exame.
ALIASES = {
    'creatinina': ['creatinina'], 'ureia': ['ureia'],
    'hemoglobina': ['hemoglobina'], 'leucócitos': ['leucocitos', 'leucócitos'],
    'plaquetas': ['plaquetas'], 'lactato': ['lactato'],
    'sódio': ['sodio', 'sódio'], 'potássio': ['potassio', 'potássio'],
    'magnésio': ['magnesio', 'magnésio'], 'pcr': ['proteina c reativa', 'proteína c reativa', 'pcr'],
    'bicarbonato': ['bicarbonato', 'hco3'], 'ph': ['ph'],
    'pco2': ['pco2'], 'glicose': ['glicose', 'glicemia'],
    'cálcio ionizado': ['calcio ionizado', 'cálcio ionizado']
}
NUM = re.compile(r'(?<![\d/])\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:\.\d+)?')
DATE_RE = re.compile(r'(?:data\s+(?:da\s+)?coleta|coletad[oa]\s+em)\s*[:\-]?\s*(\d{2}[/-]\d{2}[/-]\d{4})', re.I)
PATIENT_RE = re.compile(r'(?:nome\s+(?:do\s+)?paciente|paciente)\s*[:\-]\s*([^\n]+)', re.I)
RECORD_RE = re.compile(r'(?:prontu[aá]rio|registro)\s*[:\-]\s*([A-Za-z0-9-]+)', re.I)

def normalize(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s.casefold()) if not unicodedata.combining(c))

def number(s):
    s=s.strip()
    if ',' in s: s=s.replace('.','').replace(',','.')
    return float(s)

def parse_pdf(blob):
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        text='\n'.join(page.extract_text(layout=False) or '' for page in pdf.pages)
    if not text.strip():
        return {'error':'PDF sem texto pesquisável (digitalizado). Este protótipo não tem OCR.', 'values':{}}
    dates=set()
    for x in DATE_RE.findall(text):
        try: dates.add(datetime.strptime(x.replace('-','/'),'%d/%m/%Y').date().isoformat())
        except ValueError: pass
    names=PATIENT_RE.findall(text)
    records=RECORD_RE.findall(text)
    results={}; ambiguous=set()
    for line in text.splitlines():
        simple=normalize(line).strip()
        if not simple or any(x in simple for x in ['referencia', 'historico', 'anterior']):
            continue
        for metric,aliases in ALIASES.items():
            if not any(re.match(r'^\s*'+re.escape(normalize(alias))+r'\b',simple) for alias in aliases):
                continue
            # Não confundir valores de referência, cabeçalhos, unidades ou datas.
            m=re.match(r'^\s*[\wÀ-ÿ\s0-9()/-]+?\s*[:\-]?\s*(\d[\d.,]*)\s*(?:mg/dl|mmol/l|meq/l|g/dl|/mm3|/mm³|u/l|%|$)',line,re.I)
            if not m: continue
            try: value=number(m.group(1))
            except ValueError: continue
            if metric in results and results[metric]!=value: ambiguous.add(metric)
            else: results[metric]=value
    for metric in ambiguous: results.pop(metric,None)
    return {'values':results,'ambiguous':sorted(ambiguous),'dates':sorted(dates),
            'names':names,'records':records,'error':None}

def patient_picker(key):
    opts=st.session_state.patients
    if not opts: st.info('Cadastre primeiro um paciente fictício.');st.stop()
    query=st.text_input('Pesquisar nome ou prontuário',key=f'search_{key}')
    ids=[pid for pid,name in opts.items() if query.lower() in (pid+' '+name).lower()]
    if not ids: st.info('Nenhum paciente encontrado.');st.stop()
    return st.selectbox('Paciente',ids,format_func=lambda p:f'{opts[p]} — {p}',key=f'patient_{key}')
if page=='Pacientes':
    st.subheader('Cadastrar paciente fictício')
    with st.form('new'):
        name=st.text_input('Nome fictício'); pid=st.text_input('Prontuário fictício'); ok=st.form_submit_button('Cadastrar')
    if ok:
        if not name.strip() or not pid.strip(): st.error('Preencha os dois campos.')
        elif pid in st.session_state.patients: st.error('Prontuário já cadastrado.')
        else: st.session_state.patients[pid.strip()]=name.strip();st.success('Paciente cadastrado!')
    st.dataframe(pd.DataFrame([{'Nome':v,'Prontuário':k} for k,v in st.session_state.patients.items()]),hide_index=True,use_container_width=True)
elif page=='Enviar exame PDF':
    st.subheader('Leitura automática de múltiplos PDFs — DEMONSTRAÇÃO')
    pid=patient_picker('upload')
    patient_name=st.session_state.patients[pid]
    st.caption('Sem digitação de resultados. O sistema bloqueia PDFs sem identidade e data verificáveis ou com extração insuficiente.')
    pdfs=st.file_uploader('Selecione PDFs fictícios do MESMO paciente',type=['pdf'],accept_multiple_files=True)
    if pdfs:
        pending=[]
        for pdf in pdfs:
            st.markdown(f'**📄 {pdf.name}**')
            if pdf.size>8_000_000:
                st.error('Arquivo acima de 8 MB.'); continue
            try: data=parse_pdf(pdf.getvalue())
            except Exception as exc:
                st.error('Falha na leitura do PDF.'); continue
            if data['error']:
                st.error(data['error']); continue
            if len(data['dates'])!=1:
                st.error('Bloqueado: data de coleta ausente ou múltiplas datas de coleta no mesmo PDF.')
                continue
            names=[normalize(x).strip() for x in data['names']]
            selected=normalize(patient_name).strip()
            # Confirmação conservadora: o nome deve aparecer como identificação do paciente.
            if not names or not any(x==selected or x.startswith(selected+' ') for x in names):
                st.error('Bloqueado: nome do paciente não identificado ou diferente do cadastro.')
                continue
            if data['records'] and pid not in data['records']:
                st.error('Bloqueado: prontuário do PDF diferente do cadastro.')
                continue
            if not data['values']:
                st.error('Bloqueado: nenhum resultado extraído com segurança.'); continue
            st.write('Data da coleta identificada:',data['dates'][0])
            st.dataframe(pd.DataFrame([{'Exame':k,'Resultado':v,'Unidade':METRICS[k][0]}
                                       for k,v in data['values'].items()]),hide_index=True)
            if data['ambiguous']:
                st.warning('Resultados conflitantes ignorados: '+', '.join(data['ambiguous']))
            st.warning('Extração experimental: confira o PDF original. Resultados omitidos não são interpretados.')
            pending.append({'prontuario':pid,'data':data['dates'][0],
                            'arquivo':pdf.name,'hash':hashlib.sha256(pdf.getvalue()).hexdigest(),
                            'valores':data['values']})
        if pending and st.button('Salvar PDFs elegíveis (somente demonstração)',type='primary'):
            existing={(r['prontuario'],r.get('hash',r['arquivo'])) for r in st.session_state.records}
            added=0
            for record in pending:
                key=(record['prontuario'],record['hash'])
                if key not in existing:
                    st.session_state.records.append(record)
                    existing.add(key); added+=1
            st.success(f'{added} PDF(s) adicionados à sessão. Faça backup JSON.')

elif page=='Tendência':
    st.subheader('Tendência laboratorial cronológica — sem gráficos')
    pid=patient_picker('trend')
    records=sorted([r for r in st.session_state.records if r['prontuario']==pid],key=lambda r:(r['data'],r['arquivo']))
    if not records: st.info('Nenhum exame salvo para este paciente.');st.stop()
    st.write(f'**{len(records)} arquivo(s)** | **{len(set(r["data"] for r in records))} data(s)**')
    # Colunas por exame preservam resultados distintos no mesmo dia.
    labels=[f'{r["data"]} · {i+1}' for i,r in enumerate(records)]
    matrix=[]
    for metric,(unit,_) in METRICS.items():
        vals=[r['valores'].get(metric) for r in records]
        if any(v is not None for v in vals):
            row={'Exame':f'{metric.capitalize()} ({unit})'}
            row.update({label:('—' if v is None else v) for label,v in zip(labels,vals)})
            matrix.append(row)
    st.markdown('#### Resultados por data (do mais antigo ao mais recente)')
    st.dataframe(pd.DataFrame(matrix),hide_index=True,use_container_width=True)
    st.caption('Colunas numeradas distinguem PDFs da mesma data. “—” significa resultado não informado, não valor zero.')
    st.markdown('#### Interpretação descritiva das tendências')
    for metric,(unit,kind) in METRICS.items():
        obs=[(r['data'],r['valores'][metric]) for r in records if metric in r['valores']]
        if len(obs)<2: continue
        old,new=obs[0][1],obs[-1][1]
        if new>old: direction='aumento'
        elif new<old: direction='redução'
        else: direction='estabilidade'
        sequence=' → '.join(f'{v:g}' for _,v in obs)
        st.write(f'**{metric.capitalize()}:** {sequence} {unit} — **{direction}** entre {obs[0][0]} e {obs[-1][0]}.')
    st.warning('As tendências descrevem variações numéricas, não determinam melhora, piora, diagnóstico ou conduta. Resultados dependem do contexto clínico e de intervalos de referência. Confira cada valor no laudo original.')
    st.markdown('#### Análise integrada — achados e hipóteses (não é diagnóstico)')
    st.info('Regras de triagem demonstrativas. Valores extraídos precisam ser conferidos. Os resultados de exames diferentes podem não ter sido coletados simultaneamente. Não substitui avaliação clínica.')
    findings=analyze(records)
    for item in findings:
        if item['nivel']=='tendência': continue
        with st.expander(f"{'⚠️' if item['nivel']=='prioritário' else '🔎'} {item['titulo']}", expanded=item['nivel']=='prioritário'):
            st.write('**Evidência:** '+item['evidencia'])
            st.write('**Interpretação / hipótese:** '+item['interpretacao'])
            if item['verificar']: st.write('**Conferir / informações faltantes:** '+item['verificar'])
    if not [x for x in findings if x['nivel']!='tendência']:
        st.info('Nenhum achado das regras disponíveis foi identificado; isso não exclui alterações ou doenças.')
    st.warning('IMPORTANTE: não misture sódio/potássio séricos com valores da gasometria sem identificar o tipo de amostra. A versão demo não distingue automaticamente essas fontes. As correlações usam os valores mais recentes disponíveis, que podem ser de datas diferentes.')
    st.markdown('#### Arquivos incluídos')
    for i,r in enumerate(records):
        with st.expander(f'{r["data"]} — {r["arquivo"]} (coluna {i+1})'):
            st.json(r['valores'])
else:
    st.subheader('Backup e restauração')
    st.error('Os dados desta demonstração ficam na sessão e podem desaparecer ao reiniciar o aplicativo. Baixe o backup após cada uso.')
    data={'patients':st.session_state.patients,'records':st.session_state.records,'version':1}
    st.download_button('⬇️ Baixar backup JSON',json.dumps(data,ensure_ascii=False,indent=2),file_name='backup_demo_laboratorio.json',mime='application/json')
    up=st.file_uploader('Restaurar backup JSON',type=['json'])
    if up and st.button('Restaurar agora'):
        try:
            obj=json.load(up)
            assert isinstance(obj['patients'],dict) and isinstance(obj['records'],list)
            assert len(obj['records'])<10000
            st.session_state.patients=obj['patients'];st.session_state.records=obj['records']
            st.success('Backup restaurado.');st.rerun()
        except Exception: st.error('Backup inválido.')