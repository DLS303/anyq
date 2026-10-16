from fastapi import APIRouter

from app.schemas import ModuleInfo

router = APIRouter(prefix="/v1/modules", tags=["architecture"])

MODULES = [
    ModuleInfo(
        id="marketplace",
        title="Marketplace Service",
        phase=1,
        status="live",
        notes="Материалы и услуги. Рынок земли отключён.",
    ),
    ModuleInfo(
        id="gis-cadastre",
        title="GIS & Cadastre Service",
        phase=1,
        status="stub",
        notes="Отключён: земля и кадастр не в этом контуре.",
    ),
    ModuleInfo(
        id="crm-pm",
        title="CRM & PM Service",
        phase=2,
        status="live",
        notes="Канбан + площадка Procore-style: RFI, punch, инспекции, ТБ.",
    ),
    ModuleInfo(
        id="estimate-docs",
        title="Estimate & Docs Service",
        phase=3,
        status="live",
        notes="KENML позже. Сейчас: бюджет, CO, журнал, график.",
    ),
    ModuleInfo(
        id="fintech-escrow",
        title="FinTech & Escrow Service",
        phase=3,
        status="stub",
        notes="Номинальный счёт, Kaspi Pay, факторинг.",
    ),
    ModuleInfo(
        id="gov-gateway",
        title="Gov-Integration Gateway",
        phase=4,
        status="stub",
        notes="Smart Bridge: ЕГКН, e-Qurylys, E-License, eGov Sign.",
    ),
    ModuleInfo(
        id="chat-events",
        title="Chat & Event Service",
        phase=2,
        status="live",
        notes="P2P-мессенджер. Kafka — позже.",
    ),
]


@router.get("")
def list_modules():
    return {"ok": True, "data": MODULES}
