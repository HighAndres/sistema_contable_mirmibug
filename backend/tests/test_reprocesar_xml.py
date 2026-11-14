"""Reproceso de XML guardados: rellena los desgloses que el parser viejo no
guardaba, sin tocar cifras ni capturas del contador, y es idempotente."""

from sqlalchemy import delete, select

from app.modules.cfdi.models import Cfdi, CfdiImpuesto, CfdiNomina, CfdiRelacionado
from app.modules.sat.carga_xml import cargar_archivos
from scripts.reprocesar_xml import reprocesar
from tests.conftest import agregar_membresia, crear_empresa, crear_usuario
from tests.test_xml_extendido import EMPRESA, UUID_MIXTO, UUID_NOMINA, XML_MIXTO, XML_NOMINA


def _simular_carga_vieja(db, empresa):
    """Carga los XML con el parser actual y luego borra lo que una carga de
    agosto de 2026 no guardaba, dejando el CFDI como quedó en producción."""
    res = cargar_archivos(db, empresa=empresa, archivos=[("mixto.xml", XML_MIXTO.encode()), ("nomina.xml", XML_NOMINA.encode())])
    assert res.nuevos == 2, res.errores
    ids = [c for c in db.scalars(select(Cfdi.id).where(Cfdi.empresa_id == empresa.id))]
    db.execute(delete(CfdiImpuesto).where(CfdiImpuesto.cfdi_id.in_(ids)))
    db.execute(delete(CfdiRelacionado).where(CfdiRelacionado.cfdi_id.in_(ids)))
    # Borrar la nómina arrastra sus conceptos por el ondelete CASCADE de la FK.
    db.execute(delete(CfdiNomina).where(CfdiNomina.cfdi_id.in_(ids)))
    for cfdi in db.scalars(select(Cfdi).where(Cfdi.id.in_(ids))):
        cfdi.moneda = None
        cfdi.regimen_emisor = None
        cfdi.lugar_expedicion = None
        cfdi.pac_rfc = None
        cfdi.complementos = None
        for c in cfdi.conceptos:
            c.clave_prodserv = None
    db.commit()
    db.expire_all()


def test_reproceso_rellena_sin_tocar_lo_capturado(db, seed_rbac):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc=EMPRESA)
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    _simular_carga_vieja(db, empresa)

    # Captura del contador previa al reproceso: debe sobrevivir intacta.
    mixto = db.scalar(select(Cfdi).where(Cfdi.uuid_fiscal == UUID_MIXTO))
    mixto.clasificacion = "no_deducible"
    mixto.concepto = "REFRESCOS"
    total_antes = mixto.total
    db.commit()

    t = reprocesar(db)
    assert t["errores"] == []
    assert t["con_cambios"] == 2
    assert t["impuestos"] == 2 and t["nomina"] == 1 and t["relacionados"] == 1 and t["conceptos"] == 2

    db.expire_all()
    mixto = db.scalar(select(Cfdi).where(Cfdi.uuid_fiscal == UUID_MIXTO))
    # Desgloses de vuelta, tal como los deja una carga nueva.
    assert {(i.naturaleza, i.impuesto) for i in mixto.impuestos} >= {("traslado", "002"), ("retencion", "001"), ("traslado", "ISH")}
    assert mixto.relacionados[0].uuid_relacionado and mixto.moneda == "MXN"
    assert mixto.regimen_emisor == "601" and mixto.lugar_expedicion == "07780"
    assert all(c.clave_prodserv for c in mixto.conceptos if c.descripcion != "Cuota") and len(mixto.conceptos) == 4
    # Nada capturado ni calculado se movió.
    assert mixto.clasificacion == "no_deducible" and mixto.concepto == "REFRESCOS"
    assert mixto.total == total_antes

    recibo = db.scalar(select(Cfdi).where(Cfdi.uuid_fiscal == UUID_NOMINA))
    assert recibo.nomina is not None
    assert recibo.nomina.registro_patronal == "B5510768108"
    assert len(recibo.nomina.conceptos) == 4  # 1 percepción + 2 deducciones + 1 otro pago

    # Idempotente: una segunda pasada no encuentra nada que rellenar.
    t2 = reprocesar(db)
    assert t2["con_cambios"] == 0 and t2["errores"] == []


def test_reproceso_dry_run_no_guarda(db, seed_rbac):
    usuario = crear_usuario(db)
    empresa = crear_empresa(db, rfc=EMPRESA)
    agregar_membresia(db, usuario=usuario, empresa=empresa, rol=seed_rbac["administrador"])
    _simular_carga_vieja(db, empresa)

    t = reprocesar(db, dry_run=True)
    assert t["con_cambios"] == 2
    db.expire_all()
    mixto = db.scalar(select(Cfdi).where(Cfdi.uuid_fiscal == UUID_MIXTO))
    assert mixto.impuestos == [] and mixto.moneda is None
