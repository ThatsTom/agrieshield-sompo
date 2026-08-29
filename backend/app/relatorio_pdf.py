"""Relatório PDF enxuto por fazenda e apólice."""

from __future__ import annotations

from io import BytesIO
from html import escape
from typing import Any, Dict

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


VERMELHO = colors.HexColor("#D71920")
AZUL = colors.HexColor("#17243B")
CINZA = colors.HexColor("#667085")
FUNDO = colors.HexColor("#F4F6F8")
LINHA = colors.HexColor("#DDE2E8")


def _texto(valor: Any, padrao: str = "Não informado") -> str:
    texto = str(valor or "").strip()
    return escape(texto) if texto else padrao


def _origem(valor: Any) -> str:
    normalizada = str(valor or "").lower()
    if normalizada == "nasa_power":
        return "NASA POWER - dados reais"
    if normalizada == "simulado":
        return "Dados simulados - contingência"
    return "Ainda não processada"


def _data_br(valor: Any) -> str:
    partes = str(valor or "").split("T", 1)[0].split("-")
    return "/".join(reversed(partes)) if len(partes) == 3 else _texto(valor)


def gerar_relatorio_pdf(
    fazenda: Dict[str, Any], resumo: Dict[str, Any] | None, apolice: str
) -> bytes:
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
        title=f"Relatório AgriShield - {fazenda.get('nome_fazenda', '')}",
        author="AgriShield",
    )
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "TituloAgri",
        parent=estilos["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=AZUL,
        spaceAfter=4 * mm,
    )
    subtitulo = ParagraphStyle(
        "SubtituloAgri",
        parent=estilos["Normal"],
        fontSize=9,
        leading=13,
        textColor=CINZA,
        spaceAfter=7 * mm,
    )
    secao = ParagraphStyle(
        "SecaoAgri",
        parent=estilos["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=AZUL,
        spaceBefore=6 * mm,
        spaceAfter=3 * mm,
    )
    corpo = ParagraphStyle(
        "CorpoAgri", parent=estilos["BodyText"], fontSize=9, leading=13
    )
    destaque = ParagraphStyle(
        "DestaqueAgri",
        parent=corpo,
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=20,
        textColor=VERMELHO,
        alignment=TA_CENTER,
    )

    resumo = resumo or {}
    condicao = resumo.get("condicao_atual") or "AGUARDANDO LEITURA"
    score = resumo.get("score")
    score_texto = f"{score}/100" if score is not None else "--/100"
    historia = [
        Paragraph("AgriShield", titulo),
        Paragraph(
            "Relatório operacional por propriedade e apólice", subtitulo
        ),
        Table(
            [
                [Paragraph(score_texto, destaque), Paragraph(_texto(condicao), destaque)],
                ["Score de risco", "Condição atual"],
                [
                    _data_br(resumo.get("data_referencia")),
                    _origem(resumo.get("origem_dados")),
                ],
                ["Data de referência", "Origem do score"],
            ],
            colWidths=[80 * mm, 80 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), FUNDO),
                    ("BOX", (0, 0), (-1, -1), 0.8, LINHA),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, LINHA),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TEXTCOLOR", (0, 1), (-1, 1), CINZA),
                    ("TEXTCOLOR", (0, 3), (-1, 3), CINZA),
                    ("FONTSIZE", (0, 1), (-1, 3), 8),
                    ("TOPPADDING", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("TOPPADDING", (0, 2), (-1, 2), 7),
                    ("BOTTOMPADDING", (0, 2), (-1, 2), 4),
                ]
            ),
        ),
        Paragraph("Identificação", secao),
    ]

    area = fazenda.get("area_ha")
    area_texto = f"{area} ha" if area not in (None, "") else "Não informado"
    linhas_identificacao = [
        ["Fazenda", _texto(fazenda.get("nome_fazenda"))],
        ["Apólice selecionada", _texto(apolice)],
        ["Todas as apólices", _texto(", ".join(fazenda.get("apolices") or []))],
        ["ID", _texto(fazenda.get("id_fazenda") or fazenda.get("id"))],
        ["Operação", _texto(fazenda.get("tipo_operacao"))],
        ["Área aproximada", area_texto],
        ["Situação cadastral", "Arquivada" if fazenda.get("arquivada") else "Ativa"],
    ]
    historia.append(
        Table(
            linhas_identificacao,
            colWidths=[48 * mm, 112 * mm],
            style=TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.7, LINHA),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, LINHA),
                    ("BACKGROUND", (0, 0), (0, -1), FUNDO),
                    ("TEXTCOLOR", (0, 0), (0, -1), CINZA),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            ),
        )
    )

    endereco = ", ".join(
        item
        for item in [
            str(fazenda.get("logradouro") or "").strip(),
            str(fazenda.get("numero_km") or "").strip(),
            str(fazenda.get("bairro") or "").strip(),
            f"{fazenda.get('cidade', '')}/{fazenda.get('uf', '')}".strip("/"),
            f"CEP {fazenda.get('cep')}" if fazenda.get("cep") else "",
        ]
        if item
    )
    poligono = fazenda.get("poligono") or []
    historia.extend(
        [
            Paragraph("Localização e perímetro", secao),
            KeepTogether(
                [
                    Paragraph(f"<b>Endereço:</b> {_texto(endereco)}", corpo),
                    Spacer(1, 2 * mm),
                    Paragraph(
                        f"<b>Coordenadas da sede:</b> {_texto(fazenda.get('latitude'))}, "
                        f"{_texto(fazenda.get('longitude'))}",
                        corpo,
                    ),
                    Spacer(1, 2 * mm),
                    Paragraph(
                        f"<b>Polígono:</b> {len(poligono)} vértice(s) cadastrado(s)",
                        corpo,
                    ),
                ]
            ),
            Paragraph("Observações", secao),
            Paragraph(
                "Este relatório resume o cadastro e a última condição climática "
                "persistida. Dados simulados devem ser tratados apenas como contingência "
                "de demonstração e não como medição observada.",
                corpo,
            ),
        ]
    )

    def cabecalho_rodape(canvas, doc):
        canvas.saveState()
        largura, altura = A4
        canvas.setFillColor(VERMELHO)
        canvas.rect(0, altura - 5 * mm, largura, 5 * mm, fill=1, stroke=0)
        canvas.setStrokeColor(LINHA)
        canvas.line(18 * mm, 13 * mm, largura - 18 * mm, 13 * mm)
        canvas.setFillColor(CINZA)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(18 * mm, 8 * mm, "AgriShield - relatório gerado pelo sistema")
        canvas.drawRightString(
            largura - 18 * mm, 8 * mm, f"Página {doc.page}"
        )
        canvas.restoreState()

    documento.build(
        historia, onFirstPage=cabecalho_rodape, onLaterPages=cabecalho_rodape
    )
    return buffer.getvalue()
