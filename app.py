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
# Extrator para laudos textuais PCLAB. Não realiza OCR nem validação clínica.
DATE_RE = re.compile(r"\bColeta\s*:\s*(\d{2}/\d{2}/\d{4})(?:\s+\d{2}:\d{2})?", re.I)
EXAM_RE = re.compile(r"(?im)^\s*Exame\s*:\s*([^\n]+)")
PATIENT_RE = re.compile(r"(?im)^\s*Paciente\s*:\s*(.+?)\s+(?:Nasc\.\.|Nasc\.|Sexo\s*:|$)")
PATIENT_CODE_RE = re.compile(r"(?im)C[oó]d\.\s*Pac\.\s*:\s*(\d+)")

def normalize(s):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', str(s).casefold()) if not unicodedata.combining(c)).split())

def number(s):
    s=s.strip()
    if ',' in s: s=s.replace('.','').replace(',','.')
    elif re.fullmatch(r'\d{1,3}(?:\.\d{3})+',s): s=s.replace('.','')
    return float(s)

def find_result(block, pattern):
    match=re.search(pattern, block, re.I | re.M)
    return number(match.group(1)) if match else None

def parse_pdf(blob):
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        pages=[page.extract_text(layout=False) or '' for page in pdf.pages]
    if not any(p.strip() for p in pages):
        return {'error':'PDF sem texto pesquisável. Esta demonstração não possui OCR.', 'values':{}}
    text='\n'.join(pages)
    # Cada página pode conter vários exames; separamos pelo título Exame.
    pieces=re.split(r'(?im)^\s*Exame\s*:\s*', text)
    entries=[]
    for piece in pieces[1:]:
        heading=re.split(r'\s+Id\s+Exame\s*:',piece.splitlines()[0],flags=re.I)[0].strip()
        body='\n'.join(piece.splitlines()[1:])
        # Recorta no próximo cabeçalho de paciente para não carregar resultados da página seguinte.
        body=re.split(r'(?im)^\s*Dt\.\s*Cadastro\s*:',body)[0]
        entries.append((normalize(heading),body))
    dates=set()
    for _,body in entries:
        for d in DATE_RE.findall(body):
            try: dates.add(datetime.strptime(d,'%d/%m/%Y').date().isoformat())
            except ValueError: pass
    names=[normalize(x) for x in PATIENT_RE.findall(text)]
    codes=PATIENT_CODE_RE.findall(text)
    results={}; ambiguous=set(); evidence={}
    # Só extrair a linha de resultado do exame correspondente; não ler referências nem histórico.
    simple_tests={
        'creatinina':'creatinina', 'ureia':'ureia', 'magnesio':'magnésio',
        'potassio':'potássio', 'sodio':'sódio', 'lactato venoso':'lactato',
        'proteina c reativa':'pcr', 'calcio ionico venoso':'cálcio ionizado',
    }
    result_pattern=r'(?im)^\s*(?:resultado|resultado\.{2,})\s*\.*\s*:\s*([0-9][0-9.,]*)\b'
    # Hemograma usa uma linha com porcentagem antes da contagem absoluta.
    hem_patterns={
        'hemoglobina':r'(?im)^\s*Hemoglobinas?\.{2,}\s*:\s*([0-9][0-9.,]*)\s*g/dL',
        'leucócitos':r'(?im)^\s*Leuc[oó]citos\.{2,}\s*:\s*\d+\s*%\s*([0-9][0-9.,]*)\s*/mm3',
        'plaquetas':r'(?im)^\s*Plaquetas\.{2,}\s*:\s*([0-9][0-9.,]*)\s*/mm3',
    }
    gas_patterns={
        'ph':r'(?im)^\s*pH\.{2,}\s*:\s*([0-9][0-9.,]*)',
        'pco2':r'(?im)^\s*PCO2\.{2,}\s*:\s*([0-9][0-9.,]*)',
        'bicarbonato':r'(?im)^\s*HC[O0]3\.{2,}\s*:\s*([0-9][0-9.,]*)',
        'glicose':r'(?im)^\s*glicose\s*\.{2,}\s*:\s*([0-9][0-9.,]*)',
    }
    def add(metric,value,source):
        if value is None: return
        if metric in results and results[metric]!=value: ambiguous.add(metric)
        else: results[metric]=value; evidence[metric]=source
    for title,body in entries:
        # Retirar rodapé e histórico, para não confundir valores anteriores.
        body=re.split(r'(?im)^\s*Resultados anteriores\s*:',body)[0]
        if title in simple_tests:
            add(simple_tests[title],find_result(body,result_pattern),title)
        elif title.startswith('hemograma'):
            for metric,pattern in hem_patterns.items(): add(metric,find_result(body,pattern),title)
        elif title.startswith('gasometria venosa'):
            for metric,pattern in gas_patterns.items(): add(metric,find_result(body,pattern),title)
            # Sódio/potássio da gasometria NÃO são misturados com resultados séricos.
    for metric in ambiguous: results.pop(metric,None);evidence.pop(metric,None)
    return {'values':results,'ambiguous':sorted(ambiguous),'dates':sorted(dates),
            'names':names,'patient_codes':sorted(set(codes)),'records':[],
            'evidence':evidence,'error':None}

