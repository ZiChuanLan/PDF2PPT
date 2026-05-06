# Research: Backend Hardcoded Values Audit

- **Query**: Find all hardcoded magic values, magic numbers, and hardcoded strings in the backend Python code
- **Scope**: internal
- **Date**: 2026-05-05

## Findings

### 1. Configuration Defaults in `config.py`

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `api/app/config.py:12` | `"127.0.0.1"` | API bind host default | ✅ `api_bind_host` |
| `api/app/config.py:14` | `100` | Max file size MB | ✅ `max_file_mb` |
| `api/app/config.py:15` | `200` | Max pages | ✅ `max_pages` |
| `api/app/config.py:18` | `1440` | Job TTL minutes (24h) | ✅ `job_ttl_minutes` |
| `api/app/config.py:20` | `15` | Cleanup interval minutes | ✅ `job_cleanup_interval_minutes` |
| `api/app/config.py:23` | `15` | Keepalive interval seconds | ✅ `job_keepalive_interval_s` |
| `api/app/config.py:25` | `200` | Debug events limit | ✅ `job_debug_events_limit` |
| `api/app/config.py:28` | `"data/jobs"` | Job root directory | ✅ `job_root_dir` |
| `api/app/config.py:29` | `"redis://redis:6379/0"` | Redis URL | ✅ `redis_url` |
| `api/app/config.py:38` | `200` | OCR render DPI | ✅ `ocr_render_dpi` |
| `api/app/config.py:39` | `200` | Scanned render DPI | ✅ `scanned_render_dpi` |
| `api/app/config.py:47` | `5` | Final preview max pages | ✅ `export_final_preview_max_pages` |
| `api/app/config.py:50` | `300` | OCR page timeout seconds | ✅ `ocr_page_timeout_s` |
| `api/app/config.py:54` | `2` | Max consecutive timeouts | ✅ `ocr_max_consecutive_timeouts` |
| `api/app/config.py:57` | `3600` | OCR total timeout seconds | ✅ `ocr_total_timeout_s` |
| `api/app/config.py:60` | `12` | Image region timeout seconds | ✅ `ocr_image_region_timeout_s` |
| `api/app/config.py:61` | `"http://localhost:3000,http://127.0.0.1:3000"` | CORS origins | ✅ `cors_allow_origins` |
| `api/app/config.py:66` | `"http://localhost:3000/auth/callback"` | LinuxDo redirect URI | ✅ `linuxdo_redirect_uri` |
| `api/app/config.py:72` | `"data/pdf2ppt.db"` | SQLite path | ✅ `sqlite_path` |
| `api/app/config.py:76` | `"self"` | Deploy mode | ✅ `deploy_mode` |
| `api/app/config.py:78` | `"admin12345678"` | Default admin password | ✅ `admin_default_password` |
| `api/app/config.py:80` | `60` | Rate limit requests | ✅ `rate_limit_requests` |
| `api/app/config.py:81` | `60` | Rate limit window seconds | ✅ `rate_limit_window_seconds` |
| `api/app/config.py:83` | `500` | Min disk space MB | ✅ `min_disk_space_mb` |

