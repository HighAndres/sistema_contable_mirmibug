# Nubinox

Sistema contable/fiscal multi-empresa inspirado en iAudita.com (bóveda fiscal de CFDI,
validaciones tipo EFOS, dashboard de IVA/ISR y flujo de caja), con un módulo de
**inventarios** como diferenciador. La conexión con el SAT está **simulada** (mock): no
se maneja e.firma/CIEC reales, así que la demo no depende de un RFC de prueba.

## Estructura

```
backend/    API FastAPI + PostgreSQL + SQLAlchemy 2.0 + Alembic
frontend/   Next.js 14 + TypeScript + Tailwind + shadcn/ui
```

Backend organizado por módulo de negocio (`app/modules/<dominio>/{models,schemas,crud,router}.py`):
`auth` (JWT + RBAC), `tenants` (empresas/multi-RFC), `catalogs` (catálogos SAT), `credentials`
(conexión SAT simulada), `sat` (sincronización simulada de CFDIs), `cfdi`, `rules` (motor de
validación), `reports` (dashboard fiscal), `inventory` (ledger de stock, adaptable a cualquier
producto o servicio) y `bitacora` (auditoría de acciones por usuario).

## Backend — puesta en marcha (macOS / zsh)

```zsh
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configuración
cp .env.example .env   # ajustar credenciales de PostgreSQL si hace falta

# Base de datos
PYTHONPATH=. python scripts/create_db.py   # crea la base 'nubinox'
alembic upgrade head                       # aplica migraciones
PYTHONPATH=. python scripts/seed_rbac.py       # roles y permisos base
PYTHONPATH=. python scripts/seed_catalogs.py   # catálogos SAT (subconjunto real)
PYTHONPATH=. python scripts/seed_demo.py       # empresa, usuarios, ~150 CFDIs, inventario

# Servidor
PYTHONPATH=. uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Docs: http://127.0.0.1:8000/docs
- Health: `/health` (liveness) · `/health/db` (readiness)

## Frontend — puesta en marcha

```zsh
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL apunta al backend
npm run dev
```

- App: http://localhost:3000 (requiere el backend corriendo en :8000)

## Usuarios de demo

Sembrados por `scripts/seed_demo.py`:

| Usuario | Rol | Alcance | Contraseña |
|---|---|---|---|
| superadmin@nubinox.demo | superadmin | **Todas** las empresas del sistema, todos los permisos | Demo1234! |
| admin@nubinox.demo | administrador | Solo Nubinox Demo SA de CV | Demo1234! |
| contador@nubinox.demo | contador | Solo Nubinox Demo SA de CV, permisos acotados | Demo1234! |

El superadmin no pertenece a ninguna empresa vía membresía (`usuario_empresas`): el backend
le da acceso directo a cualquier `empresa_id` con todos los permisos (ver
`app/api/deps.py::get_current_empresa`). Es el rol de soporte/operación de la plataforma, no
un rol de negocio — pensado para quien administra Nubinox, no para el cliente final.

## Flujo de demo sugerido

1. Login como `admin@nubinox.demo`.
2. **Dashboard**: KPIs fiscales (ingresos, egresos, utilidad, IVA por pagar, ISR estimado),
   gráfica de ingresos vs egresos y alertas de validación.
3. **CFDI**: lista filtrable, botón "Sincronizar con SAT" (genera CFDIs nuevos simulados y
   corre el motor de reglas), detalle con conceptos y alertas (p. ej. EFOS detectado).
4. **Inventario**: stock actual por almacén, historial de movimientos, registrar entradas/
   salidas/ajustes (bloquea si el stock quedaría negativo).
5. **Reportes**: tendencia de utilidad, top clientes y proveedores.
6. **Empresas**: crear una empresa nueva (te vuelve su administrador automáticamente),
   conectar el SAT (simulado).
7. **Bitácora**: quién hizo qué y cuándo (crear empresa, conectar/sincronizar SAT, alta de
   producto/almacén, movimientos de inventario).
8. **Usuarios**: invitar a alguien a la empresa (solo correos sin cuenta previa — ver
   Seguridad más abajo) y, si entraste como superadmin, la sección adicional de
   administración de la plataforma (crear/activar/desactivar/eliminar cualquier usuario).
9. **Reportes** y **CFDI** traen botón "Exportar a Excel" (se genera en el navegador con los
   datos ya cargados, sin ida y vuelta al backend).
10. Cierra sesión y entra como `contador@nubinox.demo` para ver el mismo flujo con permisos
    más acotados (sin gestión de credenciales SAT, usuarios ni bitácora).
11. Entra como `superadmin@nubinox.demo` para ver **todas** las empresas del sistema en el
    selector del encabezado (no solo la demo), cada una con acceso total, más la sección de
    administración global en Usuarios.
12. Prueba "¿Olvidaste tu contraseña?" desde el login: el enlace de reset no se envía por
    correo (no hay servicio de correo), se imprime en la consola del backend (busca `[DEV]`).

## Notas

- `bcrypt` está fijado en `4.0.1` por compatibilidad con `passlib`.
- El RBAC es **por empresa**, no global al usuario: la tabla `usuario_empresas` liga un
  usuario a una empresa con un rol específico, así puede ser administrador en una empresa y
  contador en otra.
- El generador de CFDIs mock (`app/modules/sat/mock_generator.py`) no usa librerías externas
  (Faker, etc.) y sesga los montos para que la empresa demo se vea rentable.
- `Producto` es un catálogo abierto: `categoria` es texto libre (cada empresa nombra las
  suyas) y `atributos` es JSON arbitrario (`{"color": "negro", "ram_gb": 16}`, etc.), para que
  el mismo modelo sirva para cualquier giro sin migraciones nuevas. `tipo` distingue
  `producto` (con control de existencias) de `servicio` (sin stock).
- La bitácora se escribe **después** de que la acción principal tuvo éxito, y solo para
  escrituras con impacto de negocio (no audita cada GET).

## Seguridad

Auditoría propia sobre este sistema (no hay componentes de terceros con CVEs conocidos que
gestionar; todo el hallazgo es de diseño propio). Corregido:

- **Bloqueo de cuenta**: 5 intentos fallidos de login bloquean la cuenta 15 minutos
  (`Usuario.intentos_fallidos` / `bloqueado_hasta`, configurable en `.env`).
- **Login a tiempo constante**: antes, un correo inexistente respondía más rápido que uno
  real con contraseña incorrecta (no había hash contra el cual comparar) — se filtraba por
  temporización qué correos existen. Ahora siempre corre bcrypt contra un hash señuelo
  (`verify_password_o_dummy`).
- **Invalidación de sesión al cambiar contraseña**: los JWT llevan un claim `tv`
  (`token_version`) que se compara contra `Usuario.token_version` en cada request. Antes, un
  access/refresh token robado seguía siendo válido hasta su expiración natural (hasta 7 días)
  aunque la víctima cambiara su contraseña; ahora se invalida al instante (`set_password`
  incrementa `token_version`), y lo mismo aplica al desactivar una cuenta.
- **Contraseñas**: longitud mínima de 8 caracteres validada en el backend (Pydantic
  `Field(min_length=...)`), no solo en el frontend.
- **Invitar usuarios**: un administrador de empresa solo puede invitar correos que **no**
  tengan cuenta todavía (se crea una nueva con contraseña temporal). Antes, invitar un correo
  ya existente lo agregaba a la empresa sin su consentimiento, y de paso servía como oráculo
  para saber qué correos ya están registrados en la plataforma — cualquiera puede crear una
  empresa gratis y usar "invitar" para probar correos. Vincular una cuenta ya existente a otra
  empresa ahora requiere un superadmin (`/admin/usuarios`).
- **Superadmin**: no hay forma de auto-otorgarse `is_superadmin` vía API (ni en `/auth/register`
  ni en `/tenants/usuarios/invitar`) — solo se asigna por seed/DB directa, o por otro
  superadmin ya autenticado vía `/admin/usuarios`. Un superadmin no puede desactivarse ni
  eliminarse a sí mismo por accidente.

Verificado y sin hallazgos:
- Aislamiento entre empresas: toda consulta de negocio filtra por `empresa_id` derivado de
  `X-Empresa-Id` + membresía (o el bypass explícito de superadmin), nunca de un `empresa_id`
  tomado directamente del body/query de otro endpoint.
- Sin SQL injection (SQLAlchemy parametrizado en todo el código, sin f-strings hacia SQL).
- Sin XSS (no hay `dangerouslySetInnerHTML`/`innerHTML` en el frontend; React escapa por
  defecto incluso el JSON libre de `atributos` y las descripciones de la bitácora).
- CORS restringido a orígenes explícitos (`BACKEND_CORS_ORIGINS`), sin comodín.
- JWT con algoritmo fijo (`HS256` desde `settings`, no tomado del propio token) — sin
  superficie para "alg confusion".

Aceptado como riesgo conocido (fuera de alcance para una demo):
- `/auth/register` revela si un correo ya tiene cuenta (409 vs 201) — tradeoff común de UX de
  registro; `/auth/forgot-password` sí es deliberadamente genérico.
- Tokens en `localStorage` (no cookies `httpOnly`) — mismo patrón que los otros proyectos de
  referencia; más expuesto a robo vía XSS si alguna vez se introdujera uno, pero no hay ningún
  sink de XSS en el código actual.
- Sin límite de tamaño en el JSON de `atributos` de producto — requiere ya tener el permiso
  `inventario.ajustar`, así que el abuso requiere una cuenta autenticada y privilegiada.
