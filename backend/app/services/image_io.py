"""Reading microscopy image series (folders of frames or multi-page TIFFs)
and rendering individual frames as contrast-adjusted 8-bit PNGs for the
browser."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

from app.config import SUPPORTED_IMAGE_EXTENSIONS

# Names (case-insensitive substrings) recognized as a transmitted-light
# channel suitable for segmentation, checked in priority order.
_DIC_NAME_HINTS = ("dic",)
_TRANSMITTED_LIGHT_HINTS = ("bf", "brightfield", "bright field", "phase", "trans")

# Common fluorophore/channel name keywords -> the LUT hue ImageJ conventionally
# assigns them, used to sanity-check (and if needed, re-order) declared channel
# names against actual per-channel LUT colors -- see _reconcile_channel_names.
_HUE_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "gray": ("dic", "bf", "brightfield", "bright field", "phase", "trans"),
    "blue": ("dapi", "hoechst"),
    "green": ("gfp", "fitc", "alexa488", "egfp"),
    "red": ("rfp", "mcherry", "mscarlet", "dsred", "texas red", "cy3"),
}


@dataclass
class SeriesMetadata:
    frame_count: int
    width: int
    height: int
    dtype: str
    channels: int  # per-pixel channels (e.g. RGB=3), NOT imaging channels
    channel_count: int = 1  # number of imaging channels (T/C-axis), e.g. DIC+GFP+...
    channel_names: list[str] | None = None
    dic_channel_index: int | None = None  # best-guess transmitted-light channel


def sorted_frame_files(folder: Path) -> list[Path]:
    files = [
        p
        for p in folder.iterdir()
        if p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]
    return sorted(files, key=lambda p: p.name)


def _nonspatial_axes_shape(series: "tifffile.TiffPageSeries") -> tuple[str, tuple[int, ...]]:
    """The series' axes/shape with the trailing Y,X (spatial) axes stripped,
    e.g. axes='TCYX' -> ('TC', (n_t, n_c)). Empty if the series has no extra
    axes beyond a single 2D page."""
    axes = series.axes
    shape = series.shape
    if len(axes) >= 2 and axes[-2:] == "YX":
        return axes[:-2], shape[:-2]
    return "", ()


def _extract_channel_names(tf: tifffile.TiffFile, channel_count: int) -> list[str] | None:
    """Best-effort extraction of per-channel names from ImageJ hyperstack
    'Info' metadata (as embedded by Nikon .nd2 -> ImageJ conversions, e.g.
    'Name #1 = DAPI'). Returns None if nothing usable is found."""
    md = tf.imagej_metadata or {}
    info = md.get("Info")
    if not isinstance(info, str):
        return None

    names: dict[int, str] = {}
    for m in re.finditer(r"Name #(\d+)\s*=\s*([^\r\n]*)", info):
        idx = int(m.group(1))
        if idx not in names:
            names[idx] = m.group(2).strip()

    if not names:
        return None

    return [names.get(i + 1, f"channel {i + 1}") for i in range(channel_count)]


def _grayscale_lut_channel(tf: tifffile.TiffFile, channel_count: int) -> int | None:
    """ImageJ conventionally assigns transmitted-light channels (DIC,
    brightfield, phase) the plain "Grays" LUT and fluorescence channels a
    colored one. This is a much more reliable signal than channel *names*,
    whose declared order in the 'Info' text block isn't guaranteed to match
    the actual channel/page storage order (observed in practice on real
    Nikon .nd2 -> ImageJ exports). Returns the index of the single grayscale
    channel, or None if there's zero or more than one (ambiguous)."""
    md = tf.imagej_metadata or {}
    luts = md.get("LUTs")
    if not luts or len(luts) < channel_count:
        return None

    grayscale = [
        i
        for i in range(channel_count)
        if np.array_equal(luts[i][0], luts[i][1]) and np.array_equal(luts[i][1], luts[i][2])
    ]
    return grayscale[0] if len(grayscale) == 1 else None


