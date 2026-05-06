# Research: Hardcoded Values in Configuration Files, Docker Setup, and Infrastructure Code

- **Query**: Find all hardcoded values in configuration files, Docker setup, and infrastructure code of this project
- **Scope**: internal
- **Date**: 2026-05-05

## Findings

### 1. Docker/docker-compose Hardcoded Values

#### docker-compose.yml (Production)
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 8 | `http://api:8000` | Internal API origin for web container | Already configurable via `INTERNAL_API_ORIGIN` |
| 11 | `3000` | Web container internal port | Already configurable via `WEB_PORT` |
| 42 | `127.0.0.1` | API bind host default | Already configurable via `API_BIND_HOST` |
| 42 | `8000` | API port default | Already configurable via `API_PORT` |
| 95 | `redis:7-alpine` | Redis image version | Should be configurable via env var |
| 97 | `redis-server --save "" --appendonly no` | Redis persistence config | Could be configurable |
| 28 | `30s` | Healthcheck interval | Could be configurable |
| 29 | `10s` | Healthcheck timeout | Could be configurable |
| 30 | `3` | Healthcheck retries | Could be configurable |
| 31 | `30s` | Web healthcheck start_period | Could be configurable |
| 59-62 | `30s`, `10s`, `3`, `240s` | API healthcheck parameters | Could be configurable |
| 87-90 | `30s`, `10s`, `3`, `240s` | Worker healthcheck parameters | Could be configurable |
| 100-102 | `10s`, `3s`, `5` | Redis healthcheck parameters | Could be configurable |

#### docker-compose.dev.yml (Development)
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 7 | `3000:3000` | Web port mapping | Already configurable via `WEB_PORT` |
| 15 | `8000` | API port default | Already configurable via `NEXT_PUBLIC_API_PORT` |
| 74 | `redis:7-alpine` | Redis image version | Should be configurable via env var |
| 76 | `6379:6379` | Redis port mapping | Should be configurable |

#### docker-compose.hosted.yml
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 9 | `0.0.0.0` | API bind host default | Already configurable via `API_BIND_HOST` |
| 9 | `8000` | API port default | Already configurable via `API_PORT` |
| 240s | `240s` | Healthcheck start_period | Could be configurable |

#### docker-compose.docs.yml
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 8 | `4173` | Docs port default | Already configurable via `DOCS_PORT` |

### 2. Dockerfile Hardcoded Values

#### api/Dockerfile
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 1 | `python:3.11-slim-bookworm` | Python base image | Should be configurable via ARG |
| 8-14 | System packages | OCR runtime dependencies | Hardcoded, acceptable |
| 24 | `8000` | Exposed port | Already configurable via env var |

#### web/Dockerfile
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 1 | `node:20-alpine` | Node base image | Should be configurable via ARG |
| 15 | `3000` | Exposed port | Already configurable via env var |

#### web/Dockerfile.prod
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 1 | `node:20-alpine` | Node base image | Should be configurable via ARG |
| 5 | `1` | NEXT_TELEMETRY_DISABLED | Hardcoded, acceptable |
| 13 | `http://api:8000` | INTERNAL_API_ORIGIN default | Already configurable via ARG |
| 24 | `3000` | PORT default | Already configurable via env var |
| 25 | `0.0.0.0` | HOSTNAME | Hardcoded, acceptable for production |
| 37 | `3000` | Exposed port | Already configurable via env var |

### 3. Config Files (api/app/config.py)

| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 12 | `127.0.0.1` | api_bind_host default | Already configurable via env var |
| 14 | `100` | max_file_mb default | Already configurable via env var |
| 15 | `200` | max_pages default | Already configurable via env var |
| 18 | `1440` | job_ttl_minutes default (24h) | Already configurable via env var |
| 20 | `15` | job_cleanup_interval_minutes default | Already configurable via env var |
| 23 | `15` | job_keepalive_interval_s default | Already configurable via env var |
| 25 | `200` | job_debug_events_limit default | Already configurable via env var |
| 28 | `data/jobs` | job_root_dir default | Already configurable via env var |
| 29 | `redis://redis:6379/0` | redis_url default | Already configurable via env var |
| 30 | `INFO` | log_level default | Already configurable via env var |
| 38 | `200` | ocr_render_dpi default | Already configurable via env var |
| 39 | `200` | scanned_render_dpi default | Already configurable via env var |
| 50 | `300` | ocr_page_timeout_s default (5min) | Already configurable via env var |
| 54 | `2` | ocr_max_consecutive_timeouts default | Already configurable via env var |
| 57 | `3600` | ocr_total_timeout_s default (1h) | Already configurable via env var |
| 60 | `12` | ocr_image_region_timeout_s default | Already configurable via env var |
| 61 | `http://localhost:3000,http://127.0.0.1:3000` | cors_allow_origins default | Already configurable via env var |
| 66 | `http://localhost:3000/auth/callback` | linuxdo_redirect_uri default | Already configurable via env var |
| 70 | `True` | cookie_secure default | Already configurable via env var |
| 72 | `data/pdf2ppt.db` | sqlite_path default | Already configurable via env var |
| 76 | `self` | deploy_mode default | Already configurable via env var |
| 78 | `admin12345678` | admin_default_password | **SECURITY RISK**: Should be randomly generated or required |
| 80 | `60` | rate_limit_requests default | Already configurable via env var |
| 81 | `60` | rate_limit_window_seconds default | Already configurable via env var |
| 83 | `500` | min_disk_space_mb default | Already configurable via env var |

### 4. Redis Key Patterns (api/app/services/redis_service.py)

| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 133 | `job:{job_id}` | Job metadata key prefix | Should be configurable |
| 137 | `job:{job_id}:cancel` | Cancel flag key pattern | Should be configurable |
| 363 | `job:{job_id}:secrets` | Secrets key pattern | Should be configurable |
| 408 | `job:*` | Job key scan pattern | Derived from job key prefix |
| 447 | `rl:{client_ip}` | Rate limit key pattern | Should be configurable |
| 112-113 | `1` second | Redis socket timeout | Could be configurable |

### 5. API Configuration Hardcoded Values

#### api/app/auth.py
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 21 | `https://connect.linux.do/oauth2/authorize` | LinuxDo authorize URL | Hardcoded, acceptable (external service) |
| 22 | `https://connect.linux.do/oauth2/token` | LinuxDo token URL | Hardcoded, acceptable (external service) |
| 23 | `https://connect.linux.do/api/user` | LinuxDo userinfo URL | Hardcoded, acceptable (external service) |
| 26 | `HS256` | JWT algorithm | Could be configurable |
| 27 | `60` | ACCESS_TOKEN_EXPIRE_MINUTES | Could be configurable |
| 28 | `30` | REFRESH_TOKEN_EXPIRE_DAYS | Could be configurable |
| 31 | `600` | OAuth state TTL (10min) | Could be configurable |
| 87 | `10.0` | httpx timeout for token exchange | Could be configurable |
| 118 | `10.0` | httpx timeout for user info fetch | Could be configurable |

#### api/app/main.py
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 28 | `127.0.0.1`, `localhost`, `::1`, `[::1]` | Loopback host list | Hardcoded, acceptable |
| 64 | `5` seconds | Cleanup thread join timeout | Could be configurable |
| 69 | `PDF to PPT API` | App title | Hardcoded, acceptable |
| 70 | `Convert PDF documents and images to PowerPoint presentations` | App description | Hardcoded, acceptable |
| 71 | `0.1.0` | App version | Should be configurable or read from package |
| 107 | `/api/v1/auth/`, `/api/v1/admin/`, `/api/v1/setup/` | Bearer token skip paths | Could be configurable |

### 6. Worker Configuration Hardcoded Values

#### api/app/worker.py
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 1061 | `default` | RQ queue name | Could be configurable |
| 1053 | `INFO` | Default log level | Already configurable via `LOG_LEVEL` |

