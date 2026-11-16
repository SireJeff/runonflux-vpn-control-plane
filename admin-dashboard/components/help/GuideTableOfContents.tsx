'use client'

import { useMemo, useState } from 'react'
import { parseToc } from '@/lib/help/toc'
import { cn } from '@/lib/utils'

interface GuideTableOfContentsProps {
  content: string
}

export function GuideTableOfContents({ content }: GuideTableOfContentsProps) {
  const [filter, setFilter] = useState('')
  const entries = useMemo(() => parseToc(content), [content])
  const needle = filter.trim().toLowerCase()
  const visible = needle
    ? entries.filter((e) => e.text.toLowerCase().includes(needle))
    : entries

  return (
    <nav aria-label="Table of contents" className="sticky top-6 space-y-2 text-sm">
      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter sections…"
        aria-label="Filter sections"
        className="w-full rounded-md border bg-background px-3 py-1.5 text-sm"
      />
      <ul className="space-y-1">
        {visible.map((entry) => (
          <li key={entry.slug}>
            <a
              href={`#${entry.slug}`}
              className={cn(
                'block rounded px-2 py-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground',
                entry.depth === 3 && 'pl-5 text-xs',
              )}
            >
              {entry.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}
