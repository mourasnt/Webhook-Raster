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
    codchecklist: str
    placa: str
    carreta01: Optional[str] = ""
    carreta02: Optional[str] = ""
    carreta03: Optional[str] = ""
    vinculo: str
    codfilial: str
    timestamp: Optional[str] = Field(
        None, description="Timestamp ISO 8601 do evento (opcional, para validação anti-replay)"
    )


class ResultadoChecklistPayload(BaseModel):
    metodo: str = Field(..., description="RESULTADOCHECKLIST")
    codchecklist: str
    placa: str
    carreta01: Optional[str] = ""
    carreta02: Optional[str] = ""
    carreta03: Optional[str] = ""
    vinculo: str
    codfilial: str
    codperfilseguranca: str
    codresultado: str
    resultado: str
    dataexpiracao: str
    produtos: List[ProdutoItem]
    timestamp: Optional[str] = Field(
        None, description="Timestamp ISO 8601 do evento (opcional, para validação anti-replay)"
    )


class PesquisaConsultaPayload(BaseModel):
    method: str = Field(..., description="PESQUISACONCULTA")
    id: int
    identification: str
    identification_type: str
    password: str
    situation: str
    bond: str
    establishment_id: int
    expiration_date: str
    end_date: str
    reasons: Optional[str] = None
    base64: Optional[str] = ""
    timestamp: Optional[str] = Field(
        None, description="Timestamp ISO 8601 do evento (opcional, para validação anti-replay)"
    )


class ChecklistWebhookRequest(BaseModel):
    url: str
    payload: ChecklistPayload


class ResultadoChecklistWebhookRequest(BaseModel):
    url: str
    payload: ResultadoChecklistPayload


class PesquisaConsultaWebhookRequest(BaseModel):
    url: str
    payload: PesquisaConsultaPayload
