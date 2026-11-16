'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { HelpCircle } from 'lucide-react'
import { helpAnchorForPath } from '@/lib/content/help-map'
import { cn } from '@/lib/utils'

export function HelpButton() {
  const pathname = usePathname()
  const target = helpAnchorForPath(pathname)
  if (!target) return null

  return (
    <Link
      href={target.href}
      aria-label="Help for this page"
      title="Help for this page"
      className={cn(
        'inline-flex h-9 w-9 items-center justify-center rounded-md',
        'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
      )}
    >
      <HelpCircle className="h-5 w-5" />
    </Link>
  )
}
