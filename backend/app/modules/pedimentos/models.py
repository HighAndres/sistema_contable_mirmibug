"""Pedimentos de importación y sus partidas: la fuente del costeo de importación.

Un pedimento se captura casi siempre importando el archivo M3 (".003") del
agente aduanal (ver parser_m3.py); la captura manual existe como respaldo.
Los valores CALCULADOS (DTA por pieza, costo unitario, prefactura...) no se
persisten: se derivan siempre de los datos de entrada + la configuración de
prorrateo del pedimento (ver costeo.py), igual que las fórmulas del Excel.
Lo único que se "congela" es el costo con el que se dio entrada al inventario
(StockMovimiento.costo_unitario) al aplicar el pedimento.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Pedimento(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "pedimentos"
    __table_args__ = (
        # El mismo consecutivo se repite entre aduanas/patentes; la llave real es la terna.
        UniqueConstraint("empresa_id", "aduana", "patente", "numero", name="uq_pedimento_empresa_aduana_patente_numero"),
    )

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # ---- Identificación (registro 501 del M3 / encabezado del pedimento impreso) ----
    numero: Mapped[str] = mapped_column(String(10), nullable=False)  # consecutivo, "6000018"
    patente: Mapped[str] = mapped_column(String(6), nullable=False)  # "3382"
    aduana: Mapped[str] = mapped_column(String(5), nullable=False)  # sección aduanera, "510"
    clave_pedimento: Mapped[str | None] = mapped_column(String(5))  # "A1"
    tipo_operacion: Mapped[str | None] = mapped_column(String(3))  # "1" imp / "2" exp
    rfc_importador: Mapped[str | None] = mapped_column(String(13))
    referencia: Mapped[str | None] = mapped_column(String(60))  # operación interna, "LMA26-019"

    fecha_entrada: Mapped[date | None] = mapped_column(Date)
    fecha_pago: Mapped[date | None] = mapped_column(Date, index=True)

    tipo_cambio: Mapped[Decimal] = mapped_column(Numeric(12, 5), nullable=False)
    peso_bruto: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    incoterm: Mapped[str | None] = mapped_column(String(5))
    proveedor_nombre: Mapped[str | None] = mapped_column(String(255))
    proveedor_id_fiscal: Mapped[str | None] = mapped_column(String(40))
    contenedores: Mapped[list | None] = mapped_column(JSON)
    guias: Mapped[list | None] = mapped_column(JSON)

    # ---- Contribuciones a nivel pedimento ----
    dta: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    # {"REC": "1614", "PRV": "330", ...} solo informativo (no se prorratean; el
    # papel de trabajo únicamente reparte el DTA).
    otras_contribuciones: Mapped[dict | None] = mapped_column(JSON)

    # ---- Configuración del costeo (lo que en el Excel eran celdas sueltas) ----
    # [{"concepto": "Flete marítimo", "monto": 52680}, ...] — fletes, seguros,
    # maniobras, honorarios: solo cuando existen (opcional).
    gastos_adicionales: Mapped[list | None] = mapped_column(JSON)
    utilidad: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    metodo_prorrateo: Mapped[str] = mapped_column(
        String(20), default="partes_iguales", server_default="partes_iguales", nullable=False
    )

    # borrador (editable) | aplicado (ya generó entradas al inventario; congelado)
    estatus: Mapped[str] = mapped_column(String(15), default="borrador", server_default="borrador", nullable=False)
    aplicado_almacen_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("almacenes.id", ondelete="SET NULL"))
    origen: Mapped[str] = mapped_column(String(10), default="m3", server_default="m3", nullable=False)  # m3 | manual
    archivo_nombre: Mapped[str | None] = mapped_column(String(120))
    notas: Mapped[str | None] = mapped_column(String(500))

    partidas: Mapped[list["PedimentoPartida"]] = relationship(
        back_populates="pedimento",
        cascade="all, delete-orphan",
        order_by="PedimentoPartida.secuencia",
        lazy="selectin",
    )

    @property
    def numero_completo(self) -> str:
        anio = (self.fecha_pago or self.fecha_entrada or self.created_at.date()).strftime("%y")
        return f"{anio} {self.aduana[:2]} {self.patente} {self.numero}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Pedimento {self.numero_completo}>"


class PedimentoPartida(UUIDPKMixin, Base):
    __tablename__ = "pedimento_partidas"
    __table_args__ = (UniqueConstraint("pedimento_id", "secuencia", name="uq_partida_pedimento_secuencia"),)

    pedimento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pedimentos.id", ondelete="CASCADE"), index=True, nullable=False
    )
    secuencia: Mapped[int] = mapped_column(Integer, nullable=False)
    fraccion: Mapped[str] = mapped_column(String(10), nullable=False)
    nico: Mapped[str | None] = mapped_column(String(4))
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    pais_origen: Mapped[str | None] = mapped_column(String(3))

    cantidad_umc: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    umc_clave: Mapped[str] = mapped_column(String(3), nullable=False)  # clave del pedimento ("6" = pieza)
    cantidad_umt: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    umt_clave: Mapped[str | None] = mapped_column(String(3))

    # Numeric(18,6): el M3 trae precios unitarios con 5 decimales (0.73723).
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)  # MXN por UMC
    valor_aduana: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    valor_comercial: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    valor_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    igi: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    iva: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)  # IVA de importación
    tasa_igi: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    tasa_iva: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))

    # Para la refactura al cliente (cols G/AD y AE del Excel). Editables.
    clave_prodserv: Mapped[str | None] = mapped_column(String(10))
    clave_unidad_sat: Mapped[str | None] = mapped_column(String(5))
    # Producto del catálogo al que entra esta partida (se resuelve al aplicar si viene vacío).
    producto_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("productos.id", ondelete="SET NULL"))

    pedimento: Mapped[Pedimento] = relationship(back_populates="partidas")
    producto = relationship("Producto", lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PedimentoPartida {self.secuencia} {self.descripcion}>"


class ConceptoClaveSat(UUIDPKMixin, TimestampMixin, Base):
    """Catálogo por empresa: descripción de mercancía → clave c_ClaveProdServ.
    Es la hoja CATALOGO del papel de trabajo (el VLOOKUP de la columna G): al
    importar un pedimento, cada partida busca aquí su clave por descripción."""

    __tablename__ = "pedimento_conceptos_sat"
    __table_args__ = (UniqueConstraint("empresa_id", "concepto_norm", name="uq_concepto_sat_empresa"),)

    empresa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"), index=True, nullable=False)
    concepto: Mapped[str] = mapped_column(String(255), nullable=False)
    concepto_norm: Mapped[str] = mapped_column(String(255), nullable=False)  # mayúsculas sin acentos, para buscar
    clave_prodserv: Mapped[str] = mapped_column(String(10), nullable=False)
    clave_unidad_sat: Mapped[str | None] = mapped_column(String(5))
