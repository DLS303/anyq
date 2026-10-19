"""Feature gate that reads ids only from the request path.

A pid or rid argument on a dependency is also filled from the query string.
That would let ?pid= point at another company's project. Path params only.
Company and membership come from one JOIN. No row is 404.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import text

from app.company_features import FEATURE_KEYS, ensure_feature, project_company_id
from app.deps import require_user
from app.schemas import User
from app.store import store

_PROJECT_ACCESS = text(
    """
    SELECT proj.doc_id AS project_id
    FROM records AS proj
    LEFT JOIN records AS mem
      ON mem.collection = 'directory'
     AND mem.project_id = proj.doc_id
     AND mem.user_id = :user_id
    WHERE proj.collection = 'projects'
      AND proj.doc_id = :pid
      AND (proj.owner_id = :user_id OR mem.user_id IS NOT NULL)
    LIMIT 1
    """
)

_ENTITY_ACCESS = text(
    """
    SELECT r.id AS entity_id, r.project_id AS project_id, r.company_id AS company_id
    FROM rfis AS r
    JOIN records AS proj
      ON proj.collection = 'projects'
     AND proj.doc_id = r.project_id
    LEFT JOIN records AS mem
      ON mem.collection = 'directory'
     AND mem.project_id = r.project_id
     AND mem.user_id = :user_id
    WHERE r.id = :rid
      AND r.deleted_at IS NULL
      AND (:pid = '' OR r.project_id = :pid)
      AND (proj.owner_id = :user_id OR mem.user_id IS NOT NULL)
    LIMIT 1
    """
)


def require_feature(key: str):
    """Hide a route when the company flag is off. A missing flag or member is 404."""

    if key not in FEATURE_KEYS:
        raise RuntimeError(f"unknown feature {key}")

    def dependency(request: Request, user: User = Depends(require_user)) -> User:
        path = request.path_params
        rid = str(path["rid"]) if "rid" in path else ""
        pid = str(path["pid"]) if "pid" in path else ""
        if not rid and not pid:
            raise HTTPException(status_code=404, detail="Не найдено")
        with store._sql.factory() as session:
            if rid:
                found = session.execute(
                    _ENTITY_ACCESS, {"user_id": user.id, "rid": rid, "pid": pid}
                ).mappings().first()
            else:
                found = session.execute(
                    _PROJECT_ACCESS, {"user_id": user.id, "pid": pid}
                ).mappings().first()
        if found is None:
            raise HTTPException(status_code=404, detail="Не найдено")
        project_id = str(found["project_id"])
        if rid:
            company_id = str(found["company_id"] or "")
        else:
            project = store.get_project(project_id)
            company_id = project_company_id(project) if project is not None else ""
        if not company_id:
            raise HTTPException(status_code=404, detail="Не найдено")
        ensure_feature(company_id, key)
        request.state.rfi_access = {
            "project_id": project_id,
            "company_id": company_id,
            "entity_id": str(found["entity_id"]) if rid else None,
        }
        return user

    return dependency
