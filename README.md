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
producto o servicio), `pedimentos` (costeo de importación a partir del archivo M3 del agente
aduanal), `impuestos` (previa de IVA base flujo e ISR provisional por régimen), `conciliacion`
(estados de cuenta bancarios vs CFDI vs declarado), `terceros` (clientes y proveedores con
saldos y antigüedad) y `bitacora` (auditoría de acciones por usuario).

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

### Pruebas automatizadas

```zsh
cd backend
./.venv/bin/pytest tests/ -v
```

Usan una base Postgres separada (`nubinox_test`, se crea sola si no existe) y cada test corre
en su propia transacción con un SAVEPOINT interno (`join_transaction_mode="create_savepoint"`),
así que aunque el código bajo prueba haga `commit()` (como toda la capa `crud/`), al terminar
el test se revierte todo y la base de demo (`nubinox`) nunca se toca. 69 pruebas: login/bloqueo/
tiempo constante/reset/cambio de contraseña, aislamiento entre empresas, invitar usuario,
inventario (stock, atributos, 409 por stock insuficiente), motor de reglas, precisión decimal, y
pedimentos (parser M3 contra el pedimento impreso, costeo contra el Excel, importar → configurar
→ aplicar al inventario), CFDI (filtros, resumen por tipo, serie/folio/método) e impuestos
(IVA base flujo, tarifa art. 96, RESICO, coeficiente de utilidad, configuración fiscal),
dashboard por periodo, vigencias FIEL/CSD, documentos SAT simulados y conciliación (importador
xlsx/csv, auto/manual, declaraciones, resumen a tres columnas) y cargas masivas (productos,
movimientos, catálogo de claves SAT con el Excel real del cliente) y CFDI reales (parser XML 4.0
con Pagos 2.0 y nómina, carga ZIP, ligado REP↔PPD) y terceros (detección, saldos, antigüedad,
carga Excel).

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
2. **Dashboard**: selector de periodo (mensual/anual); tarjetas **configurables** (elegir y
   ordenar, se guarda por empresa en el navegador): ingresos, egresos, utilidad, IVA a cargo/a
   favor e ISR (tomados del módulo `impuestos`), cuentas por cobrar y por pagar (facturas PPD
   sin complemento), CFDIs con alertas; gráfica ingresos vs egresos; alertas de validación
   explicadas por regla; top clientes **y** proveedores; vigencia de e.firma y CSD (aviso a 60
   días); descarga de constancia de situación fiscal y opinión de cumplimiento (PDF simulado).
3. **CFDI**: apartados por tipo (Ingresos / Gastos / Nómina / Pagos / Todos) con tarjetas de
   totales, filtros por estatus (vigente, cancelado, en proceso de cancelación), emisor,
   receptor, mes/año, método (PUE/PPD), forma de pago y búsqueda por UUID/serie/folio;
   columnas UUID, serie-folio, método y forma de pago. Botón "Sincronizar con SAT" (genera
   CFDIs nuevos simulados — incluidos recibos de nómina y facturas PPD — y corre el motor de
   reglas), detalle con conceptos y alertas (p. ej. EFOS detectado).
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

## Pedimentos de importación (costeo)

Réplica del papel de trabajo "PAPEL COSTOS" del despacho, con el archivo **M3** del agente
aduanal (`.003`, `.004`…) como medio principal de captura:

- `POST /pedimentos/importar` recibe el M3 y crea el pedimento con encabezado (registro 501:
  tipo de cambio, RFC, patente, aduana), contribuciones (510: DTA, PRV, REC) y **todas las
  partidas** (551: fracción, descripción, cantidad/UMC, precio unitario, valor aduana/USD; 557:
  IGI e IVA por partida). Parser en `app/modules/pedimentos/parser_m3.py`; verificado contra el
  pedimento impreso (`tests/fixtures/m3382475.003`).
- Costeo (`costeo.py`) por partida: `costo landed = precio + DTA/pza + IGI/pza + gastos/pza`,
  `precio venta = landed + utilidad/pza`, subtotal/IVA 16 %/total de la refactura y la diferencia
  contra el IVA pagado en aduana. DTA, gastos adicionales (fletes, seguros, maniobras…) y
  utilidad se prorratean por **partes iguales** (como el Excel), por valor aduana, por cantidad
  o por peso. Nada calculado se persiste: se deriva siempre de los datos + la configuración.