def _lut_color_bucket(tf: tifffile.TiffFile, index: int) -> str | None:
    """Classify a channel's LUT as 'gray', 'red', 'green', 'blue', or None
    (ambiguous/mixed hue, e.g. cyan/magenta) by its color at full intensity."""
    md = tf.imagej_metadata or {}
    luts = md.get("LUTs")
    if not luts or index >= len(luts):
        return None
    r, g, b = int(luts[index][0][-1]), int(luts[index][1][-1]), int(luts[index][2][-1])
    if r == g == b:
        return "gray"
    vals = {"red": r, "green": g, "blue": b}
    dominant = max(vals, key=vals.get)
    rest = sorted(vals.values())[:-1]
    if vals[dominant] >= 200 and vals[dominant] - max(rest) >= 100:
        return dominant
    return None


def _reconcile_channel_names(
    tf: tifffile.TiffFile, channel_names: list[str] | None, channel_count: int
) -> list[str] | None:
    """The order channel names are declared in ImageJ 'Info' metadata isn't
    guaranteed to match the actual channel/page storage order (seen in
    practice on real files). Re-derive each declared name's true index from
    its expected LUT hue (DAPI->blue, GFP->green, ... DIC->gray) when that
    match is unambiguous; otherwise leave the names in their declared order
    (best effort, not authoritative -- the UI lets the user override)."""
    if not channel_names or len(channel_names) != channel_count:
        return channel_names

    buckets = [_lut_color_bucket(tf, i) for i in range(channel_count)]
    if any(b is None for b in buckets) or len(set(buckets)) != channel_count:
        return channel_names  # not a clean one-hue-per-channel signal

    expected_bucket_by_name: dict[str, str] = {}
    for name in channel_names:
        lower = name.lower()
        for bucket, hints in _HUE_NAME_HINTS.items():
            if any(h in lower for h in hints):
                expected_bucket_by_name[name] = bucket
                break

    if len(expected_bucket_by_name) != channel_count:
        return channel_names  # not every name recognized -- don't guess

    expected_buckets = set(expected_bucket_by_name.values())
    if expected_buckets != set(buckets) or len(expected_buckets) != channel_count:
        return channel_names  # buckets don't form a clean bijection

    bucket_to_index = {bucket: i for i, bucket in enumerate(buckets)}
    reordered = [""] * channel_count
    for name, bucket in expected_bucket_by_name.items():
        reordered[bucket_to_index[bucket]] = name
    return reordered


def _name_hint_channel(channel_names: list[str] | None) -> int | None:
    if not channel_names:
        return None
    for hints in (_DIC_NAME_HINTS, _TRANSMITTED_LIGHT_HINTS):
        for i, name in enumerate(channel_names):
            lower = name.lower()
            if any(h in lower for h in hints):
                return i
    return None


def probe_series(source_type: str, path: str) -> SeriesMetadata:
    p = Path(path)
    if source_type == "multipage_tiff":
        with tifffile.TiffFile(p) as tf:
            series0 = tf.series[0]
            dtype = str(series0.dtype)
            nonspatial_axes, nonspatial_shape = _nonspatial_axes_shape(series0)

            if nonspatial_axes:
                h, w = series0.shape[-2], series0.shape[-1]
            else:
                page = tf.pages[0]
                arr = page.asarray()
                h, w = arr.shape[:2]

            frame_count = 1
            channel_count = 1
            for ax, size in zip(nonspatial_axes, nonspatial_shape):
                if ax == "C":
                    channel_count = size
                else:
                    # T, Z, S, ... all fold into the "frame" index space
                    frame_count *= size
            if not nonspatial_axes:
                frame_count = len(tf.pages)

            channel_names = _extract_channel_names(tf, channel_count) if channel_count > 1 else None
            if channel_names:
                channel_names = _reconcile_channel_names(tf, channel_names, channel_count)
            dic_channel_index = _grayscale_lut_channel(tf, channel_count)
            if dic_channel_index is None:
                dic_channel_index = _name_hint_channel(channel_names)

            # per-pixel channels (RGB etc.) of a single plane -- distinct from
            # the imaging channel_count above
            first_page = tf.pages[0].asarray()
            px_channels = 1 if first_page.ndim == 2 else first_page.shape[2]

        return SeriesMetadata(
            frame_count=frame_count,
            width=w,
            height=h,
            dtype=dtype,
            channels=px_channels,
            channel_count=channel_count,
            channel_names=channel_names,
            dic_channel_index=dic_channel_index,
        )

    if source_type in ("folder", "upload"):
        files = sorted_frame_files(p)
        if not files:
            raise ValueError(f"No supported image files found in {p}")
        first = _read_single_frame_file(files[0])
        h, w = first.shape[:2]
        channels = 1 if first.ndim == 2 else first.shape[2]
        return SeriesMetadata(len(files), w, h, str(first.dtype), channels)

    raise ValueError(f"Unknown source_type: {source_type}")


