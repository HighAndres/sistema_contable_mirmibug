"""Pruebas unitarias del motor de reglas (app/modules/rules/engine.py).

Sin base de datos: evaluar_cfdi() solo necesita atributos por duck-typing,
así que se usan SimpleNamespace en vez de instancias reales de Cfdi.
"""

from datetime import date, timedelta
from types import SimpleNamespace

from app.modules.rules.engine import evaluar_cfdi


def _cfdi(**overrides):
    base = dict(
        rfc_emisor="ABC010101AAA",
        rfc_receptor="XYZ020202BBB",
        direccion="emitido",
        tipo="ingreso",
        subtotal=1000,
        conceptos=[SimpleNamespace(importe=1000)],
        fecha=date.today(),
        forma_pago_codigo="01",
        estatus="vigente",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_detecta_rfc_efos_en_recibido():
    cfdi = _cfdi(direccion="recibido", rfc_emisor="EFO900101AAA")
    alertas = evaluar_cfdi(cfdi)
    codigos = {a[0] for a in alertas}
    assert "efos_detectado" in codigos


def test_no_marca_efos_si_rfc_es_limpio():
    cfdi = _cfdi()
    alertas = evaluar_cfdi(cfdi)
    codigos = {a[0] for a in alertas}
    assert "efos_detectado" not in codigos


def test_detecta_descuadre_de_subtotal():
    cfdi = _cfdi(subtotal=1000, conceptos=[SimpleNamespace(importe=500)])
    alertas = evaluar_cfdi(cfdi)
    codigos = {a[0] for a in alertas}
    assert "descuadre_subtotal" in codigos


def test_no_marca_descuadre_dentro_de_tolerancia():
    cfdi = _cfdi(subtotal=1000, conceptos=[SimpleNamespace(importe=999.5)])
    alertas = evaluar_cfdi(cfdi)
    codigos = {a[0] for a in alertas}
    assert "descuadre_subtotal" not in codigos


def test_detecta_complemento_de_pago_pendiente():
    cfdi = _cfdi(
        forma_pago_codigo="99",
        fecha=date.today() - timedelta(days=45),
        tipo="ingreso",
        estatus="vigente",
    )
    alertas = evaluar_cfdi(cfdi)
    codigos = {a[0] for a in alertas}
    assert "complemento_pago_pendiente" in codigos


def test_no_marca_complemento_pendiente_si_cfdi_esta_cancelado():
    cfdi = _cfdi(
        forma_pago_codigo="99",
        fecha=date.today() - timedelta(days=45),
        estatus="cancelado",
    )
    alertas = evaluar_cfdi(cfdi)
    codigos = {a[0] for a in alertas}
    assert "complemento_pago_pendiente" not in codigos


def test_no_marca_complemento_pendiente_dentro_del_plazo():
    cfdi = _cfdi(forma_pago_codigo="99", fecha=date.today() - timedelta(days=5))
    alertas = evaluar_cfdi(cfdi)
    codigos = {a[0] for a in alertas}
    assert "complemento_pago_pendiente" not in codigos
