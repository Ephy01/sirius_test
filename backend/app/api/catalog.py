from fastapi import APIRouter, Request

from sirius_gate.catalog import describe

from ..dependencies import OrganizerDependency, SettingsDependency
from ..schemas import TaskFamilyCatalogResponse, TaskModuleProblemResponse
from ..tasks import FAMILIES
from ..tasks.modules import load_task_modules
from ..tasks.registry import MODULE_OF

router = APIRouter()


def _catalog(request: Request) -> TaskFamilyCatalogResponse:
    modules = getattr(request.app.state, 'task_modules', [])
    return TaskFamilyCatalogResponse(
        items=[describe(family, MODULE_OF.get(family.key)) for family in FAMILIES.values()],
        problems=[
            TaskModuleProblemResponse(module=module.name, error=module.error)
            for module in modules
            if module.error
        ],
    )


@router.get('/task-families', response_model=TaskFamilyCatalogResponse)
def list_task_families(request: Request, _organizer: OrganizerDependency) -> TaskFamilyCatalogResponse:
    """Every family a contest can use, and the task modules that failed to load."""

    return _catalog(request)


@router.post('/task-modules/reload', response_model=TaskFamilyCatalogResponse)
def reload_task_modules(
    request: Request, settings: SettingsDependency, _organizer: OrganizerDependency
) -> TaskFamilyCatalogResponse:
    """Read the modules directory again, so an author sees an edited module without a restart."""

    request.app.state.task_modules = load_task_modules(settings.task_modules_dir)
    return _catalog(request)