def frame_shape(source_type: str, path: str, frame_index: int) -> tuple[int, int]:
    """(height, width) of one specific frame -- read from that frame's own
    header, NOT the series-level SeriesMetadata.width/height (which, for a
    folder/upload of separately-sized images, only reflects the *first*
    file). Callers that rasterize polygons back into a mask must size the
    canvas from this, not the series-level fields, or masks for any frame
    other than the first come out clipped/misaligned when frames differ in
    size."""
    p = Path(path)
    if source_type == "multipage_tiff":
        with tifffile.TiffFile(p) as tf:
            series0 = tf.series[0]
            nonspatial_axes, nonspatial_shape = _nonspatial_axes_shape(series0)
            if nonspatial_axes:
                page_index = _tiff_page_index(nonspatial_axes, nonspatial_shape, frame_index, None)
            else:
                page_index = frame_index
                if page_index < 0 or page_index >= len(tf.pages):
                    raise IndexError(f"frame_index {frame_index} out of range")
            page = tf.pages[page_index]
            return page.shape[0], page.shape[1]

    if source_type in ("folder", "upload"):
        files = sorted_frame_files(p)
        if frame_index < 0 or frame_index >= len(files):
            raise IndexError(f"frame_index {frame_index} out of range")
        f = files[frame_index]
        if f.suffix.lower() in (".tif", ".tiff"):
            with tifffile.TiffFile(f) as tf:
                page = tf.pages[0]
                return page.shape[0], page.shape[1]
        with Image.open(f) as img:
            w, h = img.size
            return h, w

    raise ValueError(f"Unknown source_type: {source_type}")


def _read_single_frame_file(path: Path) -> np.ndarray:
    if path.suffix.lower() in (".tif", ".tiff"):
        return tifffile.imread(path)
    return np.array(Image.open(path))


def _tiff_page_index(
    nonspatial_axes: str,
    nonspatial_shape: tuple[int, ...],
    frame_index: int,
    channel_index: int | None,
) -> int:
    """Map a (frame_index, channel_index) pair back to the flat page index
    within the TIFF, given the series' non-spatial axes (e.g. 'TC').
    frame_index addresses every non-C axis folded together, row-major, in
    the order they appear in `axes` -- channel_index (if the series has a
    'C' axis) addresses that axis directly."""
    fold_axes = [(ax, size) for ax, size in zip(nonspatial_axes, nonspatial_shape) if ax != "C"]
    sizes = [size for _, size in fold_axes]
    total = 1
    for s in sizes:
        total *= s
    if frame_index < 0 or frame_index >= max(total, 1):
        raise IndexError(f"frame_index {frame_index} out of range")

    rem = frame_index
    per_axis_index = [0] * len(fold_axes)
    for i in range(len(fold_axes) - 1, -1, -1):
        per_axis_index[i] = rem % sizes[i] if sizes[i] else 0
        rem //= sizes[i] if sizes[i] else 1

    idx_map = {ax: val for (ax, _), val in zip(fold_axes, per_axis_index)}

    if "C" in nonspatial_axes:
        c_size = nonspatial_shape[nonspatial_axes.index("C")]
        c = channel_index if channel_index is not None else 0
        if c < 0 or c >= c_size:
            raise IndexError(f"channel_index {c} out of range")
        idx_map["C"] = c

    flat = 0
    for ax, size in zip(nonspatial_axes, nonspatial_shape):
        flat = flat * size + idx_map.get(ax, 0)
    return flat


