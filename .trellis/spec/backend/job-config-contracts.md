# Job Config Contracts

> Executable contract for the structured job config boundary: request payload → `JobConfig` model → flattened worker kwargs.

---

## Scenario: Structured JobConfig must survive flattening

### 1. Scope / Trigger

- Trigger: any change to `api/app/schemas/job_config.py`, `to_worker_kwargs()`, `/jobs/v2` job creation, or worker option plumbing.
- This is mandatory code-spec depth because it is a cross-layer config contract:
  frontend payload → backend schema → flat worker kwargs → worker/runtime behavior.

### 2. Signatures

- Frontend request shape: multipart upload with `config` JSON for `POST /api/v1/jobs/v2`
- Backend schema entry: `api/app/schemas/job_config.py::JobConfig`
- Flattening boundary: `api/app/schemas/job_config.py::JobConfig.to_worker_kwargs() -> dict[str, object]`
- Route validation path: `api/app/routers/jobs.py::create_job_v2()` → `validate_and_normalize_job_options()` → `_create_job_core()`
- Worker consumer: `api/app/worker.py::process_pdf_job()`

### 3. Contracts

#### Request / schema contract

- Structured config fields defined on `JobConfig` are the source of truth for `/jobs/v2`.
- If a field is intended to affect worker behavior, it must either:
  - be preserved in `to_worker_kwargs()`, or
  - be intentionally overridden with a provider-specific rule that is documented in code and tests.

#### Flattening contract

- `to_worker_kwargs()` is a translation layer, not a policy reset layer.
- Do **not** silently replace user-provided booleans with hardcoded defaults during flattening.
- Top-level booleans such as:
  - `enable_layout_assist`
  - `layout_assist_apply_image_regions`
  must round-trip from `JobConfig(...)` into worker kwargs unless a documented per-provider exception applies.

#### Worker contract

- The worker should receive effective values that reflect the validated job config.
- If a value is intentionally forced for a provider branch, the branch must be explicit and reviewable.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| New `JobConfig` field affects runtime | Add field to schema and map it in `to_worker_kwargs()` |
| Field is unsupported for a provider | Override only in a documented provider-specific branch |
| Structured field is dropped accidentally | Treat as a contract bug and add regression test |
| Legacy/dead worker kwarg is still emitted | Remove it or document why it remains |

### 5. Good / Base / Bad Cases

- Good: `JobConfig(enable_layout_assist=True).to_worker_kwargs()["enable_layout_assist"] is True`
- Base: defaults remain stable for unrelated fields when one config flag changes.
- Bad: a valid field exists on `JobConfig`, but `to_worker_kwargs()` emits a hardcoded value and disables the feature silently.

### 6. Tests Required

- Add focused unit tests for `JobConfig.to_worker_kwargs()` whenever new runtime-affecting fields are introduced.
- Assertions should cover:
  - explicit `True` propagation
  - explicit `False` propagation
  - paired flags that must travel together
  - provider-specific override branches
  - unrelated defaults remain unchanged

Minimum regression pattern:

```python
config = JobConfig(enable_layout_assist=True)
kwargs = config.to_worker_kwargs()
assert kwargs["enable_layout_assist"] is True
```

### 7. Wrong vs Correct

#### Wrong

```python
return {
    "enable_layout_assist": False,
    "layout_assist_apply_image_regions": False,
}
```

#### Correct

```python
return {
    "enable_layout_assist": self.enable_layout_assist,
    "layout_assist_apply_image_regions": self.layout_assist_apply_image_regions,
}
```

---

## Review Checklist

Before merging `/jobs/v2` config changes, verify:

- [ ] Every runtime-affecting `JobConfig` field is either preserved or intentionally overridden
- [ ] No silent hardcoded fallback was introduced in `to_worker_kwargs()`
- [ ] Regression tests exist for new booleans/enums at the flattening boundary
- [ ] Worker/runtime code still reads the emitted kwargs names expected by the route layer
