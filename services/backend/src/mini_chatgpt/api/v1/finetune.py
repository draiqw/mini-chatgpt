"""POST /finetune -> 202 и job_id; GET /jobs/{job_id} -> статус задачи."""

from fastapi import APIRouter

from mini_chatgpt.api.deps import Rid
from mini_chatgpt.schemas.finetune import FinetuneRequest, JobCreated, JobStatus
from mini_chatgpt.services import finetune_service

router = APIRouter(tags=["finetune"])


@router.post("/finetune", status_code=202)
async def finetune(
    body: FinetuneRequest,
    rid: Rid,
) -> JobCreated:
    """Поставить дообучение в очередь. 202 -- «принято», выполняется в фоне."""
    return JobCreated(
        job_id=await finetune_service.enqueue(
            rid=rid,
            dataset=body.dataset,
            epochs=body.epochs,
        )
    )


@router.get("/jobs/{job_id}", response_model_exclude_none=True)
def job_status(
    job_id: str,
    rid: Rid,
) -> JobStatus:
    """Статус задачи. Браузер спрашивает раз в секунду (polling)."""
    return JobStatus(
        **finetune_service.status(
            rid=rid,
            job_id=job_id,
        )
    )