- "Aplicar al inventario" genera una **entrada** al ledger por partida con
  `StockMovimiento.costo_unitario` (landed), crea los productos que falten (SKU derivado de la
  descripción, categoría "Importación", clave SAT y unidad `c_ClaveUnidad`) y congela el
  pedimento.
- Captura manual (`POST /pedimentos`) como respaldo. Permisos `pedimentos.leer` /
  `pedimentos.gestionar`. Frontend: `/pedimentos` (lista + importar) y `/pedimentos/[id]`
  (costeo, prefactura, exportar a Excel).

## Impuestos: previa de IVA e ISR

- **IVA** (`GET /impuestos/iva?anio&mes`, mensual o anual): base flujo — IVA trasladado
  efectivamente cobrado (facturas PUE + complementos de pago emitidos) menos IVA acreditable
  efectivamente pagado (PUE + REP recibidos); tabla PUE / REP / PPD pendiente / no considerados
  para emitidas y recibidas, y los saldos PPD pendientes (cuentas por cobrar/pagar).
- **ISR** (`GET /impuestos/isr?anio&hasta_mes`): cédula de pagos provisionales enero→mes según
  la mecánica del contribuyente, que se deriva del **RFC** (12 = persona moral, 13 = física) y
  del régimen configurado: PM general (ingresos nominales × coeficiente de utilidad × 30 %),
  PM RESICO (flujo × 30 %), PF RESICO (tasas 1–2.5 % sobre ingresos cobrados) y PF actividad
  empresarial/arrendamiento (tarifa del art. 96 acumulada). Cálculo en
  `app/modules/impuestos/calculos.py`.
- `GET/PUT /impuestos/configuracion` (permiso `empresas.editar`): régimen y coeficiente de
  utilidad de la empresa. Permiso de lectura `impuestos.leer`. Frontend: `/iva` e `/isr`.

## Conciliación (SAT · banco · declarado)

- Cuentas bancarias por empresa y **importación de estados de cuenta** (`.xlsx` / `.csv`,
  `POST /conciliacion/bancos/importar`) con detección flexible de columnas por sinónimos
  (fecha, concepto/descripción, referencia, cargo/retiro, abono/depósito o importe con signo,
  saldo), encabezado en cualquier fila, y deduplicación por huella (reimportar no repite).
  Parser en `app/modules/conciliacion/importador.py`; ejemplo en
  `tests/fixtures/edo_cuenta_ejemplo.xlsx`.
- **Conciliación automática** (`POST /conciliacion/bancos/auto`): liga cada movimiento pendiente
  al único CFDI vigente con el mismo monto (±$0.01), misma dirección del dinero (abono ↔ emitido,
  cargo ↔ recibido) y fecha ±N días; si hay varios candidatos queda "ambiguo" para revisión
  manual. Manual: candidatos por movimiento, ligar, desconciliar, ignorar con nota (comisiones,
  traspasos…).
- **Declaraciones** por periodo (`PUT /conciliacion/declaraciones/{anio}/{mes}`): ingresos,
  deducciones, IVA e ISR presentados, fecha y número de operación.
- **Resumen** (`GET /conciliacion/resumen?anio&mes`): tres columnas — SAT (bóveda: ingresos
  cobrados/facturados, gastos pagados, IVA e ISR del módulo impuestos), banco (abonos/cargos,
  conciliados, % conciliado) y declarado — con diferencias y semáforo. Permisos
  `conciliacion.leer` / `conciliacion.gestionar`. Frontend: `/conciliacion`.

## Carga masiva por Excel / CSV

Capa común en `app/utils/tabular.py` (lectura xlsx/csv, encabezado en cualquier fila,
columnas por sinónimos, números y fechas tolerantes, plantillas). Cada carga valida fila por
fila: las válidas se aplican y las inválidas se devuelven con número de fila y motivo.

- **Productos** (`POST /inventory/productos/importar`, plantilla en `/inventory/productos/plantilla`):
  alta/actualización por SKU; columnas SKU, Nombre, Tipo, Categoría, Unidad SAT, Costo, Clave
  SAT, Activo; cualquier columna extra se guarda como atributo libre.
- **Movimientos** (`POST /inventory/movimientos/importar`): entradas/salidas/ajustes con costo,
  referencia y nota; una salida que deje stock negativo se rechaza solo en esa fila.