#### api/app/services/job_cleanup.py
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 55 | `1440` | Default TTL minutes fallback | Already configurable via settings |
| 134 | `15` | Default cleanup interval fallback | Already configurable via settings |
| 141 | `1440` | Default TTL for logging | Already configurable via settings |

### 7. Build Configuration Hardcoded Values

#### web/next.config.mjs
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 5 | `http://api:8000` | Default internal API origin | Already configurable via env var |
| 19 | `standalone` | Next.js output mode | Hardcoded, acceptable |

### 8. OCR Configuration Hardcoded Values

#### api/app/convert/ocr/base.py
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 75 | `PaddlePaddle/PaddleOCR-VL` | Default PaddleOCR-VL model v1 | Hardcoded, acceptable |
| 76 | `PaddlePaddle/PaddleOCR-VL-1.5` | PaddleOCR-VL model v1.5 | Hardcoded, acceptable |
| 77 | `PaddlePaddle/PaddleOCR-VL` | Default PaddleOCR-VL model | Hardcoded, acceptable |
| 78 | `vllm-server` | Default PaddleDoc backend | Could be configurable |
| 124 | `chi_sim+eng` | Default Tesseract language | Already configurable via env var |
| 138 | `ch` | Default Paddle language | Could be configurable |

#### api/app/convert/ocr/vendors.py
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 67 | `gpt-4o-mini` | Default OpenAI model | Hardcoded, acceptable |
| 69 | `8192` | max_tokens_ocr default | Could be configurable |
| 70 | `4096` | max_tokens_refiner default | Could be configurable |
| 92 | `https://api.siliconflow.cn/v1` | SiliconFlow base URL | Hardcoded, acceptable (vendor) |
| 93 | `Qwen/Qwen2.5-VL-72B-Instruct` | SiliconFlow default model | Hardcoded, acceptable (vendor) |
| 94 | `4096` | SiliconFlow max_tokens_ocr | Could be configurable |
| 95 | `2048` | SiliconFlow max_tokens_refiner | Could be configurable |
| 101 | `180.0` | SiliconFlow predict_timeout_override | Could be configurable |
| 102 | `20.0` | SiliconFlow retry_timeout_override | Could be configurable |
| 105 | `10.0` | SiliconFlow singleflight_wait_s | Could be configurable |
| 106 | `2` | SiliconFlow layout_block_max_concurrency | Could be configurable |
| 110 | `https://api.ppio.com/openai` | PPIO base URL | Hardcoded, acceptable (vendor) |
| 111 | `qwen/qwen2.5-vl-72b-instruct` | PPIO default model | Hardcoded, acceptable (vendor) |
| 114 | `3072` | PPIO max_tokens_refiner | Could be configurable |
| 118 | `https://api.novita.ai/openai` | Novita base URL | Hardcoded, acceptable (vendor) |
| 119 | `qwen/qwen2.5-vl-72b-instruct` | Novita default model | Hardcoded, acceptable (vendor) |
| 127 | `https://api.deepseek.com/v1` | DeepSeek base URL | Hardcoded, acceptable (vendor) |
| 128 | `deepseek-ai/DeepSeek-OCR` | DeepSeek default model | Hardcoded, acceptable (vendor) |

#### api/app/convert/ocr/ai_client.py
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 1360 | `30.0` | OCR_PADDLE_VL_DOCPARSER_INIT_TIMEOUT_S default | Already configurable via env var |
| 3788 | `25.0` | OCR_AI_REQUEST_TIMEOUT_S default | Already configurable via env var |
| 3788 | `8.0` | Minimum timeout | Hardcoded, acceptable |
| 3797 | - | OCR_AI_REQUEST_TIMEOUT_S_QWEN default | Already configurable via env var |
| 3806 | - | OCR_AI_REQUEST_TIMEOUT_S_DEEPSEEK_OCR default | Already configurable via env var |
| 3816 | - | OCR_AI_REQUEST_TIMEOUT_S_PADDLE_VL default | Already configurable via env var |

