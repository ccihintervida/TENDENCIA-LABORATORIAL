"""Regras de TRIAGEM LABORATORIAL para demonstração, não diagnóstico clínico."""
from collections import defaultdict

LIMITS = {
 'sódio': (135,145,'mmol/L'), 'potássio': (3.5,5.0,'mmol/L'),
 'leucócitos': (4000,11000,'/mm³'), 'plaquetas': (150000,450000,'/mm³'),
 'lactato': (0.5,2.2,'mmol/L'), 'magnésio': (1.6,2.6,'mg/dL'),
 'bicarbonato': (22,29,'mmol/L'), 'ph': (7.35,7.45,''),
 'glicose': (70,140,'mg/dL'), 'cálcio ionizado': (1.10,1.35,'mmol/L'),
}

def latest(records, name):
    entries=[(r['data'],r['valores'][name]) for r in records if name in r.get('valores',{})]
    return entries[-1] if entries else None

def analyze(records, sex='não informado'):
    """Retorna achados e hipóteses, sem fechar diagnóstico e sem prescrever conduta."""
    records=sorted(records,key=lambda r:(r['data'],r.get('arquivo','')))
    out=[]
    def add(level, title, evidence, explanation, missing=''):
        out.append(dict(nivel=level,titulo=title,evidencia=evidence,interpretacao=explanation,verificar=missing))
    values={k:latest(records,k) for k in set().union(*(r.get('valores',{}).keys() for r in records))} if records else {}
    def v(key): return values.get(key,(None,None))[1] if values.get(key) else None
    na,k,cr,ur,glu=v('sódio'),v('potássio'),v('creatinina'),v('ureia'),v('glicose')
    hb,wbc,plt,lac,mg=v('hemoglobina'),v('leucócitos'),v('plaquetas'),v('lactato'),v('magnésio')
    ph,hco3,pco2=v('ph'),v('bicarbonato'),v('pco2')
    if na is not None:
        if na<135:
            sev='grave' if na<125 else ('moderada' if na<130 else 'leve')
            add('atenção' if na>=125 else 'prioritário',f'Hiponatremia laboratorial ({sev})',f'Sódio {na:g} mmol/L', 'A causa não é determinada pelo sódio isolado. Hiperglicemia pode reduzir o sódio medido; avaliar tonicidade e estado volêmico.', 'Conferir se o sódio é sérico/plasmático; glicemia, osmolaridade, medicamentos e horários das coletas.')
        elif na>145: add('atenção','Hipernatremia laboratorial',f'Sódio {na:g} mmol/L','Pode estar associada a desequilíbrio de água corporal; a causa exige contexto.','Estado volêmico, perdas hídricas e medicações.')
    if k is not None:
        if k>5.0: add('prioritário' if k>=6 else 'atenção','Hipercalemia laboratorial',f'Potássio {k:g} mmol/L','Pode ocorrer com redução da excreção renal, medicamentos, alterações ácido-base ou hemólise da amostra.','Confirmar hemólise, função renal, medicamentos e ECG conforme avaliação clínica.')
        elif k<3.5: add('prioritário' if k<2.5 else 'atenção','Hipocalemia laboratorial',f'Potássio {k:g} mmol/L','Pode se relacionar a perdas, redistribuição ou medicamentos.','Magnésio, perdas digestivas/renais, medicamentos e ECG conforme avaliação clínica.')
    if wbc is not None and wbc>11000: add('atenção','Leucocitose',f'Leucócitos {wbc:,.0f}/mm³','Achado inespecífico, que pode ocorrer em infecção, inflamação, estresse ou outras situações.','Diferencial leucocitário, sintomas, sinais vitais e contexto.')
    if wbc is not None and wbc<4000: add('atenção','Leucopenia',f'Leucócitos {wbc:,.0f}/mm³','A interpretação depende do diferencial e do contexto.','Neutrófilos absolutos, medicamentos e quadro clínico.')
    if plt is not None and plt<150000: add('prioritário' if plt<50000 else 'atenção','Plaquetopenia',f'Plaquetas {plt:,.0f}/mm³','A etiologia não pode ser inferida apenas pela contagem.','Hemograma prévio, esfregaço, medicamentos e coagulação.')
    if hb is not None and hb<11: add('atenção','Hemoglobina reduzida — possível anemia',f'Hemoglobina {hb:g} g/dL','O limiar diagnóstico depende de sexo, idade, gestação e condições clínicas.','VCM, ferritina, reticulócitos e contexto.')
    if lac is not None and lac>2.2: add('prioritário' if lac>=4 else 'atenção','Hiperlactatemia',f'Lactato {lac:g} mmol/L','Pode ter múltiplas causas e, isoladamente, não confirma sepse ou hipoperfusão.','Condições da coleta, tendência, sinais vitais, perfusão e quadro clínico.')
    if ph is not None:
        if ph<7.35: add('atenção','Acidemia',f'pH {ph:g}','Classificar o distúrbio ácido-base exige pCO₂ e bicarbonato, com identificação da amostra.','Tipo de amostra (arterial/venosa), pCO₂ e bicarbonato.')
        elif ph>7.45: add('atenção','Alcalemia',f'pH {ph:g}','Classificar o distúrbio ácido-base exige pCO₂ e bicarbonato, com identificação da amostra.','Tipo de amostra (arterial/venosa), pCO₂ e bicarbonato.')
    if na is not None and glu is not None and na<135 and glu>200:
        corrected=na+1.6*((glu-100)/100)
        add('correlação','Hiponatremia associada à hiperglicemia',f'Sódio {na:g} mmol/L; glicose {glu:g} mg/dL; sódio corrigido estimado ≈ {corrected:.1f} mmol/L','A hiperglicemia pode explicar parte da redução do sódio medido. O fator de correção é aproximado e varia com a glicemia.','Confirmar mesma coleta, osmolaridade e avaliação clínica.')
    if k is not None and k>5.0 and cr is not None and cr>1.3:
        add('correlação','Hipercalemia e creatinina elevada',f'Potássio {k:g} mmol/L; creatinina {cr:g} mg/dL','Comprometimento da excreção renal é uma hipótese, não uma causa confirmada. Creatinina isolada não estabelece lesão renal aguda.','Creatinina basal, diurese, intervalo temporal, medicamentos e hemólise.')
    if lac is not None and lac>2.2 and hco3 is not None and hco3<22:
        add('correlação','Lactato elevado com bicarbonato reduzido',f'Lactato {lac:g} mmol/L; HCO₃ {hco3:g} mmol/L','O lactato pode contribuir para acidose metabólica; sem pH, pCO₂ e contexto, não é possível caracterizar o distúrbio completamente.','Confirmar mesma coleta, tipo de gasometria e eletrólitos para ânion gap.')
    if wbc is not None and wbc>11000 and lac is not None and lac>2.2:
        add('correlação','Leucocitose associada à hiperlactatemia',f'Leucócitos {wbc:,.0f}/mm³; lactato {lac:g} mmol/L','Combinação inespecífica que merece avaliação contextual; não diagnostica infecção, sepse ou choque.','Sinais vitais, foco infeccioso, perfusão, medicamentos e evolução.')
    for name in ['creatinina','ureia','hemoglobina','leucócitos','plaquetas','lactato','sódio','potássio','pcr']:
        seq=[(r['data'],r['valores'][name]) for r in records if name in r.get('valores',{})]
        if len(seq)>=2:
            a,b=seq[0],seq[-1]
            trend='aumento' if b[1]>a[1] else ('redução' if b[1]<a[1] else 'estabilidade')
            add('tendência',f'{name.capitalize()}: {trend}',f'{a[0]}: {a[1]:g} → {b[0]}: {b[1]:g}', 'Variação numérica; não implica, por si só, melhora ou piora clínica.','Conferir intervalos entre coletas, amostra e referência.')
    return out