### 2. Magic Numbers in OCR Pipeline (`convert/ocr/ai_client.py`)

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `ai_client.py:120` | `160` | Debug text compact limit | ❌ No constant |
| `ai_client.py:356` | `60.0` | Rate limiter cutoff window (seconds) | ❌ No constant |
| `ai_client.py:382` | `60.0` | Rate limiter max wait (seconds) | ❌ No constant |
| `ai_client.py:413` | `0.05`, `5.0` | Sleep bounds for rate limiter | ❌ No constant |
| `ai_client.py:493` | `4.0` | Chars per token estimate | ❌ No constant |
| `ai_client.py:567` | `8.0`, `0.75`, `2` | Retry backoff base/max/multiplier | ❌ No constant |
| `ai_client.py:569` | `2.0` | Rate-limited min delay | ❌ No constant |
| `ai_client.py:570` | `0.25` | Non-rate-limited min delay | ❌ No constant |
| `ai_client.py:740` | `6000` | Max paddle doc max side px | ❌ No constant |
| `ai_client.py:875` | `400` | Debug text limit for content | ❌ No constant |
| `ai_client.py:904` | `240` | Debug text limit for texts | ❌ No constant |
| `ai_client.py:915` | `64` | Debug text limit for label | ❌ No constant |
| `ai_client.py:1188` | `10.0` | Progress log interval default | ✅ env `OCR_PADDLE_VL_DOCPARSER_PROGRESS_LOG_INTERVAL_S` |
| `ai_client.py:1360` | `30.0` | Init timeout default | ✅ env `OCR_PADDLE_VL_DOCPARSER_INIT_TIMEOUT_S` |
| `ai_client.py:1427` | `10.0` | Min predict timeout | ❌ No constant |
| `ai_client.py:1428` | `120.0` | Default predict timeout | ✅ env `OCR_PADDLE_VL_DOCPARSER_PREDICT_TIMEOUT_S` |
| `ai_client.py:1433` | `180.0` | PaddleOCR-VL-1.5 predict timeout | ❌ No constant |
| `ai_client.py:1444` | `90.0` | Default retry timeout cap | ❌ No constant |
| `ai_client.py:1501` | `3.0` | Singleflight wait default | ❌ No constant |
| `ai_client.py:1564` | `1.0` | Scale factor default | ❌ (identity) |
| `ai_client.py:1657` | `0.1`, `0.01` | Wait bounds for concurrency | ❌ No constant |
| `ai_client.py:1693` | `1.0` | Done wait timeout | ❌ No constant |
| `ai_client.py:1939` | `5.0` | Min layout model init timeout | ❌ No constant |
| `ai_client.py:1940` | `30.0` | Default layout model init timeout | ✅ env `OCR_AI_LAYOUT_MODEL_INIT_TIMEOUT_S` |
| `ai_client.py:2041` | `3.0` | Min block dimension threshold | ❌ No constant |
| `ai_client.py:2136` | `5.0` | Min layout block predict timeout | ❌ No constant |
| `ai_client.py:2137` | `45.0` | Default layout block predict timeout | ✅ env `OCR_AI_LAYOUT_MODEL_PREDICT_TIMEOUT_S` |
| `ai_client.py:2296` | `24`, `2`, `0.03` | Padding bounds for block crop | ❌ No constant |
| `ai_client.py:2297` | `24`, `2`, `0.18` | Y-padding bounds for block crop | ❌ No constant |
| `ai_client.py:2395` | `2`, `18`, `0.10` | Ring Y margin bounds | ❌ No constant |
| `ai_client.py:2396` | `2`, `18`, `0.04` | Ring X margin bounds | ❌ No constant |
| `ai_client.py:2421` | `18.0`, `150.0`, `22.0` | Background diff thresholds | ❌ No constant |
| `ai_client.py:2424` | `2`, `12`, `0.05` | Outer margin bounds | ❌ No constant |
| `ai_client.py:2433` | `2`, `0.0035` | Row threshold ratio | ❌ No constant |
| `ai_client.py:2434` | `1`, `0.020` | Col threshold ratio | ❌ No constant |
| `ai_client.py:2459` | `0.94` | Keep area ratio threshold | ❌ No constant |
| `ai_client.py:2460` | `0.97` | Width keep ratio threshold | ❌ No constant |
| `ai_client.py:2461` | `0.90` | Height keep ratio threshold | ❌ No constant |
| `ai_client.py:2465` | `2`, `18`, `0.08` | Pad X local bounds | ❌ No constant |
| `ai_client.py:2466` | `2`, `12`, `0.12` | Pad Y local bounds | ❌ No constant |
| `ai_client.py:2486` | `0.985`, `0.94` | Tightened width/height keep ratios | ❌ No constant |
| `ai_client.py:2495` | `1.5` | Default tolerance px | ❌ No constant |
| `ai_client.py:2560` | `10.0` | Block progress log interval | ✅ env `OCR_AI_LAYOUT_BLOCK_PROGRESS_LOG_INTERVAL_S` |
| `ai_client.py:2567` | `40.0` | Block request timeout | ✅ env `OCR_AI_LAYOUT_BLOCK_REQUEST_TIMEOUT_S` |
| `ai_client.py:2595` | `12.0` | Request timeout buffer | ❌ No constant |
| `ai_client.py:2596` | `1.5` | Request timeout multiplier | ❌ No constant |
| `ai_client.py:2597` | `55.0` | Max request timeout cap | ❌ No constant |
| `ai_client.py:2602` | `8.0` | Retry timeout buffer | ❌ No constant |
| `ai_client.py:2609` | `8.0` | Retry timeout buffer (alt) | ❌ No constant |

