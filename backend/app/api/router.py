"""Router agregador de la API v1: reúne los routers de todos los módulos de negocio."""

from fastapi import APIRouter

from app.modules.admin.router import router as admin_router
from app.modules.auth.router import router as auth_router
from app.modules.bitacora.router import router as bitacora_router
from app.modules.catalogs.router import router as catalogs_router
from app.modules.cfdi.router import router as cfdi_router
from app.modules.conciliacion.router import router as conciliacion_router
from app.modules.credentials.router import router as credentials_router
from app.modules.impuestos.router import router as impuestos_router
from app.modules.inventory.router import router as inventory_router
from app.modules.pedimentos.router import router as pedimentos_router
from app.modules.reports.router import router as reports_router
from app.modules.rules.router import router as rules_router
from app.modules.sat.router import router as sat_router
from app.modules.tenants.router import router as tenants_router
from app.modules.terceros.router import router as terceros_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(tenants_router)
api_router.include_router(catalogs_router)
api_router.include_router(credentials_router)
api_router.include_router(cfdi_router)
api_router.include_router(rules_router)
api_router.include_router(sat_router)
api_router.include_router(reports_router)
api_router.include_router(impuestos_router)
api_router.include_router(conciliacion_router)
api_router.include_router(terceros_router)
api_router.include_router(inventory_router)
api_router.include_router(pedimentos_router)
api_router.include_router(bitacora_router)
api_router.include_router(admin_router)
