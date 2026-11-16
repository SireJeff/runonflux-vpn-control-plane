'use client'

import { useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSlug from 'rehype-slug'

interface GuideRendererProps {
  content: string
}

export function GuideRenderer({ content }: GuideRendererProps) {
  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, '')
    if (!hash) return
    const el = document.getElementById(hash)
    el?.scrollIntoView?.()
  }, [content])

  return (
    <article className="prose prose-sm dark:prose-invert max-w-none">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSlug]}>
        {content}
      </ReactMarkdown>
    </article>
  )
}