### 3. Magic Numbers in Local Providers (`convert/ocr/local_providers.py`)

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `local_providers.py:342` | `0.16` | Baidu area ratio prune threshold | ❌ No constant |
| `local_providers.py:345` | `0.85` | Baidu width ratio prune threshold | ❌ No constant |
| `local_providers.py:346` | `0.08` | Baidu height ratio prune threshold | ❌ No constant |
| `local_providers.py:347` | `24` | Baidu compact text length limit | ❌ No constant |
| `local_providers.py:351` | `0.06` | Baidu area ratio threshold (alt) | ❌ No constant |
| `local_providers.py:352` | `6` | Baidu compact text length limit (alt) | ❌ No constant |
| `local_providers.py:353` | `0.06` | Baidu height ratio threshold (alt) | ❌ No constant |
| `local_providers.py:364` | `0.95` | Baidu default confidence | ❌ No constant |
| `local_providers.py:384` | `50.0` | Tesseract default min confidence | ❌ No constant |
| `local_providers.py:536` | `11` | Tesseract PSM mode (sparse text) | ❌ No constant |
| `local_providers.py:600` | `12` | Low recall line threshold | ❌ No constant |
| `local_providers.py:601` | `80` | Low recall word threshold | ❌ No constant |
| `local_providers.py:629` | `25.0` | Low confidence retry threshold | ❌ No constant |
| `local_providers.py:632` | `8`, `40` | Looks-empty thresholds | ❌ No constant |
| `local_providers.py:714` | `2200` | PaddleOCR max side pixels | ❌ No constant |
| `local_providers.py:878` | `0.85` | PaddleOCR default confidence | ❌ No constant |
| `local_providers.py:983` | `20000` | Max nodes for result traversal | ❌ No constant |
| `local_providers.py:1199` | `50.0` | Tesseract fallback min confidence | ❌ No constant |
| `local_providers.py:1550` | `140` | Min items for merge detection (aiocr) | ❌ No constant |
| `local_providers.py:1557` | `0.18`, `2.9` | Word-level detection thresholds (aiocr) | ❌ No constant |
| `local_providers.py:1590` | `80` | Min items for merge detection (paddle) | ❌ No constant |
| `local_providers.py:1597` | `0.22`, `3.2` | Word-level detection thresholds (paddle) | ❌ No constant |
| `local_providers.py:2099` | `0.2126`, `0.7152`, `0.0722` | Luma coefficients (BT.709) | ❌ No constant |
| `local_providers.py:2107` | `3`, `12`, `0.03` | Background sample pad bounds | ❌ No constant |
| `local_providers.py:2136` | `2400.0` | Step calculation divisor | ❌ No constant |
| `local_providers.py:2152` | `8.0` | Foreground contrast threshold | ❌ No constant |
| `local_providers.py:2154` | `128.0` | Background luma midpoint | ❌ No constant |
| `local_providers.py:2161` | `14.0` | Preferred contrast threshold | ❌ No constant |
| `local_providers.py:2163` | `18.0` | Fallback contrast threshold | ❌ No constant |
| `local_providers.py:2165` | `900.0` | Distance threshold | ❌ No constant |
| `local_providers.py:2167` | `12` | Top candidate count | ❌ No constant |
| `local_providers.py:2172` | `6`, `96`, `4` | Keep count bounds | ❌ No constant |
| `local_providers.py:2175` | `128.0` | Luma midpoint for dark/light | ❌ No constant |
| `local_providers.py:2176` | `6.0` | Darker threshold | ❌ No constant |
| `local_providers.py:2181` | `6.0` | Lighter threshold | ❌ No constant |
| `local_providers.py:2186` | `24` | Max chosen RGBs | ❌ No constant |
| `local_providers.py:2188` | `18.0` | Min luma contrast | ❌ No constant |
| `local_providers.py:2189` | `17`, `245` | Fallback text colors | ❌ No constant |
| `local_providers.py:2320` | `1.8`, `0.025` | Gap threshold multipliers | ❌ No constant |
| `local_providers.py:2338` | `0.70`, `0.006` | Y threshold multipliers | ❌ No constant |
| `local_providers.py:2527` | `0.04`, `6.0` | X gap threshold multipliers | ❌ No constant |
| `local_providers.py:2529` | `0.55` | Close Y threshold multiplier | ❌ No constant |
| `local_providers.py:2531` | `0.35` | Overlap threshold multiplier | ❌ No constant |
| `local_providers.py:2558` | `1.8`, `0.025` | Gap threshold multipliers (merge) | ❌ No constant |
| `local_providers.py:2629` | `0.3` | Noise area ratio threshold | ❌ No constant |
| `local_providers.py:2633` | `0.08` | Noise height ratio threshold | ❌ No constant |
| `local_providers.py:2637` | `3` | Noise min text length | ❌ No constant |
| `local_providers.py:2643` | `0.08` | Noise width ratio threshold | ❌ No constant |
| `local_providers.py:2644` | `0.08` | Noise height ratio threshold (alt) | ❌ No constant |
| `local_providers.py:2645` | `2` | Noise min text length (alt) | ❌ No constant |
| `local_providers.py:2767` | `0.90` | Coarse AI prune: width ratio | ❌ No constant |
| `local_providers.py:2768` | `0.16` | Coarse AI prune: height ratio | ❌ No constant |
| `local_providers.py:2771` | `0.90` | Coarse AI prune: width ratio (alt) | ❌ No constant |
| `local_providers.py:2772` | `0.16` | Coarse AI prune: height ratio (alt) | ❌ No constant |
| `local_providers.py:2790` | `0.85` | Overlap merge threshold | ❌ No constant |

