/**
 * Unified layout model registry — shared model metadata for frontend.
 *
 * Mirrors the backend `api/app/convert/ocr/layout_models.py` registry.
 */

export interface LayoutModelInfo {
  modelId: string
  displayName: string
  provider: "paddlex" | "doclayout_yolo"
  sizeMb: number
  speedLabel: string
  accuracy: string
  description: string
  recommended: boolean
}

export const LAYOUT_MODELS: Record<string, LayoutModelInfo> = {
  pp_doclayout_s: {
    modelId: "pp_doclayout_s",
    displayName: "PP-DocLayout-S",
    provider: "paddlex",
    sizeMb: 1.2,
    speedLabel: "8ms GPU / 14ms CPU",
    accuracy: "70.9% mAP",
    description: "超轻量，适合 CPU 和边缘设备",
    recommended: false,
  },
  pp_doclayout_m: {
    modelId: "pp_doclayout_m",
    displayName: "PP-DocLayout-M",
    provider: "paddlex",
    sizeMb: 23,
    speedLabel: "13ms GPU / 43ms CPU",
    accuracy: "75.2% mAP",
    description: "均衡型，速度与精度兼顾",
    recommended: false,
  },
  pp_doclayout_l: {
    modelId: "pp_doclayout_l",
    displayName: "PP-DocLayout-L",
    provider: "paddlex",
    sizeMb: 124,
    speedLabel: "34ms GPU / 503ms CPU",
    accuracy: "90.4% mAP",
    description: "高精度，适合复杂版式文档",
    recommended: false,
  },
  pp_doclayout_v3: {
    modelId: "pp_doclayout_v3",
    displayName: "PP-DocLayoutV3",
    provider: "paddlex",
    sizeMb: 126,
    speedLabel: "24ms GPU",
    accuracy: "25 类 + 阅读序",
    description: "默认推荐，支持 25 类版面元素与阅读序",
    recommended: true,
  },
  doclayout_yolo: {
    modelId: "doclayout_yolo",
    displayName: "DocLayout-YOLO",
    provider: "doclayout_yolo",
    sizeMb: 10,
    speedLabel: "极快 (YOLO)",
    accuracy: "93.4% AP50 (DocLayNet)",
    description: "YOLO 架构，速度极快，通用文档适用",
    recommended: false,
  },
}

export const DEFAULT_LAYOUT_MODEL = "pp_doclayout_v3"

export const LAYOUT_MODEL_IDS = Object.keys(LAYOUT_MODELS)

/**
 * Normalize a layout model ID to canonical form.
 */
export function normalizeLayoutModelId(raw: string | null | undefined): string {
  const normalized = (raw ?? "").trim().toLowerCase()
  if (!normalized) return DEFAULT_LAYOUT_MODEL

  const aliases: Record<string, string> = {
    "pp-doclayoutv3": "pp_doclayout_v3",
    pp_doclayoutv3: "pp_doclayout_v3",
    pp_doclayout: "pp_doclayout_v3",
    "pp-doclayout-v3": "pp_doclayout_v3",
    "pp-doclayout-s": "pp_doclayout_s",
    pp_doclayouts: "pp_doclayout_s",
    "pp-doclayout-m": "pp_doclayout_m",
    pp_doclayoutm: "pp_doclayout_m",
    "pp-doclayout-l": "pp_doclayout_l",
    pp_doclayoutl: "pp_doclayout_l",
    "doclayout-yolo": "doclayout_yolo",
    doclayoutyolo: "doclayout_yolo",
  }

  if (aliases[normalized]) return aliases[normalized]
  if (LAYOUT_MODELS[normalized]) return normalized
  return DEFAULT_LAYOUT_MODEL
}
