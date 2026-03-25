# OCR and Parsing Pipelines

## Parse Engine

| Mode | Meaning | Best for |
| --- | --- | --- |
| `local_ocr` | Parse PDF locally, then run OCR as needed | General default mode |
| `remote_ocr` | Remote OCR-first pipeline | OCR-quality-first scenarios |
| `baidu_doc` | Baidu document parsing pipeline | Structured parsing |
| `mineru_cloud` | MinerU cloud parsing pipeline | Tables, formulas, and complex layouts |

## OCR Provider

| Provider | Meaning | Notes |
| --- | --- | --- |
| `aiocr` | Remote OpenAI-compatible OCR | Good for higher-quality OCR |
| `tesseract` | Local Tesseract | Fewer external dependencies |
| `paddle_local` | Local PaddleOCR | Fully local setup |
| `baidu` | Baidu OCR | Standalone provider |

## AIOCR Chain

| Mode | Meaning | Characteristic |
| --- | --- | --- |
| `direct` | Send the whole page directly to a vision model | Simplest setup |
| `layout_block` | Split into local blocks, then recognize block by block | Better for dense mixed layouts |
| `doc_parser` | Structured document parsing channel | Better structural information |

## Scanned Page Mode

| Mode | Meaning | Result |
| --- | --- | --- |
| `fullpage` | Keep the page as a background and overlay editable text | Safest and closest to the original |
| `segmented` | Split charts, screenshots, and other image regions into separate objects when possible | More editable afterwards |

## Recommended Starting Configuration

For the highest chance of a stable first run, start with:

- `remote_ocr`
- `aiocr`
- `fullpage`

Then adjust based on your needs:

- try `segmented` when you want more editable image regions
- try `baidu_doc` or `mineru_cloud` when structural parsing matters more

## Boundaries

This project is better understood as a high-fidelity reconstruction tool for scanned and image-heavy documents. It should not be interpreted as:

- a guarantee that any PDF becomes a fully structured, fully editable native PPT
- a promise that complex documents work well without OCR or parsing configuration
- a system where every page becomes easier to edit than the original source