### 4. Magic Numbers in Worker (`worker.py`)

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `worker.py:369` | `72` | Min OCR render DPI | ❌ No constant |
| `worker.py:370` | `400` | Max OCR render DPI | ❌ No constant |
| `worker.py:376` | `120` | Turbo mode max DPI | ❌ No constant |
| `worker.py:378` | `160` | Fast mode max DPI | ❌ No constant |
| `worker.py:382` | `0.35` | Default image bg clear expand min pt | ❌ No constant |
| `worker.py:383` | `0.0`, `6.0` | Image bg clear expand min bounds | ❌ No constant |
| `worker.py:387` | `1.5` | Default image bg clear expand max pt | ❌ No constant |
| `worker.py:388` | `0.0`, `8.0` | Image bg clear expand max bounds | ❌ No constant |
| `worker.py:401` | `0.012` | Default image bg clear expand ratio | ❌ No constant |
| `worker.py:402` | `0.0`, `0.12` | Image bg clear expand ratio bounds | ❌ No constant |
| `worker.py:406` | `0.0025` | Default scanned image region min area ratio | ❌ No constant |
| `worker.py:407` | `0.0`, `0.35` | Scanned image region min area bounds | ❌ No constant |
| `worker.py:412` | `0.72` | Default scanned image region max area ratio | ❌ No constant |
| `worker.py:413` | `0.05`, `1.0` | Scanned image region max area bounds | ❌ No constant |
| `worker.py:424` | `0.05` | Area ratio increment | ❌ No constant |
| `worker.py:427` | `4.8` | Default max aspect ratio | ❌ No constant |
| `worker.py:428` | `1.2`, `30.0` | Max aspect ratio bounds | ❌ No constant |
| `worker.py:433` | `2200` | Default paddle doc max side px | ❌ No constant |
| `worker.py:434` | `0`, `6000` | Paddle doc max side px bounds | ❌ No constant |
| `worker.py:439` | `1` | Default page concurrency | ❌ No constant |
| `worker.py:440` | `1`, `8` | Page concurrency bounds | ❌ No constant |
| `worker.py:449` | `1`, `8` | Block concurrency bounds | ❌ No constant |
| `worker.py:457` | `1`, `2000` | RPM bounds | ❌ No constant |
| `worker.py:463` | `1000` | Default TPM | ❌ No constant |
| `worker.py:464` | `1`, `2_000_000` | TPM bounds | ❌ No constant |
| `worker.py:471` | `0`, `8` | Max retries bounds | ❌ No constant |
| `worker.py:583` | `"https://api.siliconflow.cn/v1"` | V2 mode fallback base URL | ❌ No constant |
| `worker.py:588` | `"Pro/deepseek-ai/deepseek-ocr"` | V2 mode fallback model | ❌ No constant |
| `worker.py:1167` | `"1h"` | Job timeout for memory backend | ❌ No constant |