#### api/app/convert/ocr/local_providers.py
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 364 | `0.95` | Baidu OCR default confidence | Could be configurable |
| 384 | `50.0` | Tesseract default min_confidence | Already configurable via env var |
| 384 | `chi_sim+eng` | Tesseract default language | Already configurable via env var |

### 9. Frontend Hardcoded Values

#### web/src/lib/api.ts
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 10 | `http://localhost:8000` | DEFAULT_FALLBACK_ORIGIN | Hardcoded, acceptable |
| 11 | `8000` | DEFAULT_FALLBACK_PORT | Hardcoded, acceptable |
| 168 | `1200` | Probe timeout (ms) | Could be configurable |

#### web/src/lib/settings.ts
| Line | Hardcoded Value | Description | Should Be Configurable |
|------|----------------|-------------|----------------------|
| 95 | `https://api.siliconflow.cn/v1` | SILICONFLOW_BASE_URL | Hardcoded, acceptable (vendor) |
| 100 | `pdf-to-ppt.settings.v1` | SETTINGS_STORAGE_KEY | Hardcoded, acceptable |
| 165 | `0.35` | imageBgClearExpandMinPt default | Could be configurable |
| 166 | `1.5` | imageBgClearExpandMaxPt default | Could be configurable |
| 167 | `0.012` | imageBgClearExpandRatio default | Could be configurable |
| 168 | `0.0025` | scannedImageRegionMinAreaRatio default | Could be configurable |
| 169 | `0.72` | scannedImageRegionMaxAreaRatio default | Could be configurable |
| 170 | `4.8` | scannedImageRegionMaxAspectRatio default | Could be configurable |
| 171 | `200` | ocrRenderDpi default | Could be configurable |
| 182 | `35` | ocrTesseractMinConfidence default | Could be configurable |
| 183 | `chi_sim+eng` | ocrTesseractLanguage default | Could be configurable |
| 194 | `2200` | ocrPaddleVlDocparserMaxSidePx default | Could be configurable |
| 196 | `1` | ocrAiPageConcurrency default | Could be configurable |
| 200 | `0` | ocrAiMaxRetries default | Could be configurable |

### 10. Timeout Values Across Codebase

| File | Line | Timeout Value | Description |
|------|------|---------------|-------------|
| api/app/auth.py | 87 | `10.0` | Token exchange httpx timeout |
| api/app/auth.py | 118 | `10.0` | User info fetch httpx timeout |
| api/app/routers/models.py | 401 | `10` | Model list API timeout |
| api/app/convert/ocr/ai_client.py | 1360 | `30.0` | PaddleOCR-VL init timeout |
| api/app/convert/ocr/ai_client.py | 3788 | `25.0` | AI OCR request timeout |
| api/app/convert/ocr/vendors.py | 101 | `180.0` | SiliconFlow predict timeout |
| api/app/convert/ocr/vendors.py | 102 | `20.0` | SiliconFlow retry timeout |
| api/app/convert/llm_adapter.py | 30 | `30.0` | Page timeout |
| api/app/convert/baidu_doc_adapter.py | 905 | `60.0` | Baidu client timeout |
| api/app/convert/baidu_doc_adapter.py | 1034 | `900.0` | Baidu poll timeout |
| api/app/convert/mineru_adapter.py | 1419 | `60.0` | MinerU request timeout |
| api/app/convert/mineru_adapter.py | 1606 | `1200.0` | MinerU download timeout |
| api/app/convert/mineru_adapter.py | 1712 | `3600.0` | MinerU poll timeout |

### 11. Cookie/Session Hardcoded Values

| File | Line | Hardcoded Value | Description |
|------|------|-----------------|-------------|
| api/app/auth.py | 27 | `60` | ACCESS_TOKEN_EXPIRE_MINUTES |
| api/app/auth.py | 28 | `30` | REFRESH_TOKEN_EXPIRE_DAYS |
| api/app/auth.py | 31 | `600` | OAuth state TTL (10min) |
| api/app/routers/auth.py | 417 | `3600` | Access token cookie max_age |
| api/app/routers/auth.py | 427 | `30 * 24 * 3600` | Refresh token cookie max_age |
| api/app/routers/setup.py | 23 | `3600` | Access token cookie max_age |
| api/app/routers/setup.py | 32 | `30 * 24 * 3600` | Refresh token cookie max_age |
| api/app/models/user.py | 128 | `3600` | Token expires_in default |

