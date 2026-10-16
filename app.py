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
PATTERNS={'creatinina':r'creatinina[^\n]{0,100}?(?:resultado[^\n]{0,30}?)?([0-9]+[,.][0-9]+)','ureia':r'ureia[^\n]{0,100}?(?:resultado[^\n]{0,30}?)?([0-9]+[,.][0-9]+)','hemoglobina':r'hemoglobinas?[^\n]{0,25}?([0-9]+[,.][0-9]+)','leucócitos':r'leucócitos[^\n]{0,65}?([0-9]{1,3}(?:\.[0-9]{3})+)','plaquetas':r'plaquetas[^\n]{0,25}?([0-9]{1,3}(?:\.[0-9]{3})+)','lactato':r'lactato[^\n]{0,100}?(?:resultado[^\n]{0,30}?)?([0-9]+[,.][0-9]+)','sódio':r's[oó]dio[^\n]{0,45}?([0-9]+[,.][0-9]+)','potássio':r'pot[aá]ssio[^\n]{0,45}?([0-9]+[,.][0-9]+)','magnésio':r'magn[eé]sio[^\n]{0,100}?(?:resultado[^\n]{0,30}?)?([0-9]+[,.][0-9]+)'}
def parse_pdf(blob):
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        text='\n'.join(page.extract_text() or '' for page in pdf.pages)
    found={}
    # Extraction is a draft, never assume accuracy; multiple values or page headers may interfere.
    for metric,pat in PATTERNS.items():
        m=re.search(pat,text,re.I)
        if m:
            raw=m.group(1).replace('.','').replace(',','.') if metric in ['leucócitos','plaquetas'] else m.group(1).replace(',','.')
            try: found[metric]=float(raw)
            except ValueError: pass
    return found, bool(text.strip())
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
    st.subheader('Enviar vários exames do mesmo paciente')
    pid=patient_picker('upload')
    pdfs=st.file_uploader('Selecione vários PDFs fictícios (um por data)',type=['pdf'],accept_multiple_files=True)
    if pdfs:
        st.info('Confira a DATA e TODOS os resultados de cada PDF. A leitura automática pode confundir valores e datas. PDFs digitalizados exigem digitação manual.')
        drafts=[]
        for idx,pdf in enumerate(pdfs):
            with st.expander(f'📄 {pdf.name}',expanded=True):
                if pdf.size>8_000_000:
                    st.error('Arquivo maior que 8 MB.');continue
                try:
                    extracted,has_text=parse_pdf(pdf.getvalue())
                except Exception:
                    extracted,has_text={},False
                if not has_text: st.warning('Sem texto extraível; preencha os resultados manualmente.')
                # A data não é inferida do nome: exige confirmação do operador.
                dt=st.date_input('Data da coleta deste PDF (confira no laudo)',value=date.today(),key=f'dt_{pid}_{idx}_{pdf.name}')
                cols=st.columns(3)
                raw={}
                for j,(metric,(unit,_)) in enumerate(METRICS.items()):
                    with cols[j%3]:
                        raw[metric]=st.text_input(f'{metric.capitalize()} ({unit})',value=str(extracted.get(metric,'')),key=f'm_{pid}_{idx}_{pdf.name}_{metric}')
                drafts.append((pdf.name,str(dt),raw))
        if st.button('💾 Salvar todos os exames conferidos',type='primary'):
            pending=[];errors=[]
            for fname,dt,raw in drafts:
                vals={}
                for metric,v in raw.items():
                    if v.strip():
                        try: vals[metric]=float(v.strip().replace(',','.'))
                        except ValueError: errors.append(f'{fname}: valor inválido para {metric}')
                if not vals: errors.append(f'{fname}: informe pelo menos um resultado')
                pending.append({'prontuario':pid,'data':dt,'arquivo':fname,'valores':vals})
            if errors:
                for err in errors: st.error(err)
            else:
                # Evita duplicar o mesmo PDF na mesma data em envios repetidos.
                existing={(r['prontuario'],r['data'],r['arquivo']) for r in st.session_state.records}
                added=0
                for r in pending:
                    key=(r['prontuario'],r['data'],r['arquivo'])
                    if key not in existing:
                        st.session_state.records.append(r);existing.add(key);added+=1
                st.success(f'{added} exame(s) salvo(s) nesta sessão. Baixe o backup JSON para não perder os dados.')
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
