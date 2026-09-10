import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_visitor_session
from app.config import QUANT_DIR
from app.db import get_db
from app.models.quantification import QuantificationDataset
from app.models.session import VisitorSession
from app.models.user import User
from app.schemas.quantification import (
    ComputeQuantificationRequest,
    FeatureTablePage,
    QuantificationDatasetOut,
    RegionIntensityRequest,
    TrackingTree,
    TsneResult,
)
from app.services import access
from app.services import quantification as quant_service
from app.services import quantification_compute

router = APIRouter(prefix="/api/quantification", tags=["quantification"])

ALLOWED_SUFFIXES = {".csv", ".json"}
ALLOWED_KINDS = {"features", "tracking"}


@router.get("", response_model=list[QuantificationDatasetOut])
def list_datasets(
    project_id: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    access.require_project(db, project_id, user, visitor_session)
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
    series_id: int | None = Form(None),
    file: UploadFile = File(...),
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    access.require_project(db, project_id, user, visitor_session)
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
        project_id=project_id, series_id=series_id, name=name, kind=kind, file_path=str(dest)
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


@router.post("/compute", response_model=list[QuantificationDatasetOut])
def compute_quantification(
    body: ComputeQuantificationRequest,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    """Compute geometry, per-channel intensity, and (for movies) cross-frame
    tracking from a series' saved polygons, and register the results as
    quantification datasets -- the same kind a user could otherwise upload
    by hand, so they show up in the feature table / t-SNE / tracking views
    immediately."""
    series = access.require_series(db, body.series_id, user, visitor_session)

    try:
        result = quantification_compute.compute_series_quantification(
            db,
            series,
            pixel_size=body.pixel_size,
            sampling_interval=body.sampling_interval,
            fill_gaps=body.fill_gaps,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Quantification failed: {exc}") from exc

    created: list[QuantificationDataset] = []

    features_df = result["features"]
    if not features_df.empty:
        dest = QUANT_DIR / f"{uuid.uuid4()}.csv"
        features_df.to_csv(dest, index=False)
        dataset = QuantificationDataset(
            project_id=series.project_id,
            series_id=series.id,
            name=f"{series.name} -- features",
            kind="features",
            file_path=str(dest),
        )
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        created.append(dataset)

    tracking_nodes = result["tracking"]
    if tracking_nodes:
        dest = QUANT_DIR / f"{uuid.uuid4()}.json"
        dest.write_text(
            json.dumps({"nodes": tracking_nodes, "frame_track_map": result["frame_track_map"]})
        )
        dataset = QuantificationDataset(
            project_id=series.project_id,
            series_id=series.id,
            name=f"{series.name} -- tracking",
            kind="tracking",
            file_path=str(dest),
        )
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        created.append(dataset)

    if not created:
        raise HTTPException(
            400, "No segmented frames found for this series -- segment it first."
        )
    return created


@router.post("/measure", response_model=list[QuantificationDatasetOut])
def measure(
    body: RegionIntensityRequest,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    """The main quantification table for one series: one fluorescent
    channel's intensity over a specific sub-region of each cell -- whole
    area, or outline/centerline as one column per sampled point along it (an
    intensity profile on one row rather than a single average -- see
    compute_series_measurements) -- for every cell on every frame, with an
    explicit opt-in selection of geometry columns to merge on. By default
    each row is one frame's own instance of a cell, not linked across
    frames; set track=True to link "cell" across frames via CellMate's
    tracker + CellNetwork instead (see compute_series_measurements).
    Registered as a downloadable/viewable "features" dataset."""
    series = access.require_series(db, body.series_id, user, visitor_session)
    if body.region not in quantification_compute.REGIONS:
        raise HTTPException(400, f"region must be one of {quantification_compute.REGIONS}")
    unknown_features = set(body.geometry_features) - set(quantification_compute.SELECTABLE_GEOMETRY_FEATURES)
    if unknown_features:
        raise HTTPException(
            400,
            f"Unknown geometry_features {sorted(unknown_features)} -- choices: "
            f"{quantification_compute.SELECTABLE_GEOMETRY_FEATURES}",
        )

    channel_names = dict(quantification_compute._series_non_dic_channels(series))
    if body.channel_index not in channel_names:
        raise HTTPException(
            400,
            f"channel_index {body.channel_index} is not a valid fluorescent channel for this "
            f"series -- choices: {sorted(channel_names)}",
        )

    try:
        df = quantification_compute.compute_series_measurements(
            db,
            series,
            channel_index=body.channel_index,
            region=body.region,
            pixel_size=body.pixel_size,
            sampling_interval=body.sampling_interval,
            geometry_features=body.geometry_features,
            radius=body.radius,
            track=body.track,
            align=body.align,
            iou_threshold=body.iou_threshold,
            max_miss=body.max_miss,
            neighbor_threshold=body.neighbor_threshold,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Measurement failed: {exc}") from exc

    if df.empty:
        raise HTTPException(400, "No segmented frames found for this series -- segment it first.")

    dest = QUANT_DIR / f"{uuid.uuid4()}.csv"
    df.to_csv(dest, index=False)
    channel_name = channel_names[body.channel_index]
    dataset = QuantificationDataset(
        project_id=series.project_id,
        series_id=series.id,
        name=f"{series.name} -- {channel_name} {body.region}",
        kind="features",
        file_path=str(dest),
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return [dataset]


def _get_dataset(
    dataset_id: int, user: User | None, visitor_session: VisitorSession, db: Session
) -> QuantificationDataset:
    return access.require_dataset(db, dataset_id, user, visitor_session)


@router.get("/{dataset_id}/download")
def download_dataset(
    dataset_id: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    dataset = _get_dataset(dataset_id, user, visitor_session, db)
    path = Path(dataset.file_path)
    if not path.exists():
        raise HTTPException(404, "Dataset file missing on disk")
    safe_name = "".join(c if c.isalnum() or c in " ._-" else "_" for c in dataset.name)
    return FileResponse(
        path,
        filename=f"{safe_name}{path.suffix}",
        media_type="text/csv" if path.suffix == ".csv" else "application/json",
    )


@router.get("/{dataset_id}/features", response_model=FeatureTablePage)
def get_features(
    dataset_id: int,
    offset: int = 0,
    limit: int = 200,
    sort_by: str | None = None,
    ascending: bool = True,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    dataset = _get_dataset(dataset_id, user, visitor_session, db)
    try:
        columns, rows, total = quant_service.get_feature_page(
            dataset.file_path, offset, limit, sort_by, ascending
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return FeatureTablePage(columns=columns, rows=rows, total=total)


@router.get("/{dataset_id}/tracking", response_model=TrackingTree)
def get_tracking(
    dataset_id: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    dataset = _get_dataset(dataset_id, user, visitor_session, db)
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
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    dataset = _get_dataset(dataset_id, user, visitor_session, db)
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
