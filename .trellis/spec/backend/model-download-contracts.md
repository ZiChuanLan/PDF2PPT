# Model Download Contracts

> Runtime contract for local model downloads that need both Python runtime code and model weights.

---

## Scope

- Applies to backend model download/status/delete flows under `api/app/routers/models.py`
  and `api/app/routers/_download_manager.py`.
- Applies when a local model needs large optional runtime packages in addition
  to model weights, for example MobileSAM.

## Contracts

- Keep the repository and base image lean by default. Do not vendor third-party
  model source code into the repo unless the upstream cannot be installed from a
  configurable URL.
- Downloaded runtime packages must be installed under persistent app data, not
  into an ephemeral container-only path. Default target:
  `/app/data/python-packages/<runtime-name>`.
- The provider module must add its persistent runtime target to `sys.path`
  before checking readiness or importing the runtime package.
- Model readiness must reflect the full runnable state:
  runtime dependencies available + model/checkpoint weights available.
- A download task must verify the model after download by loading enough of the
  runtime to prove the downloaded state is usable by workers.
- Delete actions for optional downloaded runtimes should remove both model
  weights and the persistent runtime package cache when that runtime is scoped
  to the model.
- Network-dependent package URLs must be configurable through environment
  variables so deployments can use mirrors.

## MobileSAM

- Runtime package target defaults to `/app/data/python-packages/sam-runtime`.
- Checkpoint target defaults to `/app/data/models/sam/mobile_sam.pt`.
- Supported mirror overrides:
  - `MOBILE_SAM_PACKAGE_URL` or `SAM_PACKAGE_URL`
  - `MOBILE_SAM_CHECKPOINT_URL` or `SAM_CHECKPOINT_URL`
  - `MOBILE_SAM_CHECKPOINT_PATH` or `SAM_CHECKPOINT_PATH`
  - `MOBILE_SAM_PYTORCH_INDEX_URL` or `PYTORCH_CPU_INDEX_URL`

## Tests Required

- Download-manager tests must cover:
  - runtime package URL overrides
  - persistent runtime target resolution
  - download order for runtime dependencies, checkpoint, and verification
  - actionable error messages for DNS/proxy failures
