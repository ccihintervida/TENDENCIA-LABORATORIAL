"""Relatório cronológico demonstrativo, sem decisão clínica automatizada."""
import io
import math
from datetime import datetime
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

INK = colors.HexColor('#183153')
PALE = colors.HexColor('#eaf0f6')
MUTED = colors.HexColor('#52647b')


def _br(v):
    try:
        n = float(v)
        if not math.isfinite(n): return '—'
        s = f'{n:,.2f}'.rstrip('0').rstrip('.') if n != int(n) else f'{int(n):,}'
        return s.replace(',', '@').replace('.', ',').replace('@', '.')
    except (ValueError, TypeError, OverflowError):
        return '—'


def _date(d):
    try: return datetime.strptime(str(d), '%Y-%m-%d').strftime('%d/%m/%Y')
    except (ValueError, TypeError): return str(d)


def _sequence(obs):
    vals=[float(v) for _,v in obs]
    moves=[(b>a)-(b<a) for a,b in zip(vals,vals[1:])]
    if all(m==0 for m in moves): return 'estável'
    if 1 in moves and -1 in moves:
        change='aumento' if vals[-1]>vals[0] else 'redução' if vals[-1]<vals[0] else 'sem variação'
        return f'oscilou; {change} líquido(a) de {_br(abs(vals[-1]-vals[0]))}'
    return ('aumentou' if vals[-1]>vals[0] else 'reduziu') + f' {_br(abs(vals[-1]-vals[0]))}'


def _integrated(records, units):
    """Descreve associações temporais, nunca causalidade ou diagnóstico."""
    data={}
    for key in units:
        obs=[]
        for r in records:
            v=r.get('valores',{}).get(key)
            try:
                if v is not None and math.isfinite(float(v)):
                    obs.append((str(r['data']),float(v)))
            except (TypeError,ValueError): pass
        if obs: data[key]=obs
    result=[]
    if 'ureia' in data and 'creatinina' in data and len(data['ureia'])>=2 and len(data['creatinina'])>=2:
        u=data['ureia']; c=data['creatinina']
        result.append('Função renal — ureia: '+_br(u[0][1])+' → '+_br(u[-1][1])+' mg/dL; creatinina: '+_br(c[0][1])+' → '+_br(c[-1][1])+' mg/dL. As variações podem ser diferentes e não permitem determinar, isoladamente, a causa ou a função renal.')
    if 'hemoglobina' in data and 'leucócitos' in data:
        h=data['hemoglobina']; l=data['leucócitos']
        result.append('Hemograma — hemoglobina: '+_br(h[0][1])+' → '+_br(h[-1][1])+' g/dL; leucócitos: '+_br(l[0][1])+' → '+_br(l[-1][1])+'/mm³. A associação temporal não estabelece infecção nem etiologia de anemia.')
    if 'sódio' in data and 'glicose' in data:
        s=data['sódio']; g=data['glicose']
        result.append('Eletrólitos e glicemia — sódio: '+_br(s[0][1])+' → '+_br(s[-1][1])+' mEq/L; glicose: '+_br(g[0][1])+' → '+_br(g[-1][1])+' mg/dL. Verificar se foram coletados no mesmo momento antes de relacionar os valores.')
    if 'lactato' in data:
        l=data['lactato']; result.append('Lactato — '+', '.join(_date(d)+': '+_br(v)+' mmol/L' for d,v in l)+'. Confirmar valores, horário, tipo de amostra e contexto clínico; lactato isolado não confirma sepse ou hipoperfusão.')
    if 'pcr' in data and 'leucócitos' in data:
        p=data['pcr']; result.append('Inflamação — PCR: '+_br(p[0][1])+' → '+_br(p[-1][1])+' mg/L. Avaliar com leucócitos, sinais clínicos e datas de coleta; alterações isoladas são inespecíficas.')
    if not result:
        result.append('Não há dados suficientes para descrever associações longitudinais pelas regras disponíveis.')
    return result