### 5. Magic Numbers in Auth (`auth.py`)

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `auth.py:21` | `"https://connect.linux.do/oauth2/authorize"` | LinuxDo authorize URL | ❌ No constant |
| `auth.py:22` | `"https://connect.linux.do/oauth2/token"` | LinuxDo token URL | ❌ No constant |
| `auth.py:23` | `"https://connect.linux.do/api/user"` | LinuxDo userinfo URL | ❌ No constant |
| `auth.py:26` | `"HS256"` | JWT algorithm | ❌ No constant |
| `auth.py:27` | `60` | Access token expire minutes | ❌ No constant |
| `auth.py:28` | `30` | Refresh token expire days | ❌ No constant |
| `auth.py:31` | `600` | OAuth state TTL seconds (10 min) | ❌ No constant |
| `auth.py:87` | `10.0` | HTTP client timeout | ❌ No constant |
| `auth.py:118` | `10.0` | HTTP client timeout (userinfo) | ❌ No constant |
| `auth.py:233` | `7` | Invite code expiry days | ❌ No constant |
| `auth.py:318` | `"https://linux.do"` | LinuxDo avatar base URL | ❌ No constant |
| `auth.py:417` | `3600` | Access token cookie max age (1h) | ❌ No constant |
| `auth.py:427` | `30 * 24 * 3600` | Refresh token cookie max age (30d) | ❌ No constant |

### 6. Magic Numbers in Routers (`routers/jobs.py`)

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `jobs.py:76` | `144.0` | Default upload image DPI | ❌ No constant |
| `jobs.py:105` | `36.0`, `1200.0` | DPI normalization bounds | ❌ No constant |
| `jobs.py:197` | `95` | JPEG quality | ❌ No constant |
| `jobs.py:336` | `1440`, `960` | Probe image dimensions | ❌ No constant |
| `jobs.py:342` | `48`, `1392`, `912` | Probe image rectangle bounds | ❌ No constant |
| `jobs.py:343` | `28` | Probe image border radius | ❌ No constant |
| `jobs.py:344` | `224`, `228`, `236` | Probe image outline color | ❌ No constant |
| `jobs.py:348` | `104`, `116` | Probe image text position | ❌ No constant |
| `jobs.py:349` | `18` | Probe image font size (title) | ❌ No constant |
| `jobs.py:370` | `2160`, `1440` | Probe image resize dimensions | ❌ No constant |
| `jobs.py:376` | `400` | Error truncation limit | ❌ No constant |
| `jobs.py:445` | `3` | Max sample items | ❌ No constant |
| `jobs.py:456` | `120` | Sample text truncation limit | ❌ No constant |
| `jobs.py:602` | `50`, `200` | Job list limit bounds | ❌ No constant |
| `jobs.py:1018` | `1024 * 1024` | Chunk size (1MB) | ❌ No constant |

### 7. Magic Numbers in Redis Service (`services/redis_service.py`)

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `redis_service.py:102` | `20` | Min debug events limit | ❌ No constant |
| `redis_service.py:113` | `1` | Socket connect timeout | ❌ No constant |
| `redis_service.py:114` | `1` | Socket timeout | ❌ No constant |
| `redis_service.py:469` | `50` | Default list jobs limit | ❌ No constant |

### 8. Magic Numbers in Job Cleanup (`services/job_cleanup.py`)

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `job_cleanup.py:50` | `60` | Min TTL seconds | ❌ No constant |
| `job_cleanup.py:133` | `60` | Min cleanup interval seconds | ❌ No constant |

