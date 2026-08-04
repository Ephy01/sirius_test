from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401 - registers SQLAlchemy metadata
from .ai import provider_from_settings
from .api import router
from .config import Settings, get_settings
from .database import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    is_production = resolved_settings.environment.casefold() == "production"
    database = Database(resolved_settings.database_url)
    ai_provider = provider_from_settings(resolved_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Local development and tests keep their zero-setup SQLite workflow.
        # Production schema changes are applied only by Alembic in the
        # container entrypoint, so a missing revision cannot be hidden by
        # create_all silently creating new tables.
        if not is_production:
            database.create_schema()
        yield
        if ai_provider is not None:
            ai_provider.close()
        database.dispose()

    application = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )
    application.state.settings = resolved_settings
    application.state.database = database
    application.state.ai_provider = ai_provider
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.parsed_cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition"],
    )
    application.include_router(router)
    return application


app = create_app()
