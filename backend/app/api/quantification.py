import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import QUANT_DIR
from app.db import get_db
from app.models.quantification import QuantificationDataset
from app.schemas.quantification import (
    FeatureTablePage,
    QuantificationDatasetOut,
    TrackingTree,
    TsneResult,
)
from app.services import quantification as quant_service

router = APIRouter(prefix="/api/quantification", tags=["quantification"])

ALLOWED_SUFFIXES = {".csv", ".json"}
ALLOWED_KINDS = {"features", "tracking"}


@router.get("", response_model=list[QuantificationDatasetOut])
def list_datasets(project_id: int, db: Session = Depends(get_db)):
    return (
        db.query(QuantificationDataset)
        .filter(QuantificationDataset.project_id == project_id)
        .order_by(QuantificationDataset.uploaded_at.desc())
        .all()
    )


@router.post("/upload", response_model=QuantificationDatasetOut)
async def upload_dataset(
    project_id: int = Form(...),
    name: str = Form(...),
    kind: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if kind not in ALLOWED_KINDS:
        raise HTTPException(400, f"kind must be one of {ALLOWED_KINDS}")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, f"file must be one of {ALLOWED_SUFFIXES}")

    dest = QUANT_DIR / f"{uuid.uuid4()}{suffix}"
    with dest.open("wb") as out:
        out.write(await file.read())

    try:
        quant_service.load_dataframe(str(dest))
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not parse file: {exc}") from exc

    dataset = QuantificationDataset(
        project_id=project_id, name=name, kind=kind, file_path=str(dest)
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


def _get_dataset(dataset_id: int, db: Session) -> QuantificationDataset:
    dataset = db.get(QuantificationDataset, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    return dataset


@router.get("/{dataset_id}/features", response_model=FeatureTablePage)
def get_features(
    dataset_id: int,
    offset: int = 0,
    limit: int = 200,
    sort_by: str | None = None,
    ascending: bool = True,
    db: Session = Depends(get_db),
):
    dataset = _get_dataset(dataset_id, db)
    try:
        columns, rows, total = quant_service.get_feature_page(
            dataset.file_path, offset, limit, sort_by, ascending
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return FeatureTablePage(columns=columns, rows=rows, total=total)


@router.get("/{dataset_id}/tracking", response_model=TrackingTree)
def get_tracking(dataset_id: int, db: Session = Depends(get_db)):
    dataset = _get_dataset(dataset_id, db)
    try:
        nodes = quant_service.build_tracking_tree(dataset.file_path)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return TrackingTree(nodes=nodes)


@router.get("/{dataset_id}/tsne", response_model=TsneResult)
def get_tsne(
    dataset_id: int,
    perplexity: float = 30.0,
    id_column: str | None = None,
    color_by: str | None = None,
    db: Session = Depends(get_db),
):
    dataset = _get_dataset(dataset_id, db)
    try:
        ids, xs, ys = quant_service.compute_tsne(
            dataset.file_path, perplexity, id_column
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc

    color_values = None
    if color_by:
        df = quant_service.load_dataframe(dataset.file_path)
        if color_by in df.columns:
            color_values = df[color_by].tolist()

    return TsneResult(
        ids=ids, x=xs, y=ys, color_by=color_by, color_values=color_values
    )
