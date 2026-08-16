from __future__ import annotations

from sqlalchemy.orm import Session

from studio.persistence.models import Project


def create_project(session: Session, *, title: str, genre: str | None = None) -> Project:
    project = Project(title=title, genre=genre)
    session.add(project)
    session.flush()
    return project