def patient_picker(key):
    opts=st.session_state.patients
    if not opts: st.info('Cadastre primeiro um paciente fictício.');st.stop()
    query=st.text_input('Pesquisar nome ou prontuário',key=f'search_{key}')
    ids=[pid for pid,name in opts.items() if query.lower() in (pid+' '+name).lower()]
    if not ids: st.info('Nenhum paciente encontrado.');st.stop()
    return st.selectbox('Paciente',ids,format_func=lambda p:f'{opts[p]} — {p}',key=f'patient_{key}')
def data_br(iso):
    try: return datetime.strptime(str(iso), '%Y-%m-%d').strftime('%d/%m/%Y')
    except (ValueError, TypeError): return str(iso)

def numero_br(value):
    if value is None: return '—'
    try:
        n=float(value)
        if not (n == n and abs(n) != float('inf')): return '—'
        txt=(f'{n:,.2f}'.rstrip('0').rstrip('.') if n != int(n) else f'{int(n):,}')
        return txt.replace(',', '#').replace('.', ',').replace('#', '.')
    except (ValueError, TypeError, OverflowError): return str(value)

def resumo_tendencia(valores):
    if len(valores)<2: return 'sem medições suficientes'
    mudancas=[]
    for a,b in zip(valores,valores[1:]):
        if b>a: mudancas.append('aumento')
        elif b<a: mudancas.append('redução')
        else: mudancas.append('estabilidade')
    if all(m == 'estabilidade' for m in mudancas): return 'estabilidade'
    if 'aumento' in mudancas and 'redução' in mudancas:
        if valores[-1]>valores[0]: saldo='aumento líquido'
        elif valores[-1]<valores[0]: saldo='redução líquida'
        else: saldo='sem variação líquida'
        return 'oscilação (aumentou e diminuiu); '+saldo
    return ('aumento' if valores[-1]>valores[0] else 'redução' if valores[-1]<valores[0] else 'estabilidade')

