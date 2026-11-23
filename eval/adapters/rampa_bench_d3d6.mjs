// D3 and D6 in Rampa's harness (pinned df32363), AccessGraph row only; every other tool's results are reused from
// the harness's stored run (bench/results/2026-10-11, same pin and same ACT file).
//   node eval/adapters/rampa_bench_d3d6.mjs CONFIG_JSON          (written by eval/d3d6.py; --dry-run: no judging)
// CONFIG: { out, rules: [ACT rule ids], keep: [corruptor ids], port, workers, dryRun }
// Builds the pairs of the kept corruptors with the harness's own builder (bench/lib/pairs.mjs), serves them with its
// own server at a fixed port (stable page URLs, so cached verdicts are reused on re-runs), compares each saved half
// with the hash the stored run recorded, and runs bench/lib/drive.mjs for the `accessgraph` row on the ACT test
// cases of the chosen rules and on the kept pairs' pages.
import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { mkdir, writeFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

const BENCH = join(process.env.RAMPA_DIR || join(process.env.ACCESSGRAPH_EXTERNAL || join(homedir(), 'w4a-external'), 'rampa-cli'), 'bench')
const lib = (file) => import(pathToFileURL(join(BENCH, 'lib', file)).href)
const { pairSpecs } = await lib('cases.mjs')
const { buildPairs } = await lib('pairs.mjs')
const { startServer } = await lib('server.mjs')
const { CACHE } = await lib('env.mjs')

const config = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const stored = JSON.parse(readFileSync(join(BENCH, 'results', '2026-10-11', 'cases.json'), 'utf8'))
const storedPairs = JSON.parse(readFileSync(join(BENCH, 'results', '2026-10-11', 'pairs.json'), 'utf8'))
await mkdir(join(config.out, 'raw'), { recursive: true })

const served = new Map()
const server = await startServer({ port: config.port, served, cacheDir: join(CACHE, 'w3c') })
try {
  const { specs, corruptors } = await pairSpecs()
  const chosen = specs.filter((spec) => config.keep.includes(spec.corruptor))
  const built = await buildPairs(chosen, corruptors, { dir: join(config.out, 'pair-pages'), origin: server.origin })
  for (const [key, file] of built.served) served.set(key, file)
  const used = new Set(built.pairs.map((pair) => pair.intactId))
  const pairPages = built.pages.filter((page) => page.kind !== 'pair-intact' || used.has(page.id))
  const storedSha = new Map(storedPairs.pages.map((page) => [page.id, page.sha]))
  const differs = pairPages.filter((page) => storedSha.get(page.id) !== page.sha).map((page) => page.id)
  const actPages = stored.cases.filter((c) => config.rules.includes(c.ruleId)).map((c) => ({ id: c.id, url: c.url, kind: 'act' }))
  const only = config.only ? new Set(config.only) : null
  const pages = [...actPages, ...pairPages.map(({ id, url, kind }) => ({ id, url, kind }))].filter((page) => !only || only.has(page.id))
  await writeFile(join(config.out, 'pages.json'), JSON.stringify(pages, null, 1))
  await writeFile(join(config.out, 'pairs.json'), JSON.stringify({ pairs: built.pairs, dropped: built.dropped, notes: built.notes, pages: pairPages, differsFromStoredRun: differs }, null, 1))
  process.stderr.write(`ACT pages ${actPages.length}, pairs ${built.pairs.length} (${built.dropped.length} dropped), pair pages ${pairPages.length}, pages differing from the stored run ${differs.length}\n`)
  if (!config.dryRun) {
    const code = await new Promise((resolveRun) => {
      const child = spawn(process.execPath, ['lib/drive.mjs', 'accessgraph', '--pages', join(config.out, 'pages.json'), '--out', join(config.out, 'raw', 'accessgraph.jsonl'), '--meta', join(config.out, 'raw', 'accessgraph.meta.json'), '--workers', String(config.workers)], { cwd: BENCH, stdio: ['ignore', 'inherit', 'inherit'] })
      child.on('close', resolveRun)
    })
    process.stderr.write(`accessgraph row exited with ${code}\n`)
  }
} finally {
  await server.close()
}
