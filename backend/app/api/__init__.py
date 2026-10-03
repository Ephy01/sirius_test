"""HTTP API of the service, one module per area."""

from fastapi import APIRouter

from . import access, assistant, catalog, contests, enrollments, health, participant, tasks

router = APIRouter(prefix='/api/v1')
for module in (health, access, catalog, contests, enrollments, participant, tasks, assistant):
    router.include_router(module.router)
