import type { PolygonAnnotation, SeriesTrackingMap } from '../../api/types';

/** The stable track id CellMate's tracker assigned this polygon on this
 * frame (see RightPanel's Run Tracking), or undefined if tracking hasn't
 * been computed for this series/frame yet. Shared by PolygonList (the
 * "track N" chip) and ImageCanvas (the on-image label toggle) so both stay
 * in sync with the same lookup. */
export function trackIdFor(
  tracking: SeriesTrackingMap | null,
  frameIndex: number,
  polygon: PolygonAnnotation,
): number | undefined {
  return tracking?.frame_track_map[String(frameIndex)]?.[String(Number(polygon.label))];
}
