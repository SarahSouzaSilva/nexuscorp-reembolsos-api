from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator
from models import PerfilEnum, CategoriaEnum, SituacaoEnum

# --- Auth & Usuário ---
class Token(BaseModel):
    access_token: str
    token_type: str

class UsuarioCreate(BaseModel):
    nome: str = Field(..., min_length=3, max_length=150)
    email: EmailStr
    senha: str = Field(..., min_length=6)
    departamento_id: int
    # RN15: Cadastro comum não permite definir perfil privilegiado livremente

class UsuarioUpdate(BaseModel):
    nome: Optional[str] = Field(None, min_length=3, max_length=150)
    # RN15: Campos perfil e departamento_id omitidos propositalmente para impedir escalonamento

class UsuarioOut(BaseModel):
    id: int
    nome: str
    email: EmailStr
    perfil: PerfilEnum
    departamento_id: int
    # RN13: senha_hash nunca é exposta

    class Config:
        from_attributes = True

# --- Solicitações ---
class SolicitacaoCreate(BaseModel):
    categoria: CategoriaEnum
    valor: float = Field(..., gt=0, description="RN04: Deve ser maior que zero")
    data_despesa: date
    justificativa: str = Field(..., min_length=5, max_length=500)
    referencia_comprovante: str = Field(..., min_length=3, max_length=100)

    @field_validator("data_despesa")
    @classmethod
    def validar_data_nao_futura(cls, v: date) -> date:
        # RN06: Despesas com datas futuras não poderão ser registradas
        if v > date.today():
            raise ValueError("A data da despesa não pode ser futura (RN06).")
        return v

class SolicitacaoUpdate(BaseModel):
    categoria: Optional[CategoriaEnum] = None
    valor: Optional[float] = Field(None, gt=0)
    data_despesa: Optional[date] = None
    justificativa: Optional[str] = Field(None, min_length=5, max_length=500)
    referencia_comprovante: Optional[str] = Field(None, min_length=3, max_length=100)

    @field_validator("data_despesa")
    @classmethod
    def validar_data_nao_futura(cls, v: Optional[date]) -> Optional[date]:
        if v is not None and v > date.today():
            raise ValueError("A data da despesa não pode ser futura (RN06).")
        return v

class HistoricoOut(BaseModel):
    id: int
    responsavel_id: int
    etapa: str
    decisao: str
    observacao: Optional[str]
    data_hora: datetime

    class Config:
        from_attributes = True

class SolicitacaoOut(BaseModel):
    id: int
    solicitante_id: int
    departamento_id: int
    categoria: CategoriaEnum
    valor: float
    data_despesa: date
    justificativa: str
    referencia_comprovante: str
    situacao: SituacaoEnum
    criado_em: datetime
    historico: List[HistoricoOut] = []

    class Config:
        from_attributes = True

class DecisaoRequest(BaseModel):
    aprovar: bool
    observacao: Optional[str] = Field(None, max_length=500)
