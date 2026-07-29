from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes import health
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="Sistema contable/fiscal multi-empresa con inventarios.",
        debug=settings.DEBUG,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if settings.DEBUG else None,
        docs_url="/docs" if settings.DEBUG else None,
    )

    if settings.BACKEND_CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.BACKEND_CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Rutas de sistema (sin prefijo de versión, para sondas/healthchecks).
    app.include_router(health.router)

    # Routers de negocio bajo /api/v1.
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
