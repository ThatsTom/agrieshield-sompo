# =============================================================================
# AgriShield — API FastAPI
# Prototipação funcional local com CSV, NASA POWER e Open-Meteo.
# =============================================================================

from __future__ import annotations

from datetime import date, datetime, timedelta
import csv
import json
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Callable, Dict
import logging
import math
import re
import sys
import threading
import uuid
from io import BytesIO

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE.parent / ".env")
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "etl"))
sys.path.insert(0, str(BASE / "app"))

from etapa1_cadastro_fazendas import (
    adicionar_fazenda,
    atualizar_fazenda,
    bool_str,
    buscar_fazenda,
    criar_base_se_nao_existir,
    definir_arquivamento,
    listar_fazendas,
    normalizar_cep,
)
from etapa2_coleta_nasa_power import COLUNAS_NUMERICAS, coletar_nasa_power
from etapa3_engenharia_variaveis import (
    avaliar_risco_alagamento,
    consolidar_para_dashboard,
    enriquecer,
    salvar_dashboard_csv,
    salvar_enriquecido_csv,
)
from etapa4_dados_geoespaciais import (
    ALGORITHM_VERSION,
    MERIT_ID,
    SCHEMA_VERSION,
    SRTM_ID,
    consultar_dados_geoespaciais,
)
from repositorio_fazendas_geoespaciais import (
    buscar_registro_geoespacial,
    salvar_resultado_geoespacial,
)
from inmet import (
    ClienteCatalogoInmet,
    ClienteHistoricoInmet,
    ErroClienteInmet,
    ErroDadosInmet,
    FazendaInmetNaoEncontrada,
    RepositorioInmetMemoria,
    ResultadoInmetNaoEncontrado,
    ServicoInmet,
)
from mapbiomas import (
    ANO_DEFAULT as MAPBIOMAS_ANO_DEFAULT,
    ClienteEarthEngineMapBiomas,
    ErroConfiguracaoMapBiomas,
    ErroConsultaMapBiomas,
    ErroDadosMapBiomas,
    ErroDominioMapBiomas,
    FazendaMapBiomasNaoEncontrada,
    RepositorioMapBiomasMemoria,
    ResultadoMapBiomasNaoEncontrado,
    ServicoMapBiomas,
)
from servicos_externos import (
    CepInvalido,
    CepNaoEncontrado,
    ErroConsultaCep,
    geocoding_por_cep,
    previsao_open_meteo,
)
from backend.app.fabrica_servico_avaliacao_exposicao import (
    criar_servico_avaliacao_exposicao,
)
from backend.app.relatorio_pdf import gerar_relatorio_pdf
from backend.app.servico_avaliacao_exposicao import (
    CodigoErroAvaliacaoExposicao,
    ErroAvaliacaoExposicao,
    ServicoAvaliacaoExposicao,
)
from backend.app.servico_hidrico_v2_experimental import (
    ResultadoInterfaceHidricoV2Dto,
    ServicoHidricoV2Experimental,
)
from backend.app.servico_parametros_score import (
    ConfiguracaoParametrosModeloApresentacao,
    ErroParametrosScoreInvalidos,
    ErroParametrosScorePersistidosInvalidos,
    obter_configuracao_parametros_modelo,
    salvar_configuracao_parametros_modelo,
)
from backend.etl.repositorio_parametros_score import (
    CHAVES_ESPERADAS as _CHAVES_PARAMETROS_MODELO,
)
from backend.exposicao.apresentacao_exposicao import (
    ResultadoApresentacaoExposicaoMaquinario,
)
from backend.risco.modelos import FonteDado

