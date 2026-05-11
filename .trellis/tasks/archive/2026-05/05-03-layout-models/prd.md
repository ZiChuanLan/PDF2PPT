# Layout Model Management

## Goal

Support multiple layout analysis models (PP-DocLayout series + DocLayout-YOLO) with a unified abstraction layer. Users can select and download models during setup wizard, and manage them from settings. Non-downloaded models appear grayed out with download prompts.

## Requirements

1. **Unified layout model abstraction**: Define `LayoutModelProvider` interface that both PP-DocLayout and DocLayout-YOLO implement. Backend uses this interface for inference, frontend doesn't care about the underlying implementation.

2. **Model registry**: A config-driven registry of available layout models with metadata (name, description, size, provider type, model ID).

3. **Setup wizard model selection**: Add a step during /setup where users can see available models and optionally download them. Can skip — just means local layout detection won't be available until a model is downloaded later.

4. **Settings page model selector**: Dropdown showing all available models. Downloaded models are normal/selectable. Non-downloaded models are grayed out, clicking prompts "download now?".

5. **Model download API**: `POST /api/v1/models/download` already exists for pp_doclayout and paddleocr. Extend to support layout model variants (S/M/L/V3) and DocLayout-YOLO.

6. **Model status detection**: Extend `GET /api/v1/models/status` to report each layout model's download status individually (not just "pp_doclayout ready/not ready").

## Available Models

### PP-DocLayout (PaddleX) — already integrated
| Model | Size | Speed | mAP | Best for |
|-------|------|-------|-----|----------|
| PP-DocLayout-S | 1.2MB | 8ms GPU / 14ms CPU | 70.9% | CPU/edge, fast draft |
| PP-DocLayout-M | 23MB | 13ms GPU / 43ms CPU | 75.2% | Balanced |
| PP-DocLayout-L | 124MB | 34ms GPU / 503ms CPU | 90.4% | High precision |
| PP-DocLayoutV3 | 126MB | 24ms GPU | - | 25 categories + reading order (current default) |

### DocLayout-YOLO (OpenDataLab) — new
| Model | Size | Speed | AP50 | Best for |
|-------|------|-------|------|----------|
| DocLayout-YOLO (DocStructBench) | ~10MB | very fast (YOLO) | 93.4% (DocLayNet) | General documents |

## Acceptance Criteria

- [ ] `LayoutModelProvider` interface defined, PP-DocLayout and DocLayout-YOLO both implement it
- [ ] Model registry in config with all 5 models listed
- [ ] Setup wizard shows model list with sizes, download buttons, and skip option
- [ ] Settings page shows model selector: downloaded=selectable, not downloaded=grayed+prompt
- [ ] `GET /api/v1/models/status` returns per-model download status for layout models
- [ ] `POST /api/v1/models/download` supports all layout model variants
- [ ] Job submission uses selected model for layout analysis
- [ ] Backward compatible: existing PP-DocLayoutV3 usage unchanged

## Definition of Done

- All acceptance criteria met
- TypeScript build passes
- Python syntax check passes
- Docker containers rebuilt and running
- Setup wizard flow tested end-to-end

## Technical Approach

**Backend:**
- New module `api/app/convert/ocr/layout_models.py` — model registry + `LayoutModelProvider` protocol
- PP-DocLayout provider: wraps `paddlex.create_model("PP-DocLayoutXxx")`
- DocLayout-YOLO provider: wraps `doclayout_yolo` pip package inference
- Extend `model_status.py` to check per-model download status
- Extend download endpoint to support all models

**Frontend:**
- `web/src/lib/layout-models.ts` — model registry (shared with backend conceptually)
- Settings page: layout model selector with status indicators
- Setup wizard: model selection step (between model detection and completion)

## Out of Scope

- Model fine-tuning
- Custom model upload
- Remote layout model API (only local inference)
- Auto-download on first use (user must explicitly download)

## Technical Notes

- PaddleX models downloaded via `paddlex.create_model()` — auto-downloads weights
- DocLayout-YOLO installed via `pip install doclayout-yolo`, model weights from HuggingFace
- Current code: `_resolve_paddlex_layout_model_name()` hardcodes "PP-DocLayoutV3"
- Current code: `AiOcrClient.__init__` takes `layout_model` param, used in `_get_local_layout_model()`
- Dockerfile needs `doclayout-yolo` package added if supporting DocLayout-YOLO
