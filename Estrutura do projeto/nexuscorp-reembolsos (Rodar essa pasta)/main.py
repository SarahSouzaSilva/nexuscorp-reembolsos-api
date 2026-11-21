from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database import engine, Base, get_db, SessionLocal
from models import (
    Departamento, Usuario, SolicitacaoReembolso, HistoricoAnalise,
    PerfilEnum, CategoriaEnum, SituacaoEnum
)
from schemas import (
    Token, UsuarioCreate, UsuarioUpdate, UsuarioOut,
    SolicitacaoCreate, SolicitacaoUpdate, SolicitacaoOut, DecisaoRequest
)
from security import (
    gerar_hash_senha, verificar_senha, criar_token_acesso,
    get_usuario_atual, oauth2_scheme, REVOKED_TOKENS
)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="NexusCorp — API de Gestão de Reembolsos Corporativos",
    description="API REST para controle de despesas, fluxos de aprovação e auditoria com RBAC.",
    version="1.0.0"
)


# --- SEED INICIAL PARA HOMOLOGAÇÃO (CENÁRIOS 01 A 08) ---
def inicializar_dados_teste():
    db = SessionLocal()
    try:
        if db.query(Departamento).count() == 0:
            dep_comercial = Departamento(nome="Comercial")
            dep_tech = Departamento(nome="Tecnologia")
            dep_fin = Departamento(nome="Financeiro")
            db.add_all([dep_comercial, dep_tech, dep_fin])
            db.commit()

            usuarios = [
                Usuario(nome="Ana Silva", email="ana@nexuscorp.com", senha_hash=gerar_hash_senha("senha123"),
                        perfil=PerfilEnum.COLABORADOR, departamento_id=dep_comercial.id),
                Usuario(nome="Bruno Costa", email="bruno@nexuscorp.com", senha_hash=gerar_hash_senha("senha123"),
                        perfil=PerfilEnum.COLABORADOR, departamento_id=dep_tech.id),
                Usuario(nome="Patrícia Souza", email="patricia@nexuscorp.com", senha_hash=gerar_hash_senha("senha123"),
                        perfil=PerfilEnum.GESTOR, departamento_id=dep_comercial.id),
                Usuario(nome="Carlos Mendes", email="carlos@nexuscorp.com", senha_hash=gerar_hash_senha("senha123"),
                        perfil=PerfilEnum.GESTOR, departamento_id=dep_tech.id),
                Usuario(nome="Fernanda Lima", email="fernanda@nexuscorp.com", senha_hash=gerar_hash_senha("senha123"),
                        perfil=PerfilEnum.FINANCEIRO, departamento_id=dep_fin.id),
            ]
            db.add_all(usuarios)
            db.commit()
    finally:
        db.close()


inicializar_dados_teste()


def registrar_historico(db: Session, solicitacao_id: int, responsavel_id: int, etapa: str, decisao: str,
                        observacao: Optional[str] = None):
    registro = HistoricoAnalise(
        solicitacao_id=solicitacao_id,
        responsavel_id=responsavel_id,
        etapa=etapa,
        decisao=decisao,
        observacao=observacao
    )
    db.add(registro)


# ==========================================
# 1. AUTENTICAÇÃO E USUÁRIOS
# ==========================================

