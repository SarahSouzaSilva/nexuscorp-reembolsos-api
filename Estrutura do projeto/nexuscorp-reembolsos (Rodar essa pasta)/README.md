Relatório do projeto  
   
# NexusCorp — Plataforma de Gestão de Reembolsos Corporativos (API)  
   
API REST desenvolvida para centralizar o registro, análise, aprovação e pagamento de reembolsos corporativos da NexusCorp, aplicando controle de acesso baseado em perfis (RBAC), escopo departamental e rastreabilidade completa de auditoria.  
   
## Tecnologias Utilizadas  
* **Linguagem:** Python 3  
* **Framework Web:** FastAPI  
* **Banco de Dados:** SQLite (`nexuscorp.db`) com SQLAlchemy  
* **Autenticação e Segurança:** OAuth2 com JWT (JSON Web Tokens) e hash de senhas (`bcrypt`/`passlib`)  
* **Documentação Interativa:** Swagger UI (`/docs`)  
   
---  
   
## Como Executar o Projeto  
   
1. Clone o repositório e acesse a pasta do projeto:  
   ```bash  
   git clone <URL_DO_SEU_REPOSITORIO>  
   cd nexuscorp-reembolsos  
   ```  
2. Crie e ative o ambiente virtual:  
   ```bash  
   python -m venv .venv  
   # Windows:  
   .\.venv\Scripts\activate  
   # Linux/Mac:  
   source .venv/bin/activate  
   ```  
3. Instale as dependências e inicie o servidor:  
   ```bash  
   pip install -r requirements.txt  
   uvicorn main:app --reload  
   ```  
4. Acesse a documentação interativa no navegador: `http://127.0.0`  
   
---  
   
## Modelo de Dados  
O banco de dados persistente é estruturado em 4 entidades principais:  
* **Departamento (`departamentos`):** `id`, `nome`, `centro_custo`  
* **Usuário (`usuarios`):** `id`, `nome`, `email`, `senha_hash`, `perfil` (*COLABORADOR*, *GESTOR*, *FINANCEIRO*), `departamento_id`  
* **Solicitação de Reembolso (`solicitacoes`):** `id`, `solicitante_id`, `departamento_id`, `categoria`, `valor`, `data_despesa`, `justificativa`, `referencia_comprovante`, `situacao`, `criado_em`  
* **Histórico de Análise (`historico_analise`):** `id`, `solicitacao_id`, `responsavel_id`, `etapa`, `decisao`, `observacao`, `data_hora`  
   
---  
   
## Matriz de Permissões (RBAC e Escopo)  
   
| Operação / Rota | Colaborador | Gestor | Financeiro | Regra de Restrição |  
| :--- | :---: | :---: | :---: | :--- |  
| `POST /auth/login` | Sim | Sim | Sim | Pública (gera token JWT) |  
| `PATCH /usuarios/me` | Parcial | Parcial | Parcial | Altera apenas dados básicos; bloqueia alteração de `perfil` ou `departamento_id` |  
| `POST /reembolsos` | Sim | Sim | Sim | Vinculada automaticamente ao usuário e departamento logados |  
| `GET /reembolsos` | Próprias | Departamento | Todas | Isolamento de dados por titularidade e departamento |  
| `PUT / DELETE /reembolsos/{id}` | Próprias | Não | Não | Permitido apenas enquanto a situação for `RASCUNHO` |  
| `POST /reembolsos/{id}/enviar` | Próprias | Não | Não | Altera status para `AGUARDANDO_GESTOR` e bloqueia edições |  
| `POST /reembolsos/{id}/analisar-gestor` | Não | Departamento | Não | Bloqueia autoaprovação e solicitações de outros departamentos |  
| `POST /reembolsos/{id}/analisar-financeiro` | Não | Não | Sim | Exige aprovação prévia do gestor (`AGUARDANDO_FINANCEIRO`) |  
| `POST /reembolsos/{id}/pagar` | Não | Não | Sim | Exige status `APROVADA`; registra conclusão como `PAGA` |  
   
---  
   
## Regras de Negócio e Decisões de Segurança  
* **Autenticação Stateless (JWT) e Hash:** Senhas nunca são armazenadas em texto puro ou retornadas nos contratos de saída (`schemas.py`). Tokens possuem tempo de expiração validado a cada requisição (RN01, RN13, RN14).  
* **Prevenção de Escalonamento de Privilégio:** O schema de atualização de perfil próprio ignora/bloqueia alterações nos campos `perfil` e `departamento_id` (RN15).  
* **Integridade de Fluxo e Auditoria:** Toda transição de estado (`RASCUNHO` -> `AGUARDANDO_GESTOR` -> `AGUARDANDO_FINANCEIRO` -> `APROVADA` -> `PAGA` ou `RECUSADA`) grava um registro imutável na tabela `historico_analise` com o ID do responsável e timestamp (RN07, RN08, RN12).  
* **Validações de Despesa:** Bloqueio de valores `<= 0` (RN04), datas futuras (RN06), duplicidade de comprovante (RN05) e exigência de justificativa em recusas (RN11).  
   
---  
   
## Índice de Evidências de Teste (Homologação)  
As evidências visuais de execução estão organizadas na pasta `/evidencias` (e no arquivo `.zip` anexo):  
* **Cenário 01 (Acesso indevido entre colaboradores):** Pasta `4`  
* **Cenário 02 (Bloqueio de gestor de outro departamento):** Pasta `10`  
* **Cenário 03 (Bloqueio de credenciais incorretas):** Pasta `17`  
* **Cenário 04 (Tentativa de alteração de permissões):** Pasta `19`  
* **Cenário 05 (Aprovação financeira fora da sequência):** Pasta `14`  
* **Cenário 06 (Tentativa de edição após envio):** Pasta `8`  
* **Cenário 07 (Consulta com filtros e escopo departamental):** Pasta `11`  
* **Cenário 08 (Fluxo completo até pagamento e histórico):** Pastas `12`, `15` e `18`  