### 9. Hardcoded Vendor URLs and Models (`convert/ocr/vendors.py`)

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `vendors.py:91` | `"https://api.siliconflow.cn/v1"` | SiliconFlow base URL | ❌ No constant |
| `vendors.py:92` | `"Qwen/Qwen2.5-VL-72B-Instruct"` | SiliconFlow default model | ❌ No constant |
| `vendors.py:93` | `4096` | SiliconFlow max tokens OCR | ❌ No constant |
| `vendors.py:94` | `2048` | SiliconFlow max tokens refiner | ❌ No constant |
| `vendors.py:95` | `"/v1"` | SiliconFlow paddle doc path | ❌ No constant |
| `vendors.py:99` | `4` | SiliconFlow vl_rec_max_concurrency | ❌ No constant |
| `vendors.py:101` | `180.0` | SiliconFlow predict timeout override | ❌ No constant |
| `vendors.py:102` | `20.0` | SiliconFlow retry timeout override | ❌ No constant |
| `vendors.py:105` | `10.0` | SiliconFlow singleflight wait | ❌ No constant |
| `vendors.py:106` | `2` | SiliconFlow layout_block_max_concurrency | ❌ No constant |
| `vendors.py:110` | `"https://api.ppio.com/openai"` | PPIO base URL | ❌ No constant |
| `vendors.py:111` | `"qwen/qwen2.5-vl-72b-instruct"` | PPIO default model | ❌ No constant |
| `vendors.py:112` | `4096` | PPIO max tokens OCR | ❌ No constant |
| `vendors.py:113` | `3072` | PPIO max tokens refiner | ❌ No constant |
| `vendors.py:114` | `"/openai"` | PPIO paddle doc path | ❌ No constant |
| `vendors.py:118` | `"https://api.novita.ai/openai"` | Novita base URL | ❌ No constant |
| `vendors.py:119` | `"qwen/qwen2.5-vl-72b-instruct"` | Novita default model | ❌ No constant |
| `vendors.py:120` | `4096` | Novita max tokens OCR | ❌ No constant |
| `vendors.py:121` | `3072` | Novita max tokens refiner | ❌ No constant |
| `vendors.py:122` | `"/openai"` | Novita paddle doc path | ❌ No constant |
| `vendors.py:127` | `"https://api.deepseek.com/v1"` | DeepSeek base URL | ❌ No constant |
| `vendors.py:128` | `"deepseek-ai/DeepSeek-OCR"` | DeepSeek default model | ❌ No constant |
| `vendors.py:129` | `4096` | DeepSeek max tokens OCR | ❌ No constant |
| `vendors.py:130` | `2048` | DeepSeek max tokens refiner | ❌ No constant |
| `vendors.py:131` | `"/v1"` | DeepSeek paddle doc path | ❌ No constant |
| `vendors.py:358` | `256` | Min max_tokens clamp | ❌ No constant |

### 10. Hardcoded Strings in Base (`convert/ocr/base.py`)

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `base.py:23` | `"PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"` | Env var name | ❌ No constant |
| `base.py:75` | `"PaddlePaddle/PaddleOCR-VL"` | PaddleOCR VL model v1 | ❌ No constant |
| `base.py:76` | `"PaddlePaddle/PaddleOCR-VL-1.5"` | PaddleOCR VL model v1.5 | ❌ No constant |
| `base.py:78` | `"vllm-server"` | Default paddle doc backend | ❌ No constant |
| `base.py:124` | `"chi_sim+eng"` | Default Tesseract language | ❌ No constant |
| `base.py:138` | `"ch"` | Default PaddleOCR language | ❌ No constant |

### 11. Hardcoded Values in Layout Models (`convert/ocr/layout_models.py`)

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `layout_models.py:47` | `1.2` | PP-DocLayout-S size MB | ❌ No constant |
| `layout_models.py:58` | `23.0` | PP-DocLayout-M size MB | ❌ No constant |
| `layout_models.py:69` | `124.0` | PP-DocLayout-L size MB | ❌ No constant |
| `layout_models.py:80` | `126.0` | PP-DocLayoutV3 size MB | ❌ No constant |
| `layout_models.py:91` | `10.0` | DocLayout-YOLO size MB | ❌ No constant |
| `layout_models.py:184` | `"/app/data/models"` | Model cache directory | ✅ env `MODEL_CACHE_DIR` |
| `layout_models.py:204` | `1024` | DocLayout-YOLO image size | ❌ No constant |
| `layout_models.py:204` | `0.2` | DocLayout-YOLO confidence threshold | ❌ No constant |

