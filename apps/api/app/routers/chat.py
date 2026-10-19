from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_user
from app.schemas import MessageCreate, ThreadCreate, User
from app.store import store

router = APIRouter(prefix="/v1/chat", tags=["chat"])


@router.get("/threads")
def threads(user: User = Depends(require_user)):
    items = store.list_threads(user)
    items.sort(key=lambda t: t.updated_at, reverse=True)
    return {"ok": True, "data": items}


@router.get("/peers")
def peers(user: User = Depends(require_user)):
    return {"ok": True, "data": store.chat_peers(user)}


@router.post("/threads")
def open_thread(body: ThreadCreate, user: User = Depends(require_user)):
    try:
        thread = store.open_thread(user, body)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "data": thread}


@router.get("/threads/{tid}/messages")
def messages(tid: str, user: User = Depends(require_user)):
    thread = store.get_thread(tid)
    if not thread or user.id not in (thread.user_a, thread.user_b):
        raise HTTPException(status_code=404, detail="Чат не найден")
    return {"ok": True, "data": store.thread_messages(tid), "thread": thread}


@router.post("/threads/{tid}/messages")
def send(tid: str, body: MessageCreate, user: User = Depends(require_user)):
    try:
        msg = store.add_message(user, tid, body)
    except (ValueError, PermissionError) as exc:
        code = 403 if isinstance(exc, PermissionError) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    return {"ok": True, "data": msg}