def gerar_relatorio_profissional(nome, prontuario, registros, metricas, achados):
    registros=sorted([r for r in registros if r.get('prontuario')==prontuario],key=lambda r:(r.get('data',''),r.get('arquivo','')))
    if not registros: raise ValueError('Sem exames para o prontuário selecionado')
    font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    bold='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
    from pathlib import Path
    if Path(font).exists() and 'HospitalDemo' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('HospitalDemo',font))
        pdfmetrics.registerFont(TTFont('HospitalDemoBold',bold))
        pdfmetrics.registerFontFamily('HospitalDemo',normal='HospitalDemo',bold='HospitalDemoBold')
    f='HospitalDemo' if Path(font).exists() else 'Helvetica'
    b='HospitalDemoBold' if Path(font).exists() else 'Helvetica-Bold'
    styles={
      'title':ParagraphStyle('titleDemo',fontName=b,fontSize=16,leading=21,textColor=INK,spaceAfter=7),
      'subtitle':ParagraphStyle('subtitleDemo',fontName=f,fontSize=9,leading=13,textColor=MUTED,spaceAfter=12),
      'heading':ParagraphStyle('headingDemo',fontName=b,fontSize=10.5,leading=14,textColor=INK,spaceBefore=13,spaceAfter=7),
      'body':ParagraphStyle('bodyDemo',fontName=f,fontSize=8,leading=12,spaceAfter=6),
      'small':ParagraphStyle('smallDemo',fontName=f,fontSize=7,leading=10,spaceAfter=5),
      'cell':ParagraphStyle('cellDemo',fontName=f,fontSize=7,leading=10),
      'cellhead':ParagraphStyle('cellheadDemo',fontName=b,fontSize=7,leading=10,textColor=INK),
    }
    buf=io.BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=landscape(A4),leftMargin=1.5*cm,rightMargin=1.5*cm,topMargin=1.7*cm,bottomMargin=1.6*cm)
    def footer(canv,doc):
        canv.saveState()
        w,h=landscape(A4)
        canv.setStrokeColor(colors.HexColor('#cbd5e1'));canv.line(1.5*cm,1.22*cm,w-1.5*cm,1.22*cm)
        canv.setFont(f,7);canv.setFillColor(MUTED)
        canv.drawString(1.5*cm,.85*cm,'DEMONSTRAÇÃO • Não validado para uso clínico • Conferir laudos originais')
        canv.drawRightString(w-1.5*cm,.85*cm,f'Página {doc.page}')
        canv.restoreState()
    P=lambda t,s='body':Paragraph(t,styles[s])
    esc=lambda x:escape(str(x))
    story=[P('RELATÓRIO DE TENDÊNCIA LABORATORIAL','title'),P('Comparação cronológica • Documento demonstrativo para conferência','subtitle')]
    details=[['PACIENTE (FICTÍCIO)', 'PRONTUÁRIO (FICTÍCIO)', 'PERÍODO', 'ARQUIVOS'],
             [str(nome),str(prontuario),_date(registros[0]['data'])+' a '+_date(registros[-1]['data']),str(len(registros))]]
    info=Table([[P(esc(x),'cellhead') for x in details[0]],[P(esc(x),'cell') for x in details[1]]],colWidths=[9*cm,5*cm,7*cm,4.7*cm])
    info.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    story.append(info)
    story.append(P('1. Resultados laboratoriais por data','heading'))
    for start in range(0,len(registros),5):
        group=registros[start:start+5]
        head=[P('Exame / unidade','cellhead')]+[P(esc(_date(r['data']))+'<br/>'+esc('PDF '+str(start+i+1)),'cellhead') for i,r in enumerate(group)]
        rows=[head]
        for metric,(unit,_) in metricas.items():
            values=[r.get('valores',{}).get(metric) for r in group]
            if not any(v is not None for v in values):continue
            rows.append([P(esc(metric.capitalize()+' ('+unit+')'),'cell')]+[P(esc(_br(v)),'cell') for v in values])
        table=Table(rows,colWidths=[6.5*cm]+[19.2*cm/len(group)]*len(group),repeatRows=1,hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PALE),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f8fafc')]),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#d5dee8')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.append(table)
    story.append(P('— significa exame não disponível nesse arquivo; não significa resultado normal ou zero.','small'))
    story.append(P('2. Evolução cronológica','heading'))
    trend=[]
    for metric,(unit,_) in metricas.items():
        obs=[]
        for r in registros:
            v=r.get('valores',{}).get(metric)
            try:
                if v is not None and math.isfinite(float(v)):obs.append((r['data'],float(v)))
            except (ValueError,TypeError):pass
        if len(obs)>=2:
            trend.append([P(esc(metric.capitalize()),'cell'),P(esc(' → '.join(_br(v) for _,v in obs))+' '+esc(unit),'cell'),P(esc(_sequence(obs)),'cell')])
    if trend:
        tab=Table([[P('Parâmetro','cellhead'),P('Sequência dos resultados','cellhead'),P('Comportamento','cellhead')]]+trend,colWidths=[5*cm,11*cm,9.7*cm],repeatRows=1,hAlign='LEFT')
        tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PALE),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#d5dee8')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.append(tab)
    else:story.append(P('Sem duas medições comparáveis para calcular tendências.'))
    story.append(P('3. Síntese integrada da evolução','heading'))
    for item in _integrated(registros,metricas):story.append(P('• '+esc(item)))
    story.append(P('4. Achados e hipóteses da triagem automática','heading'))
    visible=[a for a in achados if a.get('nivel')!='tendência']
    if not visible:story.append(P('Nenhum achado sinalizado pelas regras disponíveis. Isso não exclui alterações.'))
    for a in visible:
        lines=[P('<b>'+esc(a.get('titulo','Achado'))+'</b>')]
        for label,key in [('Evidência','evidencia'),('Hipótese','interpretacao'),('Conferir','verificar')]:
            if a.get(key):lines.append(P('<b>'+label+':</b> '+esc(a[key]),'small'))
        story.append(KeepTogether(lines))
    story.append(P('5. Alertas para conferência e limitações','heading'))
    for r in registros:
        lact=r.get('valores',{}).get('lactato')
        try:
            if lact is not None and float(lact)>=4:
                story.append(P('<b>ATENÇÃO — Lactato de '+esc(_br(lact))+' mmol/L em '+esc(_date(r['data']))+'.</b> Conferir imediatamente no laudo original. Se confirmado em paciente real, requer avaliação clínica urgente.'))
        except (ValueError,TypeError):pass
    story.append(P('A extração dos PDFs é experimental. Verifique identidade, data e hora de coleta, tipo de amostra, unidades, valores e referências antes de interpretar. Resultados de dias diferentes não são simultâneos. Não há inferência automática de causalidade, diagnóstico definitivo ou conduta.'))
    story.append(P('<b>Fontes:</b> '+esc('; '.join(_date(r['data'])+' — '+str(r.get('arquivo','arquivo sem nome')) for r in registros)),'small'))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return buf.getvalue()