### 12. Hardcoded Values in Perf Policies (`perf_policies.py`)

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `perf_policies.py:46` | `5` | Final preview max pages default | ❌ No constant |
| `perf_policies.py:87` | `200` | OCR render DPI default | ❌ No constant |
| `perf_policies.py:88` | `200` | Scanned render DPI default | ❌ No constant |
| `perf_policies.py:89` | `15.0` | Keepalive interval default | ❌ No constant |

### 13. Hardcoded Font Paths (`routers/jobs.py`)

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `jobs.py:304` | `"/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"` | CJK font path | ❌ No constant |
| `jobs.py:305` | `"/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"` | CJK font path (alt) | ❌ No constant |
| `jobs.py:306` | `"/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"` | CJK font path (alt2) | ❌ No constant |
| `jobs.py:311` | `"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"` | Latin font path | ❌ No constant |
| `jobs.py:312` | `"/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"` | Latin font path (alt) | ❌ No constant |

### 14. Hardcoded Redis Key Patterns

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `redis_service.py:133` | `"job:{job_id}"` | Job metadata key pattern | ❌ No constant |
| `redis_service.py:137` | `"job:{job_id}:cancel"` | Cancel flag key pattern | ❌ No constant |
| `redis_service.py:362` | `"job:{job_id}:secrets"` | Secrets key pattern | ❌ No constant |
| `redis_service.py:408` | `"job:*"` | Job key scan pattern | ❌ No constant |
| `redis_service.py:447` | `"rl:{client_ip}"` | Rate limit key pattern | ❌ No constant |
| `auth.py:44` | `"oauth_state:{state}"` | OAuth state key pattern | ❌ No constant |

### 15. Hardcoded API Paths and Skip Paths

| File:Line | Hardcoded Value | What It Represents | Existing Config? |
|---|---|---|---|
| `main.py:107` | `"/api/v1/auth/"`, `"/api/v1/admin/"`, `"/api/v1/setup/"` | Bearer skip paths | ❌ No constant |
| `main.py:130` | `"/health"` | Health check path | ❌ No constant |
| `routers/jobs.py:71` | `"/api/v1/jobs"` | Jobs router prefix | ❌ No constant |
| `routers/auth.py:40` | `"/api/v1/auth"` | Auth router prefix | ❌ No constant |

## Summary

### High Priority (Repeated Across Files)

1. **`0.85`** — Default confidence score used in PaddleOCR, Baidu OCR, and local providers (6+ locations)
2. **`50.0`** — Tesseract min confidence threshold (3 locations)
3. **`2200`** — Max side pixels for PaddleOCR (2 locations: worker.py, local_providers.py)
4. **`200`** — OCR/Scanned render DPI (4 locations: config.py, perf_policies.py)
5. **`10.0`** — HTTP client timeout (2 locations: auth.py)
6. **`60.0`** — Rate limiter window (2 locations: ai_client.py)

### Medium Priority (Single File, Multiple Uses)

1. **Image processing thresholds** — `0.03`, `0.18`, `0.05`, `0.94`, `0.97`, `0.90` in ai_client.py
2. **Noise detection thresholds** — `0.3`, `0.08`, `3` in local_providers.py
3. **Merge detection thresholds** — `0.18`, `2.9`, `0.22`, `3.2` in local_providers.py
4. **Color sampling thresholds** — `14.0`, `18.0`, `900.0`, `128.0` in local_providers.py
5. **Vendor config values** — URLs, model names, token limits in vendors.py

### Low Priority (Single Use, Well-Documented)

1. **Font paths** — System-specific, acceptable as hardcoded
2. **API paths** — Router prefixes, acceptable as hardcoded
3. **Redis key patterns** — Simple patterns, acceptable as hardcoded

## Caveats / Not Found

- Some values are already configurable via environment variables (marked with ✅)
- Some values are intentionally hardcoded as they represent physical constants (EMU_PER_INCH, luma coefficients)
- Some values are acceptable as hardcoded (font paths, API paths)
- The OCR pipeline has the most hardcoded values and would benefit most from extraction
