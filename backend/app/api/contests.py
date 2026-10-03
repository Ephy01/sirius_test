from fastapi import APIRouter, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..contest_config import validate_task_config
from ..dependencies import OrganizerDependency, SessionDependency, api_error
from ..models import Contest, ContestStatus, utc_now
from ..schemas import ContestCreate, ContestListResponse, ContestResponse

router = APIRouter()


def get_contest_or_404(session: Session, contest_id: str) -> Contest:
    contest = session.get(Contest, contest_id)
    if contest is None:
        raise api_error(status.HTTP_404_NOT_FOUND, 'CONTEST_NOT_FOUND', 'Контест не найден.')
    return contest


@router.get('/contests', response_model=ContestListResponse)
def list_contests(session: SessionDependency, _organizer: OrganizerDependency) -> ContestListResponse:
    contests = session.scalars(select(Contest).order_by(Contest.created_at.desc())).all()
    return ContestListResponse(items=list(contests))


@router.post('/contests', response_model=ContestResponse, status_code=status.HTTP_201_CREATED)
def create_contest(
    payload: ContestCreate, session: SessionDependency, _organizer: OrganizerDependency
) -> Contest:
    validate_task_config(payload.task_config)
    contest = Contest(**payload.model_dump())
    session.add(contest)
    session.commit()
    session.refresh(contest)
    return contest


@router.delete('/contests/{contest_id}', status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_contest(contest_id: str, session: SessionDependency, _organizer: OrganizerDependency) -> Response:
    session.delete(get_contest_or_404(session, contest_id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post('/contests/{contest_id}/publish', response_model=ContestResponse)
def publish_contest(contest_id: str, session: SessionDependency, _organizer: OrganizerDependency) -> Contest:
    contest = get_contest_or_404(session, contest_id)
    if contest.status == ContestStatus.DRAFT:
        contest.status = ContestStatus.PUBLISHED
        contest.published_at = utc_now()
        session.commit()
        session.refresh(contest)
    return contest
