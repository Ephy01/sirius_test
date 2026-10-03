from fastapi import APIRouter
from sqlalchemy import select

from ..dependencies import SessionDependency, SettingsDependency
from ..schemas import HealthResponse

router = APIRouter()


@router.get('/health', response_model=HealthResponse)
def health(settings: SettingsDependency) -> HealthResponse:
    return HealthResponse(status='ok', service=settings.app_name)


@router.get('/ready', response_model=HealthResponse)
def ready(session: SessionDependency, settings: SettingsDependency) -> HealthResponse:
    """Ready only when the database answers a query."""

    session.execute(select(1))
    return HealthResponse(status='ok', service=settings.app_name)