def read_frame(
    source_type: str,
    path: str,
    frame_index: int,
    channel_index: int | None = None,
) -> np.ndarray:
    p = Path(path)
    if source_type == "multipage_tiff":
        with tifffile.TiffFile(p) as tf:
            series0 = tf.series[0]
            nonspatial_axes, nonspatial_shape = _nonspatial_axes_shape(series0)

            if nonspatial_axes:
                page_index = _tiff_page_index(
                    nonspatial_axes, nonspatial_shape, frame_index, channel_index
                )
            else:
                page_index = frame_index
                if page_index < 0 or page_index >= len(tf.pages):
                    raise IndexError(f"frame_index {frame_index} out of range")

            return tf.pages[page_index].asarray()

    if source_type in ("folder", "upload"):
        files = sorted_frame_files(p)
        if frame_index < 0 or frame_index >= len(files):
            raise IndexError(f"frame_index {frame_index} out of range")
        return _read_single_frame_file(files[frame_index])

    raise ValueError(f"Unknown source_type: {source_type}")


def auto_contrast_range(arr: np.ndarray) -> tuple[float, float]:
    """1st/99th percentile window, a reasonable default for microscopy data."""
    lo, hi = np.percentile(arr, (1, 99))
    if hi <= lo:
        lo, hi = float(arr.min()), float(arr.max() or 1)
    return float(lo), float(hi)


def _contrast_stretch_uint8(
    arr: np.ndarray, vmin: float | None = None, vmax: float | None = None
) -> np.ndarray:
    """Contrast-stretch an 8/16-bit (or float) single-channel array into 8-bit."""
    work = arr.astype(np.float32)
    if vmin is None or vmax is None:
        auto_lo, auto_hi = auto_contrast_range(work)
        vmin = auto_lo if vmin is None else vmin
        vmax = auto_hi if vmax is None else vmax
    if vmax <= vmin:
        vmax = vmin + 1

    stretched = np.clip((work - vmin) / (vmax - vmin), 0, 1)
    return (stretched * 255).astype(np.uint8)


def render_frame_png(
    arr: np.ndarray, vmin: float | None = None, vmax: float | None = None
) -> bytes:
    """Contrast-stretch an 8/16-bit (or float) array into an 8-bit PNG --
    for the browser to *display*, where the 1st/99th percentile auto-
    contrast in `_contrast_stretch_uint8` is a reasonable default. Model
    inference wants the raw data instead -- see `raw_frame_tiff_bytes`."""
    if arr.ndim == 3 and arr.shape[2] > 3:
        arr = arr[:, :, 0]  # unsupported multi-channel: show first channel

    img8 = _contrast_stretch_uint8(arr, vmin, vmax)

    image = Image.fromarray(img8)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def raw_frame_tiff_bytes(arr: np.ndarray) -> bytes:
    """The frame as-is, losslessly, at its native dtype (8-bit, 16-bit,
    whatever) and shape -- no contrast stretch, no clipping, no percentile
    windowing. For sending to a model service (sam_service/panoptic_service),
    which does its own min/max normalization on the actual data rather than
    the percentile-clipped version `render_frame_png` makes for on-screen
    display -- the two have different jobs and shouldn't share a
    contrast-altering step."""
    buf = io.BytesIO()
    tifffile.imwrite(buf, arr)
    return buf.getvalue()


def to_uint8_rgb(arr: np.ndarray) -> np.ndarray:
    """Contrast-stretch any microscopy frame (8/16-bit, 1+ channels) into an
    8-bit RGB array -- the input format SAM's image encoder expects."""
    if arr.ndim == 3 and arr.shape[2] > 3:
        arr = arr[:, :, 0]

    img8 = _contrast_stretch_uint8(arr)
    if img8.ndim == 2:
        return np.stack([img8] * 3, axis=-1)
    if img8.shape[2] == 1:
        return np.repeat(img8, 3, axis=2)
    return img8