def gerar_relatorio_pdf(nome, prontuario, registros, metricas, achados):
    """Gera relatório para impressão com os dados já conferidos na sessão."""
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from xml.sax.saxutils import escape
    import os

    buffer = io.BytesIO()
    fonte = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    negrito = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    if os.path.isfile(fonte) and 'DejaVuRel' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('DejaVuRel', fonte))
        pdfmetrics.registerFont(TTFont('DejaVuRel-Bold', negrito))
        pdfmetrics.registerFontFamily('DejaVuRel', normal='DejaVuRel', bold='DejaVuRel-Bold')
    familia = 'DejaVuRel' if os.path.isfile(fonte) else 'Helvetica'
    styles = getSampleStyleSheet()
    normal = ParagraphStyle('NormalRel', parent=styles['Normal'], fontName=familia, fontSize=8.5, leading=12, spaceAfter=6)
    titulo = ParagraphStyle('TituloRel', parent=normal, fontSize=16, leading=21, alignment=TA_CENTER, spaceAfter=14)
    secao = ParagraphStyle('SecaoRel', parent=normal, fontSize=11, leading=15, spaceBefore=12, spaceAfter=8)
    pequeno = ParagraphStyle('PequenoRel', parent=normal, fontSize=7, leading=10)
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=1.3*cm, leftMargin=1.3*cm,
                            topMargin=1.4*cm, bottomMargin=1.4*cm)
    story = [Paragraph('RELATÓRIO DE TENDÊNCIA LABORATORIAL', titulo),
             Paragraph('DEMONSTRAÇÃO — Dados fictícios/anonimizados. Não validado para uso clínico.', normal),
             Paragraph('<b>Paciente:</b> ' + escape(str(nome)) + '    <b>Prontuário:</b> ' + escape(str(prontuario)), normal),
             Paragraph(f'<b>Arquivos:</b> {len(registros)}    <b>Datas distintas:</b> {len(set(r["data"] for r in registros))}', normal)]
    # Divide a tabela em blocos para manter as colunas legíveis na impressão.
    for inicio in range(0, len(registros), 5):
        bloco = registros[inicio:inicio+5]
        story.append(Paragraph('Resultados cronológicos' + (f' (parte {inicio//5+1})' if len(registros)>5 else ''), secao))
        header = [Paragraph('<b>Exame</b>', pequeno)]
        for r in bloco:
            header.append(Paragraph('<b>'+escape(data_br(r['data']))+'</b>', pequeno))
        linhas = [header]
        for metrica,(unidade,_) in metricas.items():
            valores=[r.get('valores',{}).get(metrica) for r in bloco]
            if not any(v is not None for v in valores):
                continue
            row=[Paragraph(escape(metrica.capitalize()+' ('+unidade+')'), pequeno)]
            row += [Paragraph('—' if v is None else escape(numero_br(v)), pequeno) for v in valores]
            linhas.append(row)
        largura = 25.5*cm
        tabela = Table(linhas, colWidths=[6.5*cm]+[(largura-6.5*cm)/len(bloco)]*len(bloco), repeatRows=1, hAlign='LEFT')
        tabela.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eef6')),
            ('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#cbd5e1')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f8fafc')]),
            ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
        ]))
        story.append(tabela)
    story.append(Paragraph('Evolução numérica', secao))
    tem_tendencia=False
    for metrica,(unidade,_) in metricas.items():
        obs=[(r['data'],r['valores'][metrica]) for r in registros if metrica in r.get('valores',{})]
        if len(obs)<2: continue
        tem_tendencia=True
        vals=' → '.join(numero_br(v) for _,v in obs)
        direcao=resumo_tendencia([v for _,v in obs])
        story.append(Paragraph('<b>'+escape(metrica.capitalize())+':</b> '+escape(vals)+' '+escape(unidade)+' — '+direcao, normal))
    if not tem_tendencia:
        story.append(Paragraph('Não há duas medições do mesmo parâmetro para calcular tendência.', normal))
    story.append(Paragraph('Pontos que exigem conferência', secao))
    if any((r.get('valores',{}).get('lactato') or 0) >= 4 for r in registros):
        story.append(Paragraph('Há lactato igual ou superior a 4 mmol/L em pelo menos uma coleta. Verifique o valor e a data diretamente no laudo original; se confirmado em contexto clínico real, exige avaliação clínica imediata.', normal))
    story.append(Paragraph('Os indicadores de alteração dependem do tipo de amostra e dos intervalos de referência do laboratório. Não há destaque automático de normalidade sem essa confirmação.', normal))
    story.append(Paragraph('Achados laboratoriais e hipóteses — não constituem diagnóstico', secao))
    exibidos=[a for a in achados if a.get('nivel')!='tendência']
    if not exibidos:
        story.append(Paragraph('Nenhum achado identificado pelas regras disponíveis.', normal))
    for a in exibidos:
        partes=[Paragraph('<b>'+escape(str(a.get('titulo','Achado')))+'</b>', normal)]
        for rotulo,chave in [('Evidência','evidencia'),('Interpretação / hipótese','interpretacao'),('Conferir','verificar')]:
            if a.get(chave): partes.append(Paragraph('<b>'+rotulo+':</b> '+escape(str(a[chave])), normal))
        story.append(KeepTogether(partes))
    story.append(Paragraph('Limitações: extração automática experimental. Confirme identidade, data, amostra, unidade e cada resultado no laudo original. Correlações não estabelecem causalidade. Não substitui avaliação profissional.', pequeno))
    story.append(Paragraph('Arquivos utilizados: '+escape('; '.join(str(r.get('arquivo','')) for r in registros)), pequeno))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()



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
            if not names or any(x != selected for x in names):
                st.error('Bloqueado: nome do paciente não identificado ou diferente do cadastro.')
                continue
            if data['records'] and pid not in data['records']:
                st.error('Bloqueado: prontuário do PDF diferente do cadastro.')
                continue
            if not data['values']:
                st.error('Bloqueado: nenhum resultado extraído com segurança.'); continue
            st.write('Data da coleta identificada:',data['dates'][0])
            st.caption('O código do paciente do laboratório pode ser diferente do prontuário local. Confira a identidade no PDF antes de salvar.')
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
    labels=[f'{data_br(r["data"])} · {i+1}' for i,r in enumerate(records)]
    matrix=[]
    for metric,(unit,_) in METRICS.items():
        vals=[r['valores'].get(metric) for r in records]
        if any(v is not None for v in vals):
            row={'Exame':f'{metric.capitalize()} ({unit})'}
            row.update({label:numero_br(v) for label,v in zip(labels,vals)})
            matrix.append(row)
    st.markdown('#### Resultados por data (do mais antigo ao mais recente)')
    st.dataframe(pd.DataFrame(matrix),hide_index=True,use_container_width=True)
    st.caption('Colunas numeradas distinguem PDFs da mesma data. “—” significa resultado não informado, não valor zero.')
    st.markdown('#### Interpretação descritiva das tendências')
    for metric,(unit,kind) in METRICS.items():
        obs=[(r['data'],r['valores'][metric]) for r in records if metric in r['valores']]
        if len(obs)<2: continue
        old,new=obs[0][1],obs[-1][1]
        direction=resumo_tendencia([v for _,v in obs])
        sequence=' → '.join(numero_br(v) for _,v in obs)
        st.write(f'**{metric.capitalize()}:** {sequence} {unit} — **{direction}** entre {data_br(obs[0][0])} e {data_br(obs[-1][0])}.')
    st.warning('As tendências descrevem variações numéricas, não determinam melhora, piora, diagnóstico ou conduta. Resultados dependem do contexto clínico e de intervalos de referência. Confira cada valor no laudo original.')
    st.markdown('#### Análise integrada — achados e hipóteses (não é diagnóstico)')
    st.info('Regras de triagem demonstrativas. Valores extraídos precisam ser conferidos. Os resultados de exames diferentes podem não ter sido coletados simultaneamente. Não substitui avaliação clínica.')
    findings=analyze(records)
    try:
        relatorio = gerar_relatorio_pdf(st.session_state.patients[pid], pid, records, METRICS, findings)
        st.download_button('📄 Baixar relatório em PDF para imprimir', data=relatorio,
                           file_name='relatorio_tendencia_'+re.sub(r'[^a-zA-Z0-9_-]','_',pid)+'.pdf',
                           mime='application/pdf', type='primary')
        st.caption('Abra o PDF baixado e pressione Ctrl + P para imprimir.')
    except Exception:
        st.error('Não foi possível gerar o PDF. Confira se reportlab está instalado nas dependências.')
    for item in findings:
        if item['nivel']=='tendência': continue
        with st.expander(f"{'⚠️' if item['nivel']=='prioritário' else '🔎'} {item['titulo']}", expanded=item['nivel']=='prioritário'):
            st.write('**Evidência:** '+item['evidencia'])
            st.write('**Interpretação / hipótese:** '+item['interpretacao'])
            if item['verificar']: st.write('**Conferir / informações faltantes:** '+item['verificar'])
    if not [x for x in findings if x['nivel']!='tendência']:
        st.info('Nenhum achado das regras disponíveis foi identificado; isso não exclui alterações ou doenças.')
    st.warning('Os valores de sódio e potássio da gasometria venosa não são incluídos como valores séricos. A correlação entre exames pode envolver datas diferentes; valide os resultados no laudo.')
    st.markdown('#### Arquivos incluídos')
    for i,r in enumerate(records):
        with st.expander(f'{data_br(r["data"])} — {r["arquivo"]} (coluna {i+1})'):
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