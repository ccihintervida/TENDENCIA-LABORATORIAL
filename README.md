# Tendência Laboratorial — DEMO (somente dados fictícios)

## Publicação gratuita
1. Crie uma conta em https://github.com e um repositório **privado** chamado `tendencia-laboratorial-demo`.
2. Envie `app.py` e `requirements.txt` para a raiz do repositório (Add file > Upload files > Commit changes).
3. Entre em https://share.streamlit.io e conecte sua conta GitHub.
4. Clique em Create app > Yup, I have an app. Selecione repositório, branch `main` e arquivo `app.py`.
5. Em Advanced settings > Secrets, configure:

   APP_USER = "seu_usuario_teste"
   APP_PASSWORD = "uma_senha_longa_unica"

   Nunca coloque a senha no repositório.
6. Clique em Deploy e configure o compartilhamento como privado, se disponível. Entre com o usuário e senha escolhidos.

## Como testar
Cadastre `Paciente Teste` e prontuário `TESTE001`. Envie um PDF de exame **fictício**, confira e corrija os resultados extraídos e salve. Repita com outra data; abra Tendência para comparar.

## Limitações importantes
- Dados ficam apenas na sessão de execução; não há banco de dados persistente. Use Backup / restaurar para baixar JSON e restaurar quando voltar. O backup JSON contém os valores e metadados, **não** os PDFs originais.
- A extração por expressões regulares é experimental e pode confundir resultados; confira todos os campos.
- PDFs escaneados sem texto não são lidos automaticamente.
- Não oferece interpretação médica automatizada; apenas tendência numérica.
- Não use com dados reais de pacientes. Para produção: banco persistente, armazenamento de PDFs, criptografia, política de retenção, logs, backups, autenticação robusta, adequação à LGPD e validação clínica.
