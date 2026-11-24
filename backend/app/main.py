from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import Settings
from app.db.session import build_engine, build_session_factory
from app.scanner.checks.catalog import build_check_registry


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.from_env()
    engine = build_engine(configured.database_url)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        engine.dispose()

    application = FastAPI(title="Mini Gauntlet API", lifespan=lifespan)
    application.state.settings = configured
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.check_registry = build_check_registry()
    application.include_router(router)
    return application


app = create_app()
