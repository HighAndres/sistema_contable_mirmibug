"""Catálogo c_RegimenFiscal del SAT con dos datos que el catálogo oficial no
trae y que el sistema necesita para "aplicar automáticamente la lógica
adecuada" (acuerdo con el cliente, 2026-09-07):

* a qué tipo de persona aplica (física, moral o ambas), para que el alta de
  empresa solo ofrezca regímenes válidos para el RFC capturado; y
* la mecánica de ISR provisional que le corresponde (ver calculos.py).

Es la fuente única: seed_catalogs.py y el endpoint /tenants/regimenes se
alimentan de aquí. Cuando el cliente entregue su tabla régimen → cálculo,
se ajusta en este archivo.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegimenFiscal:
    codigo: str
    nombre: str
    fisica: bool
    moral: bool
    # pm_general | pm_resico | pf_resico | pf_actividad | no_aplica
    mecanica_isr: str

    @property
    def tipos_persona(self) -> list[str]:
        out = []
        if self.fisica:
            out.append("fisica")
        if self.moral:
            out.append("moral")
        return out

    def aplica_a(self, tipo_persona: str) -> bool:
        return tipo_persona in self.tipos_persona


# (código, nombre, física, moral, mecánica)
_TABLA: list[tuple[str, str, bool, bool, str]] = [
    ("601", "General de Ley Personas Morales", False, True, "pm_general"),
    ("603", "Personas Morales con Fines no Lucrativos", False, True, "no_aplica"),
    ("605", "Sueldos y Salarios e Ingresos Asimilados a Salarios", True, False, "no_aplica"),
    ("606", "Arrendamiento", True, False, "pf_actividad"),
    ("607", "Régimen de Enajenación o Adquisición de Bienes", True, False, "no_aplica"),
    ("608", "Demás ingresos", True, False, "no_aplica"),
    ("610", "Residentes en el Extranjero sin Establecimiento Permanente en México", True, True, "no_aplica"),
    ("611", "Ingresos por Dividendos (socios y accionistas)", True, False, "no_aplica"),
    ("612", "Personas Físicas con Actividades Empresariales y Profesionales", True, False, "pf_actividad"),
    ("614", "Ingresos por intereses", True, False, "no_aplica"),
    ("615", "Régimen de los ingresos por obtención de premios", True, False, "no_aplica"),
    ("616", "Sin obligaciones fiscales", True, False, "no_aplica"),
    ("620", "Sociedades Cooperativas de Producción que optan por diferir sus ingresos", False, True, "pm_general"),
    ("621", "Incorporación Fiscal", True, False, "pf_actividad"),
    ("622", "Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras", False, True, "pm_general"),
    ("623", "Opcional para Grupos de Sociedades", False, True, "pm_general"),
    ("624", "Coordinados", False, True, "pm_general"),
    ("625", "Actividades Empresariales con ingresos a través de Plataformas Tecnológicas", True, False, "pf_actividad"),
    ("626", "Régimen Simplificado de Confianza (RESICO)", True, True, "resico"),
]

REGIMENES: dict[str, RegimenFiscal] = {c: RegimenFiscal(c, n, f, m, mec) for c, n, f, m, mec in _TABLA}


def get_regimen(codigo: str | None) -> RegimenFiscal | None:
    return REGIMENES.get((codigo or "").strip())


def regimenes_para(tipo_persona: str | None = None) -> list[RegimenFiscal]:
    """Lista ordenada por código; filtrada por tipo de persona si se indica."""
    return [r for r in REGIMENES.values() if tipo_persona is None or r.aplica_a(tipo_persona)]


def mecanica_isr(*, tipo_persona: str, regimen_codigo: str | None) -> str:
    """Mecánica de ISR provisional para el par (tipo de persona, régimen).

    Sin régimen configurado se asume la mecánica más común de cada tipo de
    persona (PM general / PF actividad) y el módulo de impuestos avisa que
    falta configurarlo. RESICO se desdobla según el tipo de persona.
    """
    r = get_regimen(regimen_codigo)
    if r is None:
        return "pm_general" if tipo_persona == "moral" else "pf_actividad"
    if r.mecanica_isr == "resico":
        return "pf_resico" if tipo_persona == "fisica" else "pm_resico"
    return r.mecanica_isr


def validar_regimen(*, rfc: str, regimen_codigo: str | None) -> str | None:
    """Devuelve el mensaje de error si el régimen no existe o no aplica al tipo
    de persona que define el RFC; None si es válido (o no se envió régimen)."""
    if not regimen_codigo:
        return None
    r = get_regimen(regimen_codigo)
    if r is None:
        return f"El régimen fiscal '{regimen_codigo}' no existe en el catálogo del SAT"
    tipo = "fisica" if len(rfc.strip()) == 13 else "moral"
    if not r.aplica_a(tipo):
        persona = "persona física" if tipo == "fisica" else "persona moral"
        return f"El régimen {r.codigo} · {r.nombre} no aplica a una {persona} (RFC de {len(rfc.strip())} caracteres)"
    return None
