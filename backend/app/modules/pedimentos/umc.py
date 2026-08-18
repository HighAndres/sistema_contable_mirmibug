"""Unidades de medida del pedimento (Anexo 22, apéndice 7) → clave SAT para
facturar (c_ClaveUnidad del CFDI 4.0). Espejo de la hoja "UMC" del papel de
trabajo, que es la que el despacho usa para refacturar."""

UMC: dict[str, tuple[str, str]] = {
    # clave pedimento: (descripción, c_ClaveUnidad para facturar)
    "1": ("KILO", "KGM"),
    "2": ("GRAMO", "GRM"),
    "3": ("METRO LINEAL", "LM"),
    "4": ("METRO CUADRADO", "MTK"),
    "5": ("METRO CUBICO", "MTQ"),
    "6": ("PIEZA", "H87"),
    "7": ("CABEZA", "HEA"),
    "8": ("LITRO", "LTR"),
    "9": ("PAR", "PR"),
    "10": ("KILOWATT", "KWT"),
    "11": ("MILLAR", "MIL"),
    "12": ("JUEGO", "SET"),
    "13": ("KILOWATT/HORA", "KWH"),
    "14": ("TONELADA", "TNE"),
    "15": ("BARRIL", "BLL"),
    "16": ("GRAMO NETO", "GRM"),
    "17": ("DECENAS", "TP"),
    "18": ("CIENTOS", "HC"),
    "19": ("DOCENAS", "DPC"),
    "20": ("CAJA", "XBX"),
    "21": ("BOTELLA", "XBQ"),
}


def umc_descripcion(clave: str | None) -> str | None:
    return UMC.get(clave or "", (None, None))[0]


def umc_clave_sat(clave: str | None) -> str | None:
    return UMC.get(clave or "", (None, None))[1]
