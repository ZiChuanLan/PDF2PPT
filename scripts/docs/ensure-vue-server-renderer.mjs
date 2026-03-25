import { existsSync, mkdirSync, writeFileSync } from "node:fs"
import { join } from "node:path"

const rendererRoot = join(process.cwd(), "node_modules", "@vue", "server-renderer")
const distDir = join(rendererRoot, "dist")
const indexFile = join(rendererRoot, "index.js")
const devCjsFile = join(distDir, "server-renderer.cjs.js")
const prodCjsFile = join(distDir, "server-renderer.cjs.prod.js")

if (!existsSync(rendererRoot) || !existsSync(prodCjsFile)) {
  process.exit(0)
}

mkdirSync(distDir, { recursive: true })

writeFileSync(
  devCjsFile,
  "module.exports = require('./server-renderer.cjs.prod.js')\n",
  "utf8",
)

writeFileSync(
  indexFile,
  [
    "'use strict'",
    "",
    "if (process.env.NODE_ENV === 'production') {",
    "  module.exports = require('./dist/server-renderer.cjs.prod.js')",
    "} else {",
    "  module.exports = require('./dist/server-renderer.cjs.js')",
    "}",
    "",
  ].join("\n"),
  "utf8",
)
