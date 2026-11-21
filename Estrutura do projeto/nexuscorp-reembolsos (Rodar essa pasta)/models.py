import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base

class PerfilEnum(str, enum.Enum):
    COLABORADOR = "COLABORADOR"
    GESTOR = "GESTOR"
    FINANCEIRO = "FINANCEIRO"

class CategoriaEnum(str, enum.Enum):
    ALIMENTACAO = "ALIMENTACAO"
    TRANSPORTE = "TRANSPORTE"
    HOSPEDAGEM = "HOSPEDAGEM"
    MATERIAIS = "MATERIAIS"

class SituacaoEnum(str, enum.Enum):
    RASCUNHO = "RASCUNHO"
    AGUARDANDO_GESTOR = "AGUARDANDO_GESTOR"
    AGUARDANDO_FINANCEIRO = "AGUARDANDO_FINANCEIRO"
    APROVADA = "APROVADA"
    PAGA = "PAGA"
    RECUSADA = "RECUSADA"

class Departamento(Base):
    __tablename__ = "departamentos"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), unique=True, nullable=False)

    usuarios = relationship("Usuario", back_populates="departamento")

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    senha_hash = Column(String(255), nullable=False)
    perfil = Column(Enum(PerfilEnum), nullable=False, default=PerfilEnum.COLABORADOR)
    departamento_id = Column(Integer, ForeignKey("departamentos.id"), nullable=False)

    departamento = relationship("Departamento", back_populates="usuarios")
    solicitacoes = relationship("SolicitacaoReembolso", back_populates="solicitante")

class SolicitacaoReembolso(Base):
    __tablename__ = "solicitacoes_reembolso"

    id = Column(Integer, primary_key=True, index=True)
    solicitante_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    departamento_id = Column(Integer, ForeignKey("departamentos.id"), nullable=False)
    categoria = Column(Enum(CategoriaEnum), nullable=False)
    valor = Column(Float, nullable=False)
    data_despesa = Column(Date, nullable=False)
    justificativa = Column(String(500), nullable=False)
    referencia_comprovante = Column(String(100), nullable=False)
    situacao = Column(Enum(SituacaoEnum), nullable=False, default=SituacaoEnum.RASCUNHO)
    criado_em = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # RN05: Impede duplicidade de comprovante por colaborador no nível do banco
    __table_args__ = (
        UniqueConstraint("solicitante_id", "referencia_comprovante", name="uq_solicitante_comprovante"),
    )

    solicitante = relationship("Usuario", back_populates="solicitacoes")
    departamento = relationship("Departamento")
    historico = relationship("HistoricoAnalise", back_populates="solicitacao", cascade="all, delete-orphan")

class HistoricoAnalise(Base):
    __tablename__ = "historico_analises"

    id = Column(Integer, primary_key=True, index=True)
    solicitacao_id = Column(Integer, ForeignKey("solicitacoes_reembolso.id"), nullable=False)
    responsavel_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    etapa = Column(String(50), nullable=False)
    decisao = Column(String(50), nullable=False)
    observacao = Column(String(500), nullable=True)
    data_hora = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    solicitacao = relationship("SolicitacaoReembolso", back_populates="historico")
    responsavel = relationship("Usuario")