### 12. User Quota Hardcoded Values

| File | Line | Hardcoded Value | Description |
|------|------|-----------------|-------------|
| api/app/models/user.py | 55 | `10` | daily_task_limit default |
| api/app/models/user.py | 56 | `100.0` | max_file_size_mb default |
| api/app/models/user.py | 57 | `2` | concurrent_task_limit default |
| api/app/models/user.py | 82 | `10` | UserResponse daily_task_limit |
| api/app/models/user.py | 83 | `100.0` | UserResponse max_file_size_mb |
| api/app/models/user.py | 84 | `2` | UserResponse concurrent_task_limit |
| api/app/models/user.py | 107 | `10` | QuotaInfo daily_task_limit |
| api/app/models/user.py | 108 | `100.0` | QuotaInfo max_file_size_mb |
| api/app/models/user.py | 109 | `2` | QuotaInfo concurrent_task_limit |

### 13. PPTX Generation Constants

| File | Line | Hardcoded Value | Description |
|------|------|-----------------|-------------|
| api/app/convert/pptx/constants.py | 9 | `914400` | EMU per inch |
| api/app/convert/pptx/constants.py | 10 | `72.0` | Points per inch |
| api/app/convert/pptx/constants.py | 11 | `12700.0` | EMU per point |

### 14. MinerU Adapter Constants

| File | Line | Hardcoded Value | Description |
|------|------|-----------------|-------------|
| api/app/convert/mineru_adapter.py | 20 | `https://mineru.net` | Default MinerU base URL |
| api/app/convert/mineru_adapter.py | 21 | `1000.0` | Default page width (pt) |
| api/app/convert/mineru_adapter.py | 22 | `1000.0` | Default page height (pt) |

### 15. Infrastructure Deployment Files

#### render.yaml
| Line | Hardcoded Value | Description |
|------|-----------------|-------------|
| 4 | `free` | Redis plan |
| 11 | `free` | API plan |
| 18 | `0.0.0.0` | API_BIND_HOST |
| 25 | `1` | EMBEDDED_WORKER_CONCURRENCY |
| 29 | `/app/data/jobs` | JOB_ROOT_DIR |
| 31 | `1` | OCR_PADDLE_LAYOUT_PREWARM |
| 33 | `worker` | OCR_PADDLE_LAYOUT_PREWARM_TARGET |
| 35 | `1` | PYTHONUNBUFFERED |
| 40 | `free` | Web plan |

#### zeabur.template.yaml
| Line | Hardcoded Value | Description |
|------|-----------------|-------------|
| 51 | `redis:7-alpine` | Redis image |
| 75 | `python:3.11-slim-bookworm` | Python base image |
| 94 | `8000` | API port |
| 110 | `0.0.0.0` | API_BIND_HOST |
| 112 | `redis://redis.zeabur.internal:6379/0` | Redis URL |
| 114 | `1` | EMBEDDED_WORKER_CONCURRENCY |
| 116 | `/app/data/jobs` | JOB_ROOT_DIR |
| 118 | `1` | OCR_PADDLE_LAYOUT_PREWARM |
| 120 | `worker` | OCR_PADDLE_LAYOUT_PREWARM_TARGET |
| 122 | `1` | PYTHONUNBUFFERED |
| 142 | `node:20-alpine` | Node base image |
| 154 | `http://api.zeabur.internal:8000` | INTERNAL_API_ORIGIN |
| 166 | `http://api.zeabur.internal:8000` | INTERNAL_API_ORIGIN |
| 172 | `3000` | Web port |
| 174 | `3000` | PORT default |

## Duplicated Values Across Files

