"""Seed idempotente de RBAC: crea roles base y catálogo inicial de permisos.

Ejecutar DESPUÉS de aplicar las migraciones:
    python scripts/seed_rbac.py

Es idempotente: si ya existen, no duplica; solo agrega lo que falte.
Los roles se asignan por empresa (ver tenants.models.UsuarioEmpresa), no de
forma global al usuario.
"""

from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.auth.models import Permiso, Rol

# Catálogo inicial de permisos: "recurso.accion".
PERMISOS: dict[str, str] = {
    "empresas.leer": "Ver los datos de la empresa",
    "empresas.editar": "Editar los datos de la empresa",
    "usuarios.leer": "Ver los usuarios de la empresa",
    "usuarios.invitar": "Invitar usuarios a la empresa",
    "credenciales.gestionar": "Conectar/gestionar credenciales del SAT",
    "sat.sincronizar": "Sincronizar CFDIs con el SAT",
    "cfdi.leer": "Ver CFDIs emitidos/recibidos",
    "reportes.leer": "Ver reportes y dashboard fiscal",
    "inventario.leer": "Ver inventario",
    "inventario.ajustar": "Registrar movimientos de inventario",
    "bitacora.leer": "Ver la bitácora de auditoría de la empresa",
}

# Roles base del sistema y los permisos que otorgan.
# "*" = todos los permisos.
ROLES: dict[str, dict] = {
    "administrador": {
        "descripcion": "Control total de la empresa: usuarios, SAT, CFDI, reportes e inventario",
        "permisos": "*",
    },
    "contador": {
        "descripcion": "Operación fiscal y de inventario, sin gestionar usuarios ni credenciales SAT",
        "permisos": [
            "empresas.leer",
            "sat.sincronizar",
            "cfdi.leer",
            "reportes.leer",
            "inventario.leer",
            "inventario.ajustar",
        ],
    },
}


def seed() -> None:
    db = SessionLocal()
    try:
        existentes = {p.codigo: p for p in db.scalars(select(Permiso)).all()}
        for codigo, descripcion in PERMISOS.items():
            if codigo not in existentes:
                p = Permiso(codigo=codigo, descripcion=descripcion)
                db.add(p)
                existentes[codigo] = p
        db.flush()

        roles_db = {r.nombre: r for r in db.scalars(select(Rol)).all()}
        for nombre, cfg in ROLES.items():
            rol = roles_db.get(nombre)
            if rol is None:
                rol = Rol(nombre=nombre, descripcion=cfg["descripcion"], es_sistema=True)
                db.add(rol)
                roles_db[nombre] = rol

            if cfg["permisos"] == "*":
                rol.permisos = list(existentes.values())
            else:
                rol.permisos = [existentes[c] for c in cfg["permisos"]]

        db.commit()
        print(f"Seed OK: {len(existentes)} permisos, {len(roles_db)} roles ({', '.join(roles_db)}).")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
