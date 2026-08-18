"""Constancia de situación fiscal y opinión de cumplimiento — SIMULADAS.

Con la conexión real al SAT estos documentos se descargarían del portal con la
e.firma del contribuyente. Aquí se genera un PDF sencillo (sin librerías
externas: se escribe la estructura PDF a mano) con los datos de la empresa y
la leyenda de "documento simulado", para que el flujo de la demo esté completo.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.modules.tenants.models import Empresa

_REGIMENES = {
    "601": "General de Ley Personas Morales",
    "603": "Personas Morales con Fines no Lucrativos",
    "605": "Sueldos y Salarios e Ingresos Asimilados a Salarios",
    "606": "Arrendamiento",
    "612": "Personas Físicas con Actividades Empresariales y Profesionales",
    "621": "Incorporación Fiscal",
    "626": "Régimen Simplificado de Confianza",
}


def _pdf_escape(texto: str) -> str:
    # Latin-1 básico para el font estándar Helvetica (WinAnsi); lo que no entre se sustituye.
    texto = texto.encode("cp1252", errors="replace").decode("cp1252")
    return texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_simple(lineas: list[tuple[str, int, bool]]) -> bytes:
    """Genera un PDF de una página (carta) con líneas de texto.
    lineas: (texto, tamaño de fuente, negritas)."""
    contenido = []
    y = 750
    for texto, tam, bold in lineas:
        if texto == "":
            y -= tam
            continue
        font = "/F2" if bold else "/F1"
        contenido.append(f"BT {font} {tam} Tf 60 {y} Td ({_pdf_escape(texto)}) Tj ET")
        y -= tam + 6
    stream = "\n".join(contenido).encode("cp1252", errors="replace")

    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objetos, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objetos) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def _cabecera(titulo: str, empresa: Empresa) -> list[tuple[str, int, bool]]:
    ahora = datetime.now(timezone.utc).astimezone()
    return [
        ("SERVICIO DE ADMINISTRACIÓN TRIBUTARIA (SIMULADO)", 10, True),
        (titulo, 16, True),
        ("", 6, False),
        (f"Fecha y hora de emisión: {ahora.strftime('%d/%m/%Y %H:%M')}", 10, False),
        ("", 6, False),
        ("DATOS DEL CONTRIBUYENTE", 11, True),
        (f"RFC: {empresa.rfc}", 10, False),
        (f"Denominación / razón social: {empresa.razon_social}", 10, False),
        (f"Tipo de persona: {'Física' if empresa.tipo_persona == 'fisica' else 'Moral'}", 10, False),
        (
            f"Régimen: {empresa.regimen_fiscal_codigo or 'No especificado'}"
            + (f" - {_REGIMENES[empresa.regimen_fiscal_codigo]}" if empresa.regimen_fiscal_codigo in _REGIMENES else ""),
            10,
            False,
        ),
        ("", 6, False),
    ]


def constancia_situacion_fiscal(empresa: Empresa) -> bytes:
    lineas = _cabecera("CONSTANCIA DE SITUACIÓN FISCAL", empresa)
    lineas += [
        ("DATOS DE IDENTIFICACIÓN", 11, True),
        (f"Fecha de inicio de operaciones: {empresa.created_at.strftime('%d/%m/%Y') if empresa.created_at else '-'}", 10, False),
        ("Estatus en el padrón: ACTIVO", 10, False),
        ("Fecha del último cambio de estado: -", 10, False),
        ("", 6, False),
        ("DATOS DEL DOMICILIO REGISTRADO", 11, True),
        ("Domicilio: (no capturado en Nubinox)", 10, False),
        ("", 6, False),
        ("ACTIVIDADES ECONÓMICAS", 11, True),
        ("Actividad principal: (según el régimen configurado)", 10, False),
        ("", 6, False),
        ("OBLIGACIONES", 11, True),
        ("Declaración mensual de IVA · Pago provisional mensual de ISR · Declaración anual", 10, False),
        ("", 12, False),
        ("DOCUMENTO SIMULADO POR NUBINOX PARA FINES DE DEMOSTRACIÓN. NO TIENE VALIDEZ OFICIAL.", 9, True),
        ("Con la conexión real al SAT este documento se descarga con la e.firma del contribuyente.", 9, False),
    ]
    return _pdf_simple(lineas)


def opinion_cumplimiento(empresa: Empresa, *, sentido: str = "positivo") -> bytes:
    lineas = _cabecera("OPINIÓN DEL CUMPLIMIENTO DE OBLIGACIONES FISCALES", empresa)
    lineas += [
        (f"SENTIDO DE LA OPINIÓN: {sentido.upper()}", 13, True),
        ("", 6, False),
        ("Artículo 32-D del Código Fiscal de la Federación / regla 2.1.37 RMF.", 10, False),
        ("El contribuyente se encuentra inscrito en el RFC, ha presentado sus declaraciones y no tiene", 10, False),
        ("créditos fiscales firmes o exigibles pendientes de pago (información simulada).", 10, False),
        ("", 6, False),
        (f"Vigencia: {date.today().strftime('%d/%m/%Y')} (30 días naturales)", 10, False),
        ("", 12, False),
        ("DOCUMENTO SIMULADO POR NUBINOX PARA FINES DE DEMOSTRACIÓN. NO TIENE VALIDEZ OFICIAL.", 9, True),
        ("Con la conexión real al SAT este documento se descarga con la e.firma del contribuyente.", 9, False),
    ]
    return _pdf_simple(lineas)
