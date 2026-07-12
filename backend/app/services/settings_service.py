from sqlalchemy.orm import Session

from app.models import AppSettings


def get_or_create_settings(db: Session) -> AppSettings:
    row = db.query(AppSettings).first()
    if row:
        return row
    row = AppSettings(registration_enabled=True, invite_required=False, invite_code=None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
