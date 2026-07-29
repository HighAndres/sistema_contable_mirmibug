"""Confirma la corrección de precisión decimal: los montos se guardan y leen
como Decimal exacto, sin arrastrar residuo de punto flotante binario."""

from decimal import Decimal

from app.modules.sat.mock_generator import generar_cfdis_mock
from tests.conftest import agregar_membresia, auth_headers, crear_empresa, crear_usuario


def test_cfdi_amounts_are_decimal_and_exact(db):
    empresa = crear_empresa(db)
    cfdis = generar_cfdis_mock(db, empresa=empresa, cantidad=25, dias_atras=60, seed=7)

    for cfdi in cfdis:
        assert isinstance(cfdi.subtotal, Decimal)
        assert isinstance(cfdi.iva, Decimal)
        assert isinstance(cfdi.total, Decimal)

        # subtotal + iva == total exacto (sin tolerancia): si algo pasara por
        # float en el camino, esta igualdad exacta empezaría a fallar.
        assert cfdi.subtotal + cfdi.iva == cfdi.total

        suma_conceptos = sum((c.importe for c in cfdi.conceptos), Decimal("0"))
        assert suma_conceptos == cfdi.subtotal
        for concepto in cfdi.conceptos:
            assert isinstance(concepto.importe, Decimal)
            assert isinstance(concepto.valor_unitario, Decimal)


def test_producto_costo_unitario_se_cuantiza_a_dos_decimales(client, seed_rbac, db):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db)
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    headers = auth_headers(client, email=usuario.email, password="Demo1234!", empresa_id=empresa.id)

    # 19.999999 no es un monto real, pero simula un float con más "cola" que
    # 2 decimales llegando desde el frontend — debe cuantizarse a 2 decimales.
    res = client.post(
        "/api/v1/inventory/productos",
        headers=headers,
        json={"sku": "PREC-1", "nombre": "Producto de precisión", "costo_unitario": 19.999999},
    )
    assert res.status_code == 201
    assert res.json()["costo_unitario"] == 20.0