app = FastAPI(
    title="AgriShield API",
    description="API local para o protótipo AgriShield — Sompo Seguros",
    version="2.0.0-react-local",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

criar_base_se_nao_existir()
_cache_score: Dict[str, Dict[str, Any]] = {}
_jobs_climaticos: Dict[str, Dict[str, Any]] = {}
_jobs_climaticos_lock = threading.Lock()
_repositorio_inmet = RepositorioInmetMemoria()
_servico_inmet = ServicoInmet(
    cliente_catalogo=ClienteCatalogoInmet(),
    cliente_historico=ClienteHistoricoInmet(),
    repositorio=_repositorio_inmet,
    buscar_fazenda=buscar_fazenda,
)
_repositorio_mapbiomas = RepositorioMapBiomasMemoria()
_servico_mapbiomas = ServicoMapBiomas(
    cliente=ClienteEarthEngineMapBiomas(),
    repositorio=_repositorio_mapbiomas,
    buscar_fazenda=buscar_fazenda,
)
_servico_avaliacao_exposicao = criar_servico_avaliacao_exposicao()
_servico_hidrico_v2_experimental = ServicoHidricoV2Experimental(
    _servico_avaliacao_exposicao
)
logger = logging.getLogger(__name__)


class FonteHistoricaExposicao(str, Enum):
    NASA_POWER = "NASA_POWER"
    OPEN_METEO = "OPEN_METEO"


_STATUS_HTTP_ERRO_EXPOSICAO = {
    CodigoErroAvaliacaoExposicao.FAZENDA_NAO_ENCONTRADA: 404,
    CodigoErroAvaliacaoExposicao.COORDENADAS_INDISPONIVEIS: 422,
    CodigoErroAvaliacaoExposicao.PERIODO_HISTORICO_INVALIDO: 422,
    CodigoErroAvaliacaoExposicao.CONTEXTO_TERRITORIAL_INDISPONIVEL: 422,
    CodigoErroAvaliacaoExposicao.CONTEXTO_TERRITORIAL_INCOMPATIVEL: 422,
    CodigoErroAvaliacaoExposicao.FONTE_METEOROLOGICA_INDISPONIVEL: 503,
    CodigoErroAvaliacaoExposicao.REPOSITORIO_FAZENDAS_INDISPONIVEL: 503,
}


def obter_servico_avaliacao_exposicao() -> ServicoAvaliacaoExposicao:
    return _servico_avaliacao_exposicao


def obter_servico_hidrico_v2_experimental() -> ServicoHidricoV2Experimental:
    return _servico_hidrico_v2_experimental


def _data_atual_servidor() -> date:
    return date.today()


def _traduzir_erro_exposicao(exc: ErroAvaliacaoExposicao) -> HTTPException:
    return HTTPException(
        status_code=_STATUS_HTTP_ERRO_EXPOSICAO[exc.codigo],
        detail={
            "codigo": exc.codigo.value,
            "mensagem": str(exc),
        },
    )


class FazendaIn(BaseModel):
    nome_fazenda: str = Field(..., min_length=2)
    numero_apolice: str = Field(..., min_length=3)
    apolices: list[str] = Field(default_factory=list)
    cep: str = Field(..., min_length=8)
    logradouro: str = ""
    numero_km: str = ""
    complemento: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    referencia_acesso: str = ""
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    tipo_operacao: str = "campo"
    proximidade_agua: bool = False
    area_ha: float = Field(..., gt=0)
    poligono: list[tuple[float, float]] = Field(default_factory=list)

    @field_validator("cep")
    @classmethod
    def validar_cep(cls, valor: str) -> str:
        if len(normalizar_cep(valor)) != 8:
            raise ValueError("CEP deve conter exatamente 8 dígitos")
        return valor

    @model_validator(mode="after")
    def validar_coordenadas_manuais(self) -> "FazendaIn":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude e longitude devem ser informadas juntas")
        if self.latitude == 0 and self.longitude == 0:
            raise ValueError("latitude e longitude 0,0 nao identificam uma localizacao")
        apolices = []
        for numero in [self.numero_apolice, *self.apolices]:
            normalizado = str(numero or "").strip()
            if len(normalizado) < 3:
                raise ValueError("cada numero de apolice deve ter ao menos 3 caracteres")
            if normalizado not in apolices:
                apolices.append(normalizado)
        self.numero_apolice = apolices[0]
        self.apolices = apolices

        if self.poligono and len(self.poligono) < 3:
            raise ValueError("o poligono deve possuir ao menos 3 vertices")
        for longitude, latitude in self.poligono:
            if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
                raise ValueError("vertices do poligono possuem coordenadas invalidas")
        return self


class ArquivamentoIn(BaseModel):
    arquivada: bool = True


class ColetaInmetIn(BaseModel):
    data_inicio: date
    data_fim: date
    codigo_estacao: str | None = Field(default=None, min_length=1)


class ParametroModeloIn(BaseModel):
    grupo: str = Field(..., min_length=1)
    indicador: str = Field(..., min_length=1)
    parametro: str = Field(..., min_length=1)
    valor: float


class ParametrosScoreIn(BaseModel):
    parametros: list[ParametroModeloIn] = Field(
        ...,
        min_length=len(_CHAVES_PARAMETROS_MODELO),
        max_length=len(_CHAVES_PARAMETROS_MODELO),
    )


def _status_geoespacial(
    fazenda: Dict[str, Any], registro: Dict[str, Any] | None
) -> str:
    """Traduz o registro territorial persistido para o estado resumido da fazenda."""

    if not _coordenadas_utilizaveis(fazenda) or not registro:
        return "PENDENTE"
    try:
        coordenadas_compativeis = math.isclose(
            float(fazenda["latitude"]),
            float(registro["latitude_referencia"]),
            rel_tol=0,
            abs_tol=1e-6,
        ) and math.isclose(
            float(fazenda["longitude"]),
            float(registro["longitude_referencia"]),
            rel_tol=0,
            abs_tol=1e-6,
        )
    except (KeyError, TypeError, ValueError):
        coordenadas_compativeis = False
    if not coordenadas_compativeis:
        return "PENDENTE"

    status_persistido = str(registro.get("status") or "").lower()
    if status_persistido == "sucesso":
        return "SUCESSO"
    if status_persistido in {"erro", "parcial"}:
        return "ERRO"
    return "PENDENTE"


def _normalizar_fazenda(
    f: Dict[str, Any], registro_geoespacial: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    retorno = dict(f)
    retorno["id"] = str(f.get("id_fazenda"))
    retorno["proximidade_agua"] = bool_str(f.get("proximidade_agua")) == "True"
    retorno["arquivada"] = bool_str(f.get("arquivada")) == "True"
    retorno["latitude"] = float(f.get("latitude") or 0)
    retorno["longitude"] = float(f.get("longitude") or 0)
    retorno["area_ha"] = (
        float(f["area_ha"]) if f.get("area_ha") not in (None, "") else None
    )
    retorno["status_geoespacial"] = _status_geoespacial(f, registro_geoespacial)
    retorno["score_preview"] = _carregar_score_preview(str(f.get("id_fazenda") or ""))
    retorno["apolices"] = _ler_apolices(f)
    retorno["poligono"] = _ler_poligono(f.get("poligono_geojson"))
    return retorno


def _ler_apolices(fazenda: Dict[str, Any]) -> list[str]:
    try:
        valores = json.loads(str(fazenda.get("apolices_json") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        valores = []
    principal = str(fazenda.get("numero_apolice") or "").strip()
    unicas = []
    for valor in ([principal] if principal else []) + list(valores):
        numero = str(valor or "").strip()
        if numero and numero not in unicas:
            unicas.append(numero)
    return unicas


def _ler_poligono(bruto: Any) -> list[list[float]]:
    if not bruto:
        return []
    try:
        payload = json.loads(bruto) if isinstance(bruto, str) else bruto
        coordenadas = payload.get("coordinates", [[]])[0]
        pontos = [[float(p[0]), float(p[1])] for p in coordenadas]
        if len(pontos) > 1 and pontos[0] == pontos[-1]:
            pontos.pop()
        return pontos
    except (AttributeError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return []


def _dados_persistencia_fazenda(fazenda: FazendaIn) -> Dict[str, Any]:
    dados = fazenda.model_dump(exclude={"apolices", "poligono"})
    dados["apolices_json"] = json.dumps(fazenda.apolices, ensure_ascii=False)
    if fazenda.poligono:
        vertices = [list(ponto) for ponto in fazenda.poligono]
        if vertices[0] != vertices[-1]:
            vertices.append(vertices[0])
        dados["poligono_geojson"] = json.dumps(
            {"type": "Polygon", "coordinates": [vertices]}, ensure_ascii=False
        )
    else:
        dados["poligono_geojson"] = ""
    return dados


def _carregar_score_preview(id_fazenda: str) -> Dict[str, Any] | None:
    """Lê somente o resumo persistido; listar clientes nunca dispara coleta externa."""
    resumo_cache = _cache_score.get(id_fazenda, {}).get("resumo")
    if resumo_cache:
        return {
            "score": resumo_cache.get("score"),
            "condicao_atual": resumo_cache.get("condicao_atual"),
            "data_referencia": resumo_cache.get("data_referencia"),
            "origem_dados": _cache_score.get(id_fazenda, {}).get("origem"),
        }

    arquivo = BASE / "data" / f"dashboard_indicadores_{id_fazenda}.csv"
    if not arquivo.exists():
        return None
    try:
        with arquivo.open(encoding="utf-8-sig", newline="") as f:
            linha = next(csv.DictReader(f, delimiter=";"), None)
        if not linha or linha.get("score") in (None, ""):
            return None
        return {
            "score": int(float(linha["score"])),
            "condicao_atual": linha.get("condicao_atual") or None,
            "data_referencia": linha.get("data_referencia") or None,
            "origem_dados": linha.get("origem_dados") or None,
        }
    except (OSError, TypeError, ValueError):
        logger.warning("Resumo persistido inválido", extra={"id_fazenda": id_fazenda})
        return None


def _resultado_geoespacial_erro(
    fazenda: Dict[str, Any], exc: Exception
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "status": "erro",
        "localizacao": {
            "latitude": float(fazenda["latitude"]),
            "longitude": float(fazenda["longitude"]),
        },
        "parametros": {
            "raio_analise_m": 1000,
            "limiar_drenagem_km2": 10,
            "raio_busca_drenagem_m": 50000,
        },
        "atributos": {},
        "qualidade": {"flags": ["consulta_geoespacial_nao_concluida"]},
        "fontes": [
            {"identificador": SRTM_ID},
            {"identificador": MERIT_ID},
        ],
        "cache": {"hit": False, "chave": None},
        "erros": [
            {
                "codigo": "consulta_geoespacial_falhou",
                "fonte": "earth_engine",
                "tipo": type(exc).__name__,
                "detalhe": "Falha inesperada ao executar enriquecimento geoespacial",
            }
        ],
    }


def _coordenadas_utilizaveis(fazenda: Dict[str, Any]) -> bool:
    """Aceita coordenadas geográficas finitas, mas rejeita o sentinela 0,0."""

    try:
        latitude = float(fazenda.get("latitude"))
        longitude = float(fazenda.get("longitude"))
    except (TypeError, ValueError):
        return False
    return (
        math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
        and (latitude != 0 or longitude != 0)
    )


def _processar_geoespacial(fazenda: Dict[str, Any]) -> Dict[str, Any]:
    id_fazenda = str(fazenda.get("id_fazenda") or "")
    logger.info("Enriquecimento geoespacial iniciado", extra={"id_fazenda": id_fazenda})
    try:
        resultado = consultar_dados_geoespaciais(
            float(fazenda["latitude"]), float(fazenda["longitude"])
        )
    except Exception as exc:
        resultado = _resultado_geoespacial_erro(fazenda, exc)
    registro = salvar_resultado_geoespacial(fazenda, resultado)
    logger.info(
        "Enriquecimento geoespacial concluido",
        extra={
            "id_fazenda": id_fazenda,
            "status_geoespacial": registro.get("status"),
            "cache_hit": bool(resultado.get("cache", {}).get("hit")),
        },
    )
    return registro


def _gerar_score(
    id_fazenda: str,
    *,
    forcar: bool = False,
    progresso: Callable[[int, str], None] | None = None,
) -> Dict[str, Any]:
    avisar = progresso or (lambda _percentual, _mensagem: None)
    fazenda = buscar_fazenda(id_fazenda)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    if not _coordenadas_utilizaveis(fazenda):
        raise HTTPException(
            status_code=422,
            detail="Informe latitude e longitude antes de processar o clima",
        )

    if forcar:
        _cache_score.pop(id_fazenda, None)

    if id_fazenda not in _cache_score:
        avisar(10, "Preparando coleta climática")
        fim = datetime.now()
        inicio = fim - timedelta(days=40)
        avisar(25, "Consultando NASA POWER")
        df_bruto, origem = coletar_nasa_power(
            lat=float(fazenda["latitude"]),
            lon=float(fazenda["longitude"]),
            inicio=inicio.strftime("%Y%m%d"),
            fim=fim.strftime("%Y%m%d"),
            salvar_csv=True,
            id_fazenda=id_fazenda,
        )
        if isinstance(df_bruto, pd.DataFrame):
            colunas_climaticas = [
                coluna for coluna in COLUNAS_NUMERICAS if coluna in df_bruto.columns
            ]
            if colunas_climaticas:
                df_bruto = df_bruto.dropna(subset=colunas_climaticas, how="all")
            if df_bruto.empty:
                raise HTTPException(
                    status_code=503,
                    detail="NASA POWER respondeu sem medições climáticas disponíveis",
                )
        avisar(60, "Calculando indicadores e condição atual")
        df_final = enriquecer(df_bruto)
        salvar_enriquecido_csv(df_final, id_fazenda)
        resumo = consolidar_para_dashboard(
            df_final,
            tipo_operacao=fazenda.get("tipo_operacao", "campo"),
            proximidade_agua=bool_str(fazenda.get("proximidade_agua")) == "True",
        )
        resumo["fazenda"] = {
            "id": fazenda["id_fazenda"],
            "nome": fazenda["nome_fazenda"],
            "apolice": fazenda["numero_apolice"],
            "cep": fazenda["cep"],
            "cidade": fazenda["cidade"],
            "uf": fazenda["uf"],
            "tipo_operacao": fazenda["tipo_operacao"],
            "proximidade_agua": bool_str(fazenda.get("proximidade_agua")) == "True",
        }
        resumo["origem_dados"] = origem
        avisar(85, "Persistindo resumo climático")
        salvar_dashboard_csv(id_fazenda, resumo, origem)
        _cache_score[id_fazenda] = {
            "resumo": resumo,
            "df_final": df_final,
            "origem": origem,
        }

    avisar(100, "Processamento climático concluído")
    return _cache_score[id_fazenda]["resumo"]


def _atualizar_job_climatico(id_fazenda: str, **mudancas: Any) -> Dict[str, Any]:
    with _jobs_climaticos_lock:
        job = _jobs_climaticos.setdefault(id_fazenda, {})
        job.update(mudancas)
        job["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
        return dict(job)


def _executar_job_climatico(id_fazenda: str, job_id: str) -> None:
    def progresso(percentual: int, mensagem: str) -> None:
        _atualizar_job_climatico(
            id_fazenda,
            job_id=job_id,
            status="processando",
            progresso=percentual,
            mensagem=mensagem,
        )

    try:
        resumo = _gerar_score(id_fazenda, forcar=True, progresso=progresso)
        _atualizar_job_climatico(
            id_fazenda,
            job_id=job_id,
            status="concluido",
            progresso=100,
            mensagem="Condição atual atualizada",
            score_preview={
                "score": resumo.get("score"),
                "condicao_atual": resumo.get("condicao_atual"),
                "data_referencia": resumo.get("data_referencia"),
                "origem_dados": resumo.get("origem_dados"),
            },
        )
    except Exception as exc:
        detalhe = exc.detail if isinstance(exc, HTTPException) else str(exc)
        _atualizar_job_climatico(
            id_fazenda,
            job_id=job_id,
            status="erro",
            mensagem=str(detalhe) or "Falha no processamento climático",
        )


@app.get("/")
def health():
    return {
        "servico": "AgriShield API",
        "status": "ok",
        "docs": "http://127.0.0.1:8000/docs",
    }


@app.get("/api/cep/{cep}")
def resolver_cep(cep: str):
    try:
        return geocoding_por_cep(cep)
    except CepInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CepNaoEncontrado as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ErroConsultaCep as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/fazendas")
def get_fazendas(incluir_arquivadas: bool = False):
    return [
        _normalizar_fazenda(
            fazenda,
            buscar_registro_geoespacial(str(fazenda.get("id_fazenda") or "")),
        )
        for fazenda in listar_fazendas()
        if incluir_arquivadas or bool_str(fazenda.get("arquivada")) != "True"
    ]


@app.post("/api/fazendas", status_code=201)
def post_fazenda(fazenda: FazendaIn):
    dados = _dados_persistencia_fazenda(fazenda)
    if fazenda.latitude is not None and fazenda.longitude is not None:
        dados["latitude"] = str(fazenda.latitude)
        dados["longitude"] = str(fazenda.longitude)
    else:
        geo = resolver_cep(fazenda.cep)
        dados["latitude"] = "" if geo.get("latitude") is None else str(geo["latitude"])
        dados["longitude"] = "" if geo.get("longitude") is None else str(geo["longitude"])
        for campo in ["logradouro", "complemento", "bairro", "cidade", "uf"]:
            if not dados.get(campo):
                dados[campo] = geo.get(campo, "")
    nova = adicionar_fazenda(dados)
    registro_geoespacial = None
    if _coordenadas_utilizaveis(nova):
        try:
            registro_geoespacial = _processar_geoespacial(nova)
        except Exception:
            # A persistência do cadastro é o compromisso primário deste endpoint.
            # Falhas de persistência territorial podem ser repetidas pelo retry.
            logger.warning(
                "Enriquecimento geoespacial nao foi persistido",
                extra={"id_fazenda": str(nova.get("id_fazenda") or "")},
            )
    else:
        logger.info(
            "Enriquecimento geoespacial ignorado por coordenadas indisponiveis",
            extra={"id_fazenda": str(nova.get("id_fazenda") or "")},
        )
    return _normalizar_fazenda(nova, registro_geoespacial)


@app.put("/api/fazendas/{id_fazenda}")
def put_fazenda(id_fazenda: str, fazenda: FazendaIn):
    anterior = buscar_fazenda(id_fazenda)
    if not anterior:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")

    dados = _dados_persistencia_fazenda(fazenda)
    if fazenda.latitude is not None and fazenda.longitude is not None:
        dados["latitude"] = str(fazenda.latitude)
        dados["longitude"] = str(fazenda.longitude)
    else:
        geo = resolver_cep(fazenda.cep)
        dados["latitude"] = "" if geo.get("latitude") is None else str(geo["latitude"])
        dados["longitude"] = "" if geo.get("longitude") is None else str(geo["longitude"])
        for campo in ["logradouro", "complemento", "bairro", "cidade", "uf"]:
            if not dados.get(campo):
                dados[campo] = geo.get(campo, "")

    atualizada = atualizar_fazenda(id_fazenda, dados)
    if not atualizada:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")

    _cache_score.pop(str(id_fazenda), None)
    registro_geoespacial = buscar_registro_geoespacial(id_fazenda)
    coordenadas_mudaram = any(
        str(anterior.get(campo) or "") != str(atualizada.get(campo) or "")
        for campo in ("latitude", "longitude")
    )
    if coordenadas_mudaram and _coordenadas_utilizaveis(atualizada):
        try:
            registro_geoespacial = _processar_geoespacial(atualizada)
        except Exception:
            logger.warning(
                "Enriquecimento geoespacial da edição não foi persistido",
                extra={"id_fazenda": str(id_fazenda)},
            )
    return _normalizar_fazenda(atualizada, registro_geoespacial)


@app.post("/api/fazendas/{id_fazenda}/arquivamento")
def post_arquivamento(id_fazenda: str, entrada: ArquivamentoIn):
    atualizada = definir_arquivamento(id_fazenda, entrada.arquivada)
    if not atualizada:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    return _normalizar_fazenda(
        atualizada, buscar_registro_geoespacial(str(id_fazenda))
    )


@app.get("/api/fazendas/{id_fazenda}/geoespacial")
def get_geoespacial(id_fazenda: str):
    if not buscar_fazenda(id_fazenda):
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    registro = buscar_registro_geoespacial(id_fazenda)
    if not registro:
        raise HTTPException(
            status_code=404, detail="Dados geoespaciais não encontrados"
        )
    return registro


@app.post("/api/fazendas/{id_fazenda}/geoespacial/recalcular")
def recalcular_geoespacial(id_fazenda: str):
    fazenda = buscar_fazenda(id_fazenda)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    try:
        return _processar_geoespacial(fazenda)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Não foi possível persistir os dados geoespaciais"
        ) from exc


@app.get("/api/fazendas/{id_fazenda}/inmet/candidatos")
def get_candidatos_inmet(id_fazenda: str):
    try:
        return _servico_inmet.listar_candidatos(id_fazenda)
    except FazendaInmetNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ErroClienteInmet, ErroDadosInmet) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/fazendas/{id_fazenda}/inmet/coletar")
def coletar_inmet(id_fazenda: str, entrada: ColetaInmetIn):
    try:
        return _servico_inmet.coletar(
            id_fazenda,
            data_inicio=entrada.data_inicio,
            data_fim=entrada.data_fim,
            codigo_estacao=entrada.codigo_estacao,
        )
    except FazendaInmetNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ErroClienteInmet, ErroDadosInmet) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/fazendas/{id_fazenda}/inmet")
def get_inmet(id_fazenda: str):
    try:
        return _servico_inmet.obter(id_fazenda)
    except (FazendaInmetNaoEncontrada, ResultadoInmetNaoEncontrado) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/fazendas/{id_fazenda}/mapbiomas/analisar")
def analisar_mapbiomas(
    id_fazenda: str,
    ano: int = MAPBIOMAS_ANO_DEFAULT,
):
    try:
        return _servico_mapbiomas.analisar(id_fazenda, ano=ano)
    except FazendaMapBiomasNaoEncontrada as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ErroDominioMapBiomas as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ErroConfiguracaoMapBiomas as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (ErroConsultaMapBiomas, ErroDadosMapBiomas) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/fazendas/{id_fazenda}/mapbiomas")
def get_mapbiomas(id_fazenda: str):
    try:
        return _servico_mapbiomas.obter(id_fazenda)
    except (FazendaMapBiomasNaoEncontrada, ResultadoMapBiomasNaoEncontrado) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get(
    "/api/v1/exposicao/{id_fazenda}",
    response_model=ResultadoApresentacaoExposicaoMaquinario,
    summary="Avaliar exposicao do maquinario",
    description=(
        "Executa o Score demonstrativo de Exposicao do Maquinario. "
        "O resultado nao representa probabilidade atuarial de sinistro."
    ),
)
def get_exposicao_v1(
    id_fazenda: str,
    servico: Annotated[
        ServicoAvaliacaoExposicao,
        Depends(obter_servico_avaliacao_exposicao),
    ],
    data_referencia: Annotated[
        date | None,
        Query(description="Data de referencia no formato YYYY-MM-DD"),
    ] = None,
    fonte: Annotated[
        FonteHistoricaExposicao,
        Query(description="Fonte historica selecionada explicitamente"),
    ] = FonteHistoricaExposicao.NASA_POWER,
) -> ResultadoApresentacaoExposicaoMaquinario:
    data_efetiva = (
        data_referencia if data_referencia is not None else _data_atual_servidor()
    )
    try:
        return servico.avaliar_exposicao_fazenda(
            id_fazenda,
            data_efetiva,
            fonte=FonteDado(fonte.value),
        )
    except ErroAvaliacaoExposicao as exc:
        raise _traduzir_erro_exposicao(exc) from exc


@app.get(
    "/api/v1/parametros-score",
    response_model=ConfiguracaoParametrosModeloApresentacao,
    summary="Consultar os parametros configuraveis do modelo AgriShield-EQUIP",
    description=(
        "Retorna os pesos do score, os coeficientes internos de Exposicao "
        "Hidrica/Instabilidade/Incendio/Tempestades, o valor padrao de cada "
        "um e quando foram atualizados pela ultima vez."
    ),
)
def get_parametros_score() -> ConfiguracaoParametrosModeloApresentacao:
    try:
        return obter_configuracao_parametros_modelo()
    except ErroParametrosScorePersistidosInvalidos as exc:
        raise HTTPException(
            status_code=500,
            detail="Configuração de parâmetros do modelo indisponível.",
        ) from exc


@app.put(
    "/api/v1/parametros-score",
    response_model=ConfiguracaoParametrosModeloApresentacao,
    summary="Salvar os parametros configuraveis do modelo AgriShield-EQUIP",
    description=(
        "Recebe os 18 parametros (pesos do score + coeficientes internos), "
        "valida cada grupo separadamente e persiste atomicamente a nova "
        "configuracao. Nenhum valor e normalizado automaticamente."
    ),
)
def put_parametros_score(
    entrada: ParametrosScoreIn,
) -> ConfiguracaoParametrosModeloApresentacao:
    valores = {
        (item.grupo, item.indicador, item.parametro): item.valor
        for item in entrada.parametros
    }
    try:
        return salvar_configuracao_parametros_modelo(valores)
    except ErroParametrosScoreInvalidos as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {"grupo": grupo, "mensagem": mensagem} for grupo, mensagem in exc.erros
            ],
        ) from exc


@app.get(
    "/api/experimental/exposicao-hidrica-v2/{id_fazenda}",
    response_model=ResultadoInterfaceHidricoV2Dto,
    summary="Comparar Hídrico v1 com Hídrico v2 experimental",
    description="EXPERIMENTAL — não calibrado contra sinistros reais.",
)
def get_exposicao_hidrica_v2_experimental(
    id_fazenda: str,
    servico: Annotated[
        ServicoHidricoV2Experimental,
        Depends(obter_servico_hidrico_v2_experimental),
    ],
    data_referencia: Annotated[
        date | None,
        Query(description="Data de referência no formato YYYY-MM-DD"),
    ] = None,
    fonte: Annotated[
        FonteHistoricaExposicao,
        Query(description="Fonte histórica, sem mistura de provedores"),
    ] = FonteHistoricaExposicao.NASA_POWER,
    detalhe: Annotated[
        str | None,
        Query(
            pattern="^(completo)?$", description="Use completo para retornar 180 dias"
        ),
    ] = None,
) -> ResultadoInterfaceHidricoV2Dto:
    try:
        return servico.avaliar(
            id_fazenda,
            data_referencia or _data_atual_servidor(),
            fonte=FonteDado(fonte.value),
            detalhe_completo=detalhe == "completo",
        )
    except ErroAvaliacaoExposicao as exc:
        raise _traduzir_erro_exposicao(exc) from exc


@app.get("/api/fazendas/{id_fazenda}/score")
def get_score(id_fazenda: str):
    return _gerar_score(id_fazenda)


@app.get("/api/fazendas/{id_fazenda}/relatorio.pdf")
def get_relatorio_pdf(
    id_fazenda: str,
    apolice: Annotated[str | None, Query(min_length=3)] = None,
):
    registro = buscar_fazenda(id_fazenda)
    if not registro:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    fazenda = _normalizar_fazenda(
        registro, buscar_registro_geoespacial(id_fazenda)
    )
    apolices = fazenda["apolices"]
    selecionada = apolice or (apolices[0] if apolices else "sem-apolice")
    if apolice and apolice not in apolices:
        raise HTTPException(
            status_code=404, detail="Apólice não encontrada para esta fazenda"
        )
    conteudo = gerar_relatorio_pdf(fazenda, fazenda.get("score_preview"), selecionada)
    nome_seguro = re.sub(r"[^A-Za-z0-9_-]+", "-", selecionada).strip("-")
    nome = f"agrishield_fazenda_{id_fazenda}_{nome_seguro or 'relatorio'}.pdf"
    return StreamingResponse(
        BytesIO(conteudo),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@app.post("/api/fazendas/{id_fazenda}/clima/processar", status_code=202)
def post_processamento_climatico(
    id_fazenda: str, tarefas: BackgroundTasks
):
    if not buscar_fazenda(id_fazenda):
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    with _jobs_climaticos_lock:
        atual = _jobs_climaticos.get(id_fazenda)
        if atual and atual.get("status") in {"aguardando", "processando"}:
            return dict(atual)
        job_id = uuid.uuid4().hex
        job = {
            "job_id": job_id,
            "id_fazenda": id_fazenda,
            "status": "aguardando",
            "progresso": 0,
            "mensagem": "Processamento adicionado à fila",
            "atualizado_em": datetime.now().isoformat(timespec="seconds"),
        }
        _jobs_climaticos[id_fazenda] = job
    tarefas.add_task(_executar_job_climatico, id_fazenda, job_id)
    return dict(job)


@app.get("/api/fazendas/{id_fazenda}/clima/status")
def get_status_processamento_climatico(id_fazenda: str):
    if not buscar_fazenda(id_fazenda):
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")
    with _jobs_climaticos_lock:
        job = _jobs_climaticos.get(id_fazenda)
        if job:
            return dict(job)
    return {
        "id_fazenda": id_fazenda,
        "status": "nao_iniciado",
        "progresso": 0,
        "mensagem": "Nenhum processamento iniciado nesta sessão",
    }


@app.get("/api/fazendas/{id_fazenda}/alertas")
def get_alertas(id_fazenda: str):
    fazenda = buscar_fazenda(id_fazenda)
    if not fazenda:
        raise HTTPException(status_code=404, detail="Fazenda não encontrada")

    resumo = _gerar_score(id_fazenda)
    previsao = previsao_open_meteo(
        float(fazenda["latitude"]), float(fazenda["longitude"])
    )
    alertas = list(previsao.get("alertas", []))

    if resumo.get("metricas_dia", {}).get("solo_encharcado"):
        alertas.append(
            {
                "tipo": "Solo encharcado",
                "severidade": "Média",
                "detalhe": fazenda["nome_fazenda"],
                "data": resumo.get("data_referencia", "hoje"),
            }
        )

    alerta_alagamento = avaliar_risco_alagamento(
        resumo,
        previsao.get("dias", []),
        bool_str(fazenda.get("proximidade_agua")) == "True",
    )
    if alerta_alagamento:
        alertas.append(alerta_alagamento)

    ordem = {"Alta": 0, "Média": 1, "Baixa": 2}
    alertas.sort(key=lambda a: ordem.get(a.get("severidade"), 9))
    return {
        "fazenda_id": id_fazenda,
        "origem_previsao": previsao.get("origem"),
        "alertas": alertas[:5],
        "previsao_5d": previsao.get("dias", []),
    }


@app.get("/api/fazendas/{id_fazenda}/dashboard")
def get_dashboard(id_fazenda: str):
    score = _gerar_score(id_fazenda)
    alertas = get_alertas(id_fazenda)
    return {
        "score": score,
        "alertas": alertas["alertas"],
        "previsao_5d": alertas["previsao_5d"],
    }


@app.post("/api/cache/limpar")
def limpar_cache():
    _cache_score.clear()
    return {"status": "cache limpo"}
