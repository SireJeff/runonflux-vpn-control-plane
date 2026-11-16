import GithubSlugger from 'github-slugger'

export interface TocEntry {
  depth: 2 | 3
  text: string
  slug: string
}

export function parseToc(markdown: string): TocEntry[] {
  const slugger = new GithubSlugger()
  const entries: TocEntry[] = []
  let inFence = false

  for (const rawLine of markdown.split('\n')) {
    const line = rawLine.trimEnd()
    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence
      continue
    }
    if (inFence) continue

    const match = /^(#{2,3})\s+(.*)$/.exec(line)
    if (!match) continue
    const depth = match[1].length as 2 | 3
    const text = match[2].trim()
    entries.push({ depth, text, slug: slugger.slug(text) })
  }
  return entries
}
