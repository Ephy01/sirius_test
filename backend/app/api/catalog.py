from fastapi import APIRouter, Request

from ..contest_config import MAX_DIFFICULTY
from ..dependencies import OrganizerDependency, SettingsDependency
from ..schemas import (
    TaskFamilyCatalogResponse,
    TaskFamilyResponse,
    TaskModuleProblemResponse,
    TaskVariantResponse,
)
from ..tasks import FAMILIES, TaskFamily
from ..tasks.family import FamilyCard, Variant
from ..tasks.modules import load_task_modules
from ..tasks.registry import MODULE_OF

router = APIRouter()


def _family_response(family: TaskFamily) -> TaskFamilyResponse:
    card = family.card or FamilyCard(title=family.key)
    module = MODULE_OF.get(family.key)
    return TaskFamilyResponse(
        key=family.key,
        title=card.title,
        description=card.description,
        version=family.version,
        source='module' if module else 'builtin',
        module=module,
        listed=card.listed and not family.scripted_only,
        scripted_only=family.scripted_only,
        interactive=bool(family.actions),
        default_weight=card.weight,
        default_skin=card.skin,
        min_difficulty=1,
        max_difficulty=MAX_DIFFICULTY,
        variants=[
            TaskVariantResponse(
                key=key,
                title=card.variants.get(key, Variant(key)).title,
                description=card.variants.get(key, Variant(key)).description,
            )
            for key in family.sub_kinds
        ],
    )


def _catalog(request: Request) -> TaskFamilyCatalogResponse:
    modules = getattr(request.app.state, 'task_modules', [])
    return TaskFamilyCatalogResponse(
        items=[_family_response(family) for family in FAMILIES.values()],
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
