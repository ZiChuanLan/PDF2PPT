"""Text erase bbox merging for background cleanup."""

from ..bbox_utils import _coerce_bbox_pt


def _merge_text_erase_bboxes(
    boxes: list[list[float]],
    *,
    gap_pt: float,
    fast_path_threshold: int = 240,
) -> list[list[float]]:
    """Merge nearby same-line erase boxes.

    Small/medium pages still use the existing iterative merge for maximal
    compatibility. When AI OCR returns hundreds of fragmented boxes (for
    example some DeepSeek-OCR grounding outputs), the quadratic repeated-merge
    loop can dominate the whole PPT stage. For those pages switch to a sweep
    + union-find fast path that preserves transitive same-line connectivity.
    """

    merged = [
        list(_coerce_bbox_pt(bb))
        for bb in boxes
        if isinstance(bb, list) and len(bb) == 4
    ]
    if len(merged) <= 1:
        return merged

    gap_pt = max(0.0, float(gap_pt))

    if len(merged) > int(fast_path_threshold):
        indexed = [
            (idx, bb)
            for idx, bb in enumerate(
                sorted(
                    merged,
                    key=lambda b: (float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                )
            )
        ]
        parent = list(range(len(indexed)))

        def _find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def _union(a: int, b: int) -> None:
            root_a = _find(a)
            root_b = _find(b)
            if root_a != root_b:
                parent[root_b] = root_a

        active: list[int] = []
        for current_idx, (_, current) in enumerate(indexed):
            x0, y0, x1, y1 = current
            next_active: list[int] = []
            for prev_idx in active:
                _, prev = indexed[prev_idx]
                px0, py0, px1, py1 = prev
                if float(px1) < (float(x0) - gap_pt):
                    continue
                next_active.append(prev_idx)

                y_overlap = min(float(y1), float(py1)) - max(float(y0), float(py0))
                min_h = max(1.0, min(float(y1) - float(y0), float(py1) - float(py0)))
                if y_overlap < (0.40 * min_h):
                    continue
                x_gap = max(0.0, float(x0) - float(px1))
                if x_gap <= gap_pt:
                    _union(current_idx, prev_idx)

            next_active.append(current_idx)
            active = next_active

        grouped: dict[int, list[list[float]]] = {}
        for idx, (_, bb) in enumerate(indexed):
            grouped.setdefault(_find(idx), []).append(bb)

        out: list[list[float]] = []
        for component in grouped.values():
            xs0 = [float(bb[0]) for bb in component]
            ys0 = [float(bb[1]) for bb in component]
            xs1 = [float(bb[2]) for bb in component]
            ys1 = [float(bb[3]) for bb in component]
            out.append([min(xs0), min(ys0), max(xs1), max(ys1)])
        out.sort(key=lambda b: (float(b[1]), float(b[0])))
        return out

    changed = True
    while changed:
        changed = False
        merged.sort(key=lambda b: (b[1], b[0]))
        out: list[list[float]] = []
        for bb in merged:
            x0, y0, x1, y1 = _coerce_bbox_pt(bb)
            did_merge = False
            for i, ub in enumerate(out):
                ux0, uy0, ux1, uy1 = _coerce_bbox_pt(ub)
                y_overlap = min(y1, uy1) - max(y0, uy0)
                min_h = max(1.0, min(y1 - y0, uy1 - uy0))
                if y_overlap < (0.40 * min_h):
                    continue
                if x0 > ux1:
                    x_gap = float(x0 - ux1)
                elif ux0 > x1:
                    x_gap = float(ux0 - x1)
                else:
                    x_gap = 0.0
                if x_gap > gap_pt:
                    continue
                out[i] = [
                    min(x0, ux0),
                    min(y0, uy0),
                    max(x1, ux1),
                    max(y1, uy1),
                ]
                did_merge = True
                changed = True
                break
            if not did_merge:
                out.append([x0, y0, x1, y1])
        merged = out

    return merged
