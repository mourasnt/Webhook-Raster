from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class ProdutoItem(BaseModel):
    valor: str
    produto: str
    codproduto: str
    NCMs: str


class ChecklistPayload(BaseModel):
    metodo: str = Field(..., description="CHECKLIST")
    codchecklist: Optional[str] = None
    placa: Optional[str] = None
    carreta01: Optional[str] = None
    carreta02: Optional[str] = None
    carreta03: Optional[str] = None
    vinculo: Optional[str] = None
    codfilial: Optional[str] = None
    timestamp: Optional[str] = Field(
        None, description="Timestamp ISO 8601 do evento (opcional, para validação anti-replay)"
    )


class ResultadoChecklistPayload(BaseModel):
    metodo: str = Field(..., description="RESULTADOCHECKLIST")
    codchecklist: Optional[str] = None
    placa: Optional[str] = None
    carreta01: Optional[str] = None
    carreta02: Optional[str] = None
    carreta03: Optional[str] = None
    vinculo: Optional[str] = None
    codfilial: Optional[str] = None
    codperfilseguranca: Optional[str] = None
    codresultado: Optional[str] = None
    resultado: Optional[str] = None
    dataexpiracao: Optional[str] = None
    produtos: Optional[List[ProdutoItem]] = None
    timestamp: Optional[str] = Field(
        None, description="Timestamp ISO 8601 do evento (opcional, para validação anti-replay)"
    )


class PesquisaConsultaPayload(BaseModel):
    method: str = Field(..., description="PESQUISACONCULTA")
    id: int
    identification: str
    identification_type: Optional[str] = None
    password: Optional[str] = None
    situation: Optional[str] = None
    bond: Optional[str] = None
    establishment_id: Optional[int] = None
    expiration_date: Optional[str] = None
    end_date: Optional[str] = None
    reasons: Optional[str] = None
    service: Optional[str] = None
    base64: Optional[str] = None
    timestamp: Optional[str] = Field(
        None, description="Timestamp ISO 8601 do evento"
    )