@app.post("/auth/login", response_model=Token, tags=["Autenticação"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Cenário 03: Mensagem genérica para não expor se o e-mail existe ou se a senha errou
    usuario = db.query(Usuario).filter(Usuario.email == form_data.username).first()
    if not usuario or not verificar_senha(form_data.password, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = criar_token_acesso(data={"sub": str(usuario.id), "perfil": usuario.perfil.value})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["Autenticação"])
def logout(token: str = Depends(oauth2_scheme), usuario: Usuario = Depends(get_usuario_atual)):
    # RN14: Invalida o token atual
    REVOKED_TOKENS.add(token)
    return None


@app.post("/usuarios", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED, tags=["Usuários"])
def cadastrar_usuario(dados: UsuarioCreate, db: Session = Depends(get_db)):
    dep = db.query(Departamento).filter(Departamento.id == dados.departamento_id).first()
    if not dep:
        raise HTTPException(status_code=404, detail="Departamento não encontrado.")

    # RN15: Todo cadastro comum nasce estritamente como COLABORADOR
    novo = Usuario(
        nome=dados.nome,
        email=dados.email,
        senha_hash=gerar_hash_senha(dados.senha),
        perfil=PerfilEnum.COLABORADOR,
        departamento_id=dados.departamento_id
    )
    try:
        db.add(novo)
        db.commit()
        db.refresh(novo)
        return novo
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")


@app.patch("/usuarios/me", response_model=UsuarioOut, tags=["Usuários"])
def atualizar_perfil_proprio(dados: UsuarioUpdate, db: Session = Depends(get_db),
                             usuario: Usuario = Depends(get_usuario_atual)):
    # RN15 & Cenário 04: Campos extra como 'perfil' ou 'departamento_id' são ignorados pelo schema
    if dados.nome:
        usuario.nome = dados.nome
    db.commit()
    db.refresh(usuario)
    return usuario


# ==========================================
# 2. GESTÃO DE REEMBOLSOS (COLABORADOR)
# ==========================================

@app.post("/reembolsos", response_model=SolicitacaoOut, status_code=status.HTTP_201_CREATED, tags=["Reembolsos"])
def criar_solicitacao(dados: SolicitacaoCreate, db: Session = Depends(get_db),
                      usuario: Usuario = Depends(get_usuario_atual)):
    # RN05: Verificar duplicidade de comprovante para o mesmo colaborador
    duplicada = db.query(SolicitacaoReembolso).filter(
        SolicitacaoReembolso.solicitante_id == usuario.id,
        SolicitacaoReembolso.referencia_comprovante == dados.referencia_comprovante
    ).first()
    if duplicada:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Já existe uma despesa registrada por você com esta referência de comprovante (RN05)."
        )

    nova = SolicitacaoReembolso(
        solicitante_id=usuario.id,
        departamento_id=usuario.departamento_id,
        categoria=dados.categoria,
        valor=dados.valor,
        data_despesa=dados.data_despesa,
        justificativa=dados.justificativa,
        referencia_comprovante=dados.referencia_comprovante,
        situacao=SituacaoEnum.RASCUNHO
    )
    db.add(nova)
    db.flush()
    registrar_historico(db, nova.id, usuario.id, "CRIACAO", "RASCUNHO_CRIADO", "Solicitação iniciada em rascunho.")
    db.commit()
    db.refresh(nova)
    return nova


@app.get("/reembolsos", response_model=List[SolicitacaoOut], tags=["Reembolsos"])
def listar_solicitacoes(
        departamento_id: Optional[int] = Query(None),
        situacao: Optional[SituacaoEnum] = Query(None),
        categoria: Optional[CategoriaEnum] = Query(None),
        db: Session = Depends(get_db),
        usuario: Usuario = Depends(get_usuario_atual)
):
    query = db.query(SolicitacaoReembolso)

    # Aplicação rigorosa de escopo por perfil (RN02, RN03, Cenário 07)
    if usuario.perfil == PerfilEnum.COLABORADOR:
        query = query.filter(SolicitacaoReembolso.solicitante_id == usuario.id)
    elif usuario.perfil == PerfilEnum.GESTOR:
        # Gestor só enxerga o próprio departamento (ignora filtro externo de outro dept)
        query = query.filter(SolicitacaoReembolso.departamento_id == usuario.departamento_id)
    elif usuario.perfil == PerfilEnum.FINANCEIRO:
        # Financeiro visualiza solicitações que chegaram à sua etapa ou já passaram por ela (ou próprias)
        if departamento_id is not None:
            query = query.filter(SolicitacaoReembolso.departamento_id == departamento_id)

    if situacao is not None:
        query = query.filter(SolicitacaoReembolso.situacao == situacao)
    if categoria is not None:
        query = query.filter(SolicitacaoReembolso.categoria == categoria)

    return query.all()


@app.get("/reembolsos/{solicitacao_id}", response_model=SolicitacaoOut, tags=["Reembolsos"])
def obter_solicitacao(solicitacao_id: int, db: Session = Depends(get_db),
                      usuario: Usuario = Depends(get_usuario_atual)):
    sol = db.query(SolicitacaoReembolso).filter(SolicitacaoReembolso.id == solicitacao_id).first()
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")

    # RN02 & Cenário 01: Bloqueio de acesso indevido sem revelar detalhes
    if usuario.perfil == PerfilEnum.COLABORADOR and sol.solicitante_id != usuario.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado a esta solicitação.")
    if usuario.perfil == PerfilEnum.GESTOR and sol.departamento_id != usuario.departamento_id and sol.solicitante_id != usuario.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Acesso negado: solicitação pertence a outro departamento.")

    return sol


@app.delete("/reembolsos/{solicitacao_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Reembolsos"])
def excluir_solicitacao(solicitacao_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    sol = db.query(SolicitacaoReembolso).filter(SolicitacaoReembolso.id == solicitacao_id).first()
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if sol.solicitante_id != usuario.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas o solicitante pode excluir esta solicitação.")
    if sol.situacao != SituacaoEnum.RASCUNHO:
        raise HTTPException(status_code=422, detail="Somente solicitações em rascunho podem ser excluídas.")

    db.delete(sol)
    db.commit()
    return None

@app.post("/reembolsos/{solicitacao_id}/enviar", response_model=SolicitacaoOut, tags=["Reembolsos"])
def enviar_para_gestor(solicitacao_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    sol = db.query(SolicitacaoReembolso).filter(SolicitacaoReembolso.id == solicitacao_id).first()
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if sol.solicitante_id != usuario.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas o solicitante pode enviar esta solicitação.")
    if sol.situacao != SituacaoEnum.RASCUNHO:
        raise HTTPException(status_code=422, detail="A solicitação já foi enviada ou encerrada.")

    sol.situacao = SituacaoEnum.AGUARDANDO_GESTOR
    registrar_historico(db, sol.id, usuario.id, "ENVIO", "ENVIADA_PARA_GESTOR", "Encaminhada para análise do gestor.")
    db.commit()
    db.refresh(sol)
    return sol

# ==========================================
# 3. FLUXO DE APROVAÇÃO E PAGAMENTO
# ==========================================

@app.post("/reembolsos/{solicitacao_id}/analise-gestor", response_model=SolicitacaoOut, tags=["Fluxo de Aprovação"])
def analisar_como_gestor(solicitacao_id: int, decisao: DecisaoRequest, db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    if usuario.perfil != PerfilEnum.GESTOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operação restrita ao perfil GESTOR.")

    sol = db.query(SolicitacaoReembolso).filter(SolicitacaoReembolso.id == solicitacao_id).first()
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")

    if sol.departamento_id != usuario.departamento_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Gestor não possui responsabilidade sobre este departamento (RN03).")

    if sol.solicitante_id == usuario.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Não é permitido analisar a própria solicitação (RN09).")

    if sol.situacao != SituacaoEnum.AGUARDANDO_GESTOR:
        raise HTTPException(status_code=422, detail=f"Transição inválida: situação atual é '{sol.situacao.value}'.")

    if not decisao.aprovar and (not decisao.observacao or not decisao.observacao.strip()):
        raise HTTPException(status_code=422, detail="A recusa exige uma justificativa obrigatória (RN11).")

    if decisao.aprovar:
        sol.situacao = SituacaoEnum.AGUARDANDO_FINANCEIRO
        status_decisao = "APROVADA_PELO_GESTOR"
    else:
        sol.situacao = SituacaoEnum.RECUSADA
        status_decisao = "RECUSADA_PELO_GESTOR"

    registrar_historico(db, sol.id, usuario.id, "ANALISE_GESTOR", status_decisao, decisao.observacao)
    db.commit()
    db.refresh(sol)
    return sol

@app.post("/reembolsos/{solicitacao_id}/analise-financeiro", response_model=SolicitacaoOut, tags=["Fluxo de Aprovação"])
def analisar_como_financeiro(solicitacao_id: int, decisao: DecisaoRequest, db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    if usuario.perfil != PerfilEnum.FINANCEIRO:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operação restrita ao perfil FINANCEIRO.")

    sol = db.query(SolicitacaoReembolso).filter(SolicitacaoReembolso.id == solicitacao_id).first()
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")

    if sol.solicitante_id == usuario.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Não é permitido analisar a própria solicitação (RN09).")

    if sol.situacao != SituacaoEnum.AGUARDANDO_FINANCEIRO:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Aprovação fora da sequência: situação atual é '{sol.situacao.value}' (RN08)."
        )

    if not decisao.aprovar and (not decisao.observacao or not decisao.observacao.strip()):
        raise HTTPException(status_code=422, detail="A recusa exige uma justificativa obrigatória (RN11).")

    if decisao.aprovar:
        sol.situacao = SituacaoEnum.APROVADA
        status_decisao = "APROVADA_PELO_FINANCEIRO"
    else:
        sol.situacao = SituacaoEnum.RECUSADA
        status_decisao = "RECUSADA_PELO_FINANCEIRO"

    registrar_historico(db, sol.id, usuario.id, "ANALISE_FINANCEIRO", status_decisao, decisao.observacao)
    db.commit()
    db.refresh(sol)
    return sol

@app.post("/reembolsos/{solicitacao_id}/pagar", response_model=SolicitacaoOut, tags=["Fluxo de Aprovação"])
def registrar_pagamento(solicitacao_id: int, observacao: Optional[str] = "Pagamento efetuado.", db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    if usuario.perfil != PerfilEnum.FINANCEIRO:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operação restrita ao perfil FINANCEIRO.")

    sol = db.query(SolicitacaoReembolso).filter(SolicitacaoReembolso.id == solicitacao_id).first()
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")

    if sol.situacao != SituacaoEnum.APROVADA:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Pagamento não permitido na situação '{sol.situacao.value}' (RN10)."
        )

    sol.situacao = SituacaoEnum.PAGA
    registrar_historico(db, sol.id, usuario.id, "PAGAMENTO", "PAGA", observacao)
    db.commit()
    db.refresh(sol)
    return sol

@app.put("/reembolsos/{solicitacao_id}", response_model=SolicitacaoOut, tags=["Reembolsos"])
def editar_solicitacao(solicitacao_id: int, dados: SolicitacaoUpdate, db: Session = Depends(get_db), usuario: Usuario = Depends(get_usuario_atual)):
    sol = db.query(SolicitacaoReembolso).filter(SolicitacaoReembolso.id == solicitacao_id).first()
    if not sol:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada.")
    if sol.solicitante_id != usuario.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas o solicitante pode editar esta solicitação.")
    if sol.situacao != SituacaoEnum.RASCUNHO:
        raise HTTPException(status_code=422, detail=f"Não é permitido alterar solicitação na situação '{sol.situacao.value}' (RN07).")
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(sol, campo, valor)
    db.commit()
    db.refresh(sol)
    return sol
