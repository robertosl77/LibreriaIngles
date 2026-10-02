from fastapi import APIRouter, HTTPException, status

from app.campaigns.service import mark_notice_read, pending_in_app_notices
from app.core.deps import CurrentAccount, DbSession

router = APIRouter(prefix="/campaign-notices", tags=["campaigns"])


@router.get("")
def notices(account: CurrentAccount, db: DbSession) -> list[dict]:
    return pending_in_app_notices(db, account)


@router.post("/{grant_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def read_notice(grant_id: int, account: CurrentAccount, db: DbSession) -> None:
    if not mark_notice_read(db, account, grant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aviso inexistente.")
    db.commit()
