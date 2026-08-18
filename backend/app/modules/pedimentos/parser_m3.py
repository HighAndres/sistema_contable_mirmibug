"""Parser del archivo M3 del SAAI (el ".003"/".00N" que entrega el agente aduanal).

Es el archivo de "validación" del pedimento: texto plano latin-1, un registro
por línea, campos separados por "|". El primer campo es el tipo de registro:

    500  encabezado del archivo
    501  datos generales del pedimento (patente, número, aduana, tipo de cambio,
         RFC importador, peso bruto...)
    502  transporte (línea naviera, buque)
    503  guía / conocimiento de embarque
    504  contenedores
    505  factura del proveedor extranjero (fecha, COVE, incoterm, id fiscal, nombre)
    506  fechas (1 = entrada, 2 = pago)
    507  identificadores a nivel pedimento
    509  tasas a nivel pedimento
    510  contribuciones a nivel pedimento (1 = DTA, 7 = REC, 15 = PRV, 23 = IVA/PRV)
    511  observaciones
    551  PARTIDA: fracción, secuencia, descripción, precio unitario, valor
         aduana, valor comercial, valor USD, cantidad UMC, clave UMC, cantidad
         UMT, clave UMT, país origen...
    553  regulaciones (NOM) por partida
    554  identificadores por partida
    556  tasas por partida (3 = IVA, 6 = IGI)
    557  contribuciones por partida (3 = IVA, 6 = IGI): importe pagado
    800  e.firma del agente aduanal
    801  cierre

Este parser es tolerante: solo lee los campos que el costeo necesita y deja el
resto como está. Layout verificado contra el pedimento impreso (los totales de
IVA/IGI/DTA por partida y por pedimento coinciden con el PDF).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# Claves de contribución del Anexo 22 (apéndice 12) usadas en 510/556/557.
CONTRIB_DTA = "1"
CONTRIB_IVA = "3"
CONTRIB_IGI = "6"
CONTRIB_REC = "7"
CONTRIB_PRV = "15"
CONTRIB_IVA_PRV = "23"

NOMBRES_CONTRIB = {
    "1": "DTA",
    "3": "IVA",
    "6": "IGI",
    "7": "REC",
    "15": "PRV",
    "23": "IVA/PRV",
}


class M3ParseError(ValueError):
    """El archivo no tiene la estructura esperada de un M3."""


@dataclass
class PartidaM3:
    secuencia: int
    fraccion: str
    nico: str | None
    descripcion: str
    precio_unitario: Decimal  # MXN, por unidad UMC
    valor_aduana: Decimal
    valor_comercial: Decimal
    valor_usd: Decimal
    cantidad_umc: Decimal
    umc_clave: str
    cantidad_umt: Decimal | None
    umt_clave: str | None
    pais_origen: str | None
    igi: Decimal = Decimal("0")
    iva: Decimal = Decimal("0")
    tasa_igi: Decimal | None = None
    tasa_iva: Decimal | None = None
    otras_contribuciones: dict[str, str] = field(default_factory=dict)


@dataclass
class PedimentoM3:
    patente: str
    numero: str  # consecutivo, p. ej. "6000018"
    aduana: str  # sección aduanera, p. ej. "510"
    tipo_operacion: str  # "1" importación / "2" exportación
    clave_pedimento: str  # "A1", ...
    rfc_importador: str
    tipo_cambio: Decimal
    peso_bruto: Decimal | None
    fecha_entrada: date | None
    fecha_pago: date | None
    proveedor_id_fiscal: str | None
    proveedor_nombre: str | None
    factura_fecha: date | None
    cove: str | None
    incoterm: str | None
    contenedores: list[str]
    guias: list[str]
    dta: Decimal
    otras_contribuciones: dict[str, str]  # {"REC": "1614", "PRV": "330"...} en texto
    partidas: list[PartidaM3]

    @property
    def numero_completo(self) -> str:
        """Formato impreso: 'AA AD PPPP NNNNNNN' (año, aduana, patente, consecutivo)."""
        anio = (self.fecha_pago or self.fecha_entrada or date.today()).strftime("%y")
        return f"{anio} {self.aduana[:2]} {self.patente} {self.numero}"

    @property
    def valor_aduana_total(self) -> Decimal:
        return sum((p.valor_aduana for p in self.partidas), Decimal("0"))

    @property
    def valor_usd_total(self) -> Decimal:
        return sum((p.valor_usd for p in self.partidas), Decimal("0"))

    @property
    def igi_total(self) -> Decimal:
        return sum((p.igi for p in self.partidas), Decimal("0"))

    @property
    def iva_total(self) -> Decimal:
        return sum((p.iva for p in self.partidas), Decimal("0"))


def _dec(valor: str | None, default: Decimal | None = Decimal("0")) -> Decimal | None:
    if valor is None or valor.strip() == "":
        return default
    try:
        return Decimal(valor.strip())
    except InvalidOperation as exc:
        raise M3ParseError(f"Valor numérico inválido en el M3: {valor!r}") from exc


def _fecha(valor: str | None) -> date | None:
    """Las fechas vienen como DDMMAAAA sin separadores."""
    if not valor or len(valor.strip()) != 8:
        return None
    try:
        return datetime.strptime(valor.strip(), "%d%m%Y").date()
    except ValueError:
        return None


def _campo(campos: list[str], idx: int) -> str | None:
    return campos[idx].strip() if idx < len(campos) and campos[idx].strip() != "" else None


def parse_m3(contenido: bytes | str) -> PedimentoM3:
    """Parsea el contenido completo de un archivo M3 y devuelve el pedimento con sus partidas."""
    if isinstance(contenido, bytes):
        texto = contenido.decode("latin-1")
    else:
        texto = contenido

    lineas = [ln.rstrip("\r\n") for ln in texto.splitlines() if ln.strip()]
    if not lineas:
        raise M3ParseError("El archivo está vacío")

    registros = [ln.split("|") for ln in lineas]
    tipos = {r[0] for r in registros}
    if "501" not in tipos or "551" not in tipos:
        raise M3ParseError(
            "El archivo no parece un M3 de pedimento (faltan registros 501 de encabezado o 551 de partidas)"
        )

    encabezado: list[str] | None = None
    fechas: dict[str, date | None] = {}
    proveedor: list[str] | None = None
    contenedores: list[str] = []
    guias: list[str] = []
    contrib_pedimento: dict[str, Decimal] = {}
    partidas: dict[int, PartidaM3] = {}

    for c in registros:
        tipo = c[0]
        if tipo == "501":
            encabezado = c
        elif tipo == "503":
            if _campo(c, 2):
                guias.append(_campo(c, 2))  # type: ignore[arg-type]
        elif tipo == "504":
            if _campo(c, 2):
                contenedores.append(_campo(c, 2))  # type: ignore[arg-type]
        elif tipo == "505":
            proveedor = c
        elif tipo == "506":
            fechas[_campo(c, 2) or ""] = _fecha(_campo(c, 3))
        elif tipo == "510":
            clave = _campo(c, 2) or ""
            contrib_pedimento[clave] = contrib_pedimento.get(clave, Decimal("0")) + (_dec(_campo(c, 4)) or Decimal("0"))
        elif tipo == "551":
            secuencia = int(_campo(c, 3) or "0")
            partidas[secuencia] = PartidaM3(
                secuencia=secuencia,
                fraccion=_campo(c, 2) or "",
                nico=_campo(c, 4),
                descripcion=_campo(c, 5) or "",
                precio_unitario=_dec(_campo(c, 6)),  # type: ignore[arg-type]
                valor_aduana=_dec(_campo(c, 7)),  # type: ignore[arg-type]
                valor_comercial=_dec(_campo(c, 8)),  # type: ignore[arg-type]
                valor_usd=_dec(_campo(c, 9)),  # type: ignore[arg-type]
                cantidad_umc=_dec(_campo(c, 10)),  # type: ignore[arg-type]
                umc_clave=_campo(c, 11) or "",
                cantidad_umt=_dec(_campo(c, 12), default=None),
                umt_clave=_campo(c, 13),
                pais_origen=_campo(c, 20),
            )
        elif tipo == "556":
            secuencia = int(_campo(c, 3) or "0")
            p = partidas.get(secuencia)
            if p is None:
                continue
            clave, tasa = _campo(c, 4), _dec(_campo(c, 5), default=None)
            if clave == CONTRIB_IVA:
                p.tasa_iva = tasa
            elif clave == CONTRIB_IGI:
                p.tasa_igi = tasa
        elif tipo == "557":
            secuencia = int(_campo(c, 3) or "0")
            p = partidas.get(secuencia)
            if p is None:
                continue
            clave, importe = _campo(c, 4) or "", _dec(_campo(c, 6)) or Decimal("0")
            if clave == CONTRIB_IVA:
                p.iva += importe
            elif clave == CONTRIB_IGI:
                p.igi += importe
            else:
                nombre = NOMBRES_CONTRIB.get(clave, f"contrib_{clave}")
                p.otras_contribuciones[nombre] = str(importe)

    if encabezado is None:
        raise M3ParseError("Falta el registro 501 (encabezado del pedimento)")

    tipo_cambio = _dec(_campo(encabezado, 10), default=None)
    if not tipo_cambio or tipo_cambio <= 0:
        raise M3ParseError("El registro 501 no trae un tipo de cambio válido")

    otras = {
        NOMBRES_CONTRIB.get(k, f"contrib_{k}"): str(v)
        for k, v in contrib_pedimento.items()
        if k != CONTRIB_DTA
    }

    return PedimentoM3(
        patente=_campo(encabezado, 1) or "",
        numero=_campo(encabezado, 2) or "",
        aduana=_campo(encabezado, 3) or "",
        tipo_operacion=_campo(encabezado, 4) or "",
        clave_pedimento=_campo(encabezado, 5) or "",
        rfc_importador=_campo(encabezado, 8) or "",
        tipo_cambio=tipo_cambio,
        peso_bruto=_dec(_campo(encabezado, 16), default=None),
        fecha_entrada=fechas.get("1"),
        fecha_pago=fechas.get("2"),
        proveedor_id_fiscal=_campo(proveedor, 10) if proveedor else None,
        proveedor_nombre=_campo(proveedor, 11) if proveedor else None,
        factura_fecha=_fecha(_campo(proveedor, 2)) if proveedor else None,
        cove=_campo(proveedor, 3) if proveedor else None,
        incoterm=_campo(proveedor, 4) if proveedor else None,
        contenedores=contenedores,
        guias=guias,
        dta=contrib_pedimento.get(CONTRIB_DTA, Decimal("0")),
        otras_contribuciones=otras,
        partidas=[partidas[k] for k in sorted(partidas)],
    )
