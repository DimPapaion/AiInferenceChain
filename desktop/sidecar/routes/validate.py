from fastapi import APIRouter
from pydantic import BaseModel
from training.arch_sandbox import validate_architecture
from training.dataset_loader import validate_dataset_url

router = APIRouter()


class ArchRequest(BaseModel):
    source: str
    num_classes: int = 10


class DatasetRequest(BaseModel):
    url: str
    num_classes: int | None = None


@router.post("/architecture")
def validate_arch(req: ArchRequest):
    return validate_architecture(req.source, req.num_classes)


@router.post("/dataset")
def validate_dataset(req: DatasetRequest):
    return validate_dataset_url(req.url, req.num_classes)
