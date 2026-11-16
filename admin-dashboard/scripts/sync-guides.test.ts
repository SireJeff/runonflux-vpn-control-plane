import { describe, it, expect } from 'vitest'
import { buildModuleSource, checkInSync } from './sync-guides.mjs'

describe('sync-guides', () => {
  it('round-trips markdown through the generated module', () => {
    const md = '# Title\n\n```bash\necho `hi` ${x}\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n'
    const moduleSource = buildModuleSource(md)
    // Extract the default export payload and parse it back.
    const payload = moduleSource.slice(moduleSource.indexOf('export default ') + 'export default '.length).trimEnd()
    expect(JSON.parse(payload)).toBe(md)
  })

  it('checkInSync is true only for a matching module', () => {
    const md = '# Hello\n'
    expect(checkInSync(md, buildModuleSource(md))).toBe(true)
    expect(checkInSync(md, buildModuleSource('# Changed\n'))).toBe(false)
  })
})