- **Catálogo concepto → clave SAT** (`POST /pedimentos/conceptos/importar`, listado y alta
  manual en `/pedimentos/conceptos`): la hoja CATALOGO del papel de trabajo (fixture real
  `tests/fixtures/catalogo_conceptos_sat.xlsx`, ~1,200 conceptos). Al importar un pedimento las
  partidas toman su clave SAT por descripción; `POST /pedimentos/{id}/aplicar-claves` para los ya
  importados. Frontend: componente `carga-masiva-dialog.tsx` usado en Inventario y Pedimentos.

## CFDI reales: carga de XML y camino hacia la descarga del SAT

- `app/modules/sat/xml_parser.py` — parser de CFDI 3.3/4.0: comprobante, emisor/receptor,
  conceptos, IVA trasladado y retenciones (IVA/ISR), Timbre Fiscal Digital, complemento de
  **Pagos** (2.0/1.0: documentos relacionados, parcialidad, saldos, IVA pagado) y **Nómina** 1.2.
- `POST /sat/cargar-xml` (XML sueltos o ZIP): deduplica por UUID, clasifica emitido/recibido por
  el RFC de la empresa, deriva el tipo interno (I → ingreso/egreso, E → nota_credito, P → pago,
  N → nomina), guarda el XML original (`GET /sat/xml/{id}`) y corre el motor de reglas. Los REP
  guardan el monto pagado como total y el IVA de sus documentos: así el IVA en flujo, las
  cuentas por cobrar/pagar y la conciliación funcionan con REP reales; el detalle de una PPD
  muestra sus complementos y el saldo pendiente. Las notas de crédito restan en IVA/ISR.
- `app/modules/sat/descarga.py` — interfaz `ProveedorCfdi` (`mock` hoy; `sat_ws` reservado para la
  descarga masiva con e.firma), para que el resto del sistema no cambie al conectar el SAT real.

## Clientes y proveedores (`terceros`)

- Catálogo por empresa que se **detecta solo desde la bóveda** (`POST /terceros/sincronizar`):
  RFC receptor de lo emitido → cliente, RFC emisor de lo recibido → proveedor, ambos si aplica;
  la nómina no genera clientes. El usuario complementa contacto, días/límite de crédito, CP,
  régimen y notas (alta manual, edición o carga masiva desde Excel con plantilla).
- Cifras siempre calculadas de los CFDI: número de comprobantes, facturado/comprado 12 meses,
  **saldo pendiente** (PPD menos complementos de pago) y **antigüedad** 0-30 / 31-60 / 61-90 /
  >90 días por cobrar y por pagar; bandera **EFOS**. Frontend: `/clientes` y `/proveedores`
  (mismo componente `terceros-page.tsx`), detalle con saldos, historial de CFDI y datos.
  Permisos `terceros.leer` / `terceros.gestionar`.

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
- Sin XSS: React escapa por defecto incluso el JSON libre de `atributos` y las descripciones
  de la bitácora. El único `dangerouslySetInnerHTML` del código es el script de modo oscuro
  (`THEME_INIT_SCRIPT`), una cadena estática sin ningún dato de usuario interpolado — no hay
  `innerHTML` en ningún otro lado.
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

## Otras validaciones hechas después del lanzamiento inicial

- **Precisión decimal**: los montos (`Cfdi.subtotal/iva/total`, `CfdiConcepto.valor_unitario/
  importe`, `Producto.costo_unitario`) son `Decimal` de punta a punta en el backend (antes
  eran `float` aunque la columna ya fuera `Numeric`, así que se perdía precisión binaria en
  cada lectura/escritura y en la suma de cientos de CFDIs). `app/utils/money.py::to_money()`
  cuantiza a 2 decimales cualquier monto que entra por la API antes de guardarlo. Los schemas
  de respuesta se quedan en `float` a propósito (JSON no tiene tipo decimal nativo; el frontend
  no cambió) — la conversión Decimal→float ocurre una sola vez, al final, no en cada paso
  intermedio del cálculo.
- **Navegación móvil**: el sidebar se oculta por debajo de `lg`; ahora hay un botón de
  hamburguesa que abre el mismo menú como panel deslizante (reutiliza el componente `Dialog`),
  filtrado por los mismos permisos que el sidebar de escritorio.
- **Modo oscuro**: botón sol/luna en el header del dashboard y en el login. Se aplica antes de
  hidratar (script inline en `layout.tsx`) para no parpadear en claro al cargar, y persiste en
  `localStorage`.
- **Accesibilidad básica**: `aria-label` en los botones de solo-ícono (menú móvil, tema,
  eliminar usuario, quitar atributo); el botón de cerrar de los diálogos ya traía texto
  accesible (`sr-only`).
