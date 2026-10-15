# Sistema de Tendência Laboratorial — MVP

Aplicação web em português para cadastrar pacientes, pesquisar por nome/prontuário, armazenar PDFs e comparar resultados laboratoriais em datas diferentes.

## Instalação

Requer Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
export APP_USER=admin
export APP_PASSWORD='COLOQUE_UMA_SENHA_FORTE_AQUI'
uvicorn app:app --host 127.0.0.1 --port 8000
```

Abra `http://127.0.0.1:8000` no navegador. No Windows PowerShell use `$env:APP_PASSWORD="..."` e `$env:APP_USER="admin"`.

## Fluxo

1. Cadastre nome e número de prontuário.
2. Abra o paciente e envie um PDF.
3. Confira a data de coleta, abra o PDF original e corrija valores pela seção de conferência. Marque como conferido.
4. Nos dias seguintes, pesquise o prontuário e importe novos PDFs.
5. Veja os valores anteriores e atuais com tendências numéricas.

Os dados ficam em `dados/app.sqlite3` e os arquivos em `dados/arquivos/`. Faça backup **protegido** da pasta `dados` regularmente.

## Limitações importantes

- Protótipo, **não homologado para uso clínico ou produção**. A extração por texto é limitada a certos formatos de laudo e pode omitir, confundir ou sobrescrever valores, sobretudo em PDFs com várias datas, gasometrias e múltiplos materiais. Não suporta OCR de PDFs escaneados.
- Não oferece interpretação médica por IA; oferece **comparação numérica e alertas simples**. Não estabelece diagnóstico ou conduta. A direção da mudança nem sempre equivale a melhora/piora clínica.
- O cadastro não confirma automaticamente que o PDF pertence ao paciente; o operador deve conferir o nome e o prontuário no laudo.
- Não há segregação por profissional, trilha de auditoria imutável, consentimento, criptografia dos dados em repouso, retenção configurável nem controle granular de acesso.
- **Não publique este servidor diretamente na internet.** Para ambiente real com dados de pacientes é necessário HTTPS, autenticação robusta e perfis de acesso, backups criptografados, logs/auditoria, política de retenção e exclusão, análise de risco, avaliação de LGPD e validação técnica/clínica. Considere infraestrutura profissional e responsável técnico.
- Não utilize a senha padrão de exemplos. Execute atrás de um proxy HTTPS apenas após endurecimento de segurança.

## Tecnologias

FastAPI, SQLite, PyMuPDF, HTML/CSS; sem dependência de serviços de IA externos. Todos os PDFs ficam no armazenamento do servidor escolhido.