1. **Redis URL** (`redis://redis:6379/0`):
   - .env.example:34
   - api/app/config.py:29
   - docker-compose.yml:86 (healthcheck)
   - docker-compose.dev.yml:65 (healthcheck)
   - zeabur.template.yaml:112

2. **Port numbers** (3000, 8000):
   - docker-compose.yml:11,42
   - docker-compose.dev.yml:7,15
   - docker-compose.hosted.yml:9
   - .env.example:4,7
   - api/Dockerfile:24
   - web/Dockerfile:15
   - web/Dockerfile.prod:24,37
   - zeabur.template.yaml:94,172,174,177

3. **Healthcheck parameters** (30s, 10s, 3 retries):
   - docker-compose.yml:28-30,59-61,87-89
   - docker-compose.dev.yml:39-42,65-68
   - docker-compose.hosted.yml:23-26

4. **API bind host** (127.0.0.1, 0.0.0.0):
   - docker-compose.yml:42
   - docker-compose.hosted.yml:9
   - api/app/config.py:12
   - render.yaml:18
   - zeabur.template.yaml:110

5. **CORS origins** (http://localhost:3000, http://127.0.0.1:3000):
   - api/app/config.py:61
   - api/app/config.py:119
   - api/app/config.py:127
   - .env.example:76

## Inconsistencies Found

1. **Default admin password**:
   - api/app/config.py:78: `admin12345678` (hardcoded default)
   - .env.example:21: `WEB_ACCESS_PASSWORD=123456` (different password)
   - **Security risk**: Should require explicit configuration

2. **Default timeout values**:
   - Different timeout values across different OCR providers (25s, 30s, 60s, 180s, etc.)
   - Some are configurable via env vars, others are hardcoded

3. **Default quota values**:
   - api/app/models/user.py:55-57: `10`, `100.0`, `2`
   - web/src/lib/auth.ts:75-77: `10`, `100`, `2` (consistent)

4. **Default DPI values**:
   - api/app/config.py:38-39: `200` (ocr_render_dpi, scanned_render_dpi)
   - api/app/convert/llm_adapter.py:31: `150` (_DEFAULT_RENDER_DPI)
   - web/src/lib/settings.ts:171: `200` (ocrRenderDpi)

## Recommendations

### High Priority (Security/Critical)

1. **Remove hardcoded admin password** (`admin12345678`):
   - Generate random password on first run
   - Or require explicit configuration via env var

2. **Make Redis URL configurable**:
   - Already configurable, but hardcoded in healthchecks
   - Extract to env var for healthcheck commands

3. **Make port numbers configurable**:
   - Already configurable via env vars
   - Ensure all references use env vars consistently

### Medium Priority (Configuration)

1. **Extract Redis key prefixes**:
   - `job:`, `job:{id}:cancel`, `job:{id}:secrets`, `rl:`
   - Make configurable for multi-tenant scenarios

2. **Make timeout values configurable**:
   - OCR timeouts, HTTP client timeouts, healthcheck timeouts
   - Already partially configurable, complete the coverage

3. **Make healthcheck parameters configurable**:
   - interval, timeout, retries, start_period
   - Extract to env vars

4. **Make quota defaults configurable**:
   - daily_task_limit, max_file_size_mb, concurrent_task_limit
   - Already configurable via admin UI, consider env var defaults

### Low Priority (Nice to Have)

1. **Make Docker image versions configurable**:
   - Redis, Python, Node base images
   - Use ARG in Dockerfiles

2. **Make JWT settings configurable**:
   - Algorithm, token expiration times
   - Already partially configurable

3. **Make vendor-specific timeouts configurable**:
   - SiliconFlow, PPIO, Novita, DeepSeek timeouts
   - Already partially configurable via env vars

## Caveats / Not Found

- Some hardcoded values are acceptable (vendor URLs, algorithm names, etc.)
- Many values are already configurable via env vars but have hardcoded defaults
- Frontend settings are stored in localStorage and may have different defaults than backend
- Some values are duplicated between frontend and backend (should be single source of truth)
