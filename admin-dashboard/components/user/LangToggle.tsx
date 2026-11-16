'use client'

/**
 * Small language toggle for /user/* pages. Renders "FA | EN" — click either
 * to switch. Persists to localStorage via useI18n().
 */

import { Button } from '@/components/ui/button'
import { useI18n, type Lang } from '@/lib/i18n/user-portal'

export function LangToggle() {
  const { lang, setLang } = useI18n()
  const options: Lang[] = ['fa', 'en']

  return (
    <div className="flex items-center gap-1 rounded-md border border-border bg-background px-1 py-0.5 text-xs font-medium">
      {options.map((opt) => (
        <Button
          key={opt}
          variant={lang === opt ? 'default' : 'ghost'}
          size="sm"
          className="h-6 px-2 text-xs"
          onClick={() => setLang(opt)}
        >
          {opt.toUpperCase()}
        </Button>
      ))}
    </div>
  )
}
