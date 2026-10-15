import streamlit as st
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
METRICS={'creatinina':('mg/dL','menor'), 'ureia':('mg/dL','menor'),'hemoglobina':('g/dL','contexto'),'leucócitos':('/mm³','contexto'),'plaquetas':('/mm³','contexto'),'lactato':('mmol/L','menor'),'sódio':('mEq/L','contexto'),'potássio':('mEq/L','contexto'),'magnésio':('mg/dL','contexto'),'pcr':('mg/L','menor'),'bicarbonato':('mmol/L','contexto')}
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
    st.subheader('Adicionar exame')
    pid=patient_picker('upload')
    dt=st.date_input('Data da coleta',value=date.today())
    pdf=st.file_uploader('Exame em PDF (apenas fictício)',type=['pdf'])
    if pdf:
        if pdf.size>8_000_000: st.error('PDF excede 8 MB.');st.stop()
        try: extracted,has_text=parse_pdf(pdf.getvalue())
        except Exception as e: st.error('Não foi possível ler o PDF. Use um PDF textual.');st.stop()
        if not has_text: st.warning('PDF digitalizado sem texto. Digite os valores manualmente.')
        st.info('Confira e corrija TODOS os valores antes de salvar. A extração automática pode errar.')
        with st.form('confirm'):
            values={}
            for metric,(unit,_) in METRICS.items():
                default=str(extracted[metric]) if metric in extracted else ''
                value=st.text_input(f'{metric.capitalize()} ({unit})',value=default)
                if value.strip():
                    try: values[metric]=float(value.replace(',','.'))
                    except ValueError: st.error(f'Valor inválido: {metric}')
            ok=st.form_submit_button('Salvar resultados conferidos')
        if ok:
            if not values: st.error('Informe pelo menos um resultado.')
            else:
                st.session_state.records.append({'prontuario':pid,'data':str(dt),'arquivo':pdf.name,'valores':values})
                st.success('Resultados salvos nesta sessão. Faça backup para preservar os dados.')
elif page=='Tendência':
    st.subheader('Comparação de exames')
    pid=patient_picker('trend')
    records=sorted([r for r in st.session_state.records if r['prontuario']==pid],key=lambda r:r['data'])
    if not records: st.info('Nenhum exame salvo para este paciente.');st.stop()
    rows=[]
    for metric,(unit,kind) in METRICS.items():
        observations=[(r['data'],r['valores'][metric]) for r in records if metric in r['valores']]
        if not observations: continue
        first=observations[0]; last=observations[-1]
        delta=last[1]-first[1]
        trend='Estável' if abs(delta)<0.00001 else ('Aumentou' if delta>0 else 'Diminuiu')
        rows.append({'Exame':metric.capitalize(),'Primeira data':first[0],'Primeiro valor':first[1],'Última data':last[0],'Último valor':last[1],'Unidade':unit,'Tendência':trend})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    st.caption('Aumento ou redução NÃO significa necessariamente melhora ou piora. A interpretação depende de referências, contexto clínico, método e unidade.')
    st.subheader('Histórico por data')
    for r in records:
        with st.expander(f"{r['data']} — {r['arquivo']}"):
            st.json(r['valores'])
    st.warning('Este protótipo não fornece diagnóstico nem decisão terapêutica. Confira os laudos originais e consulte o profissional responsável.')
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
