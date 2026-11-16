'use client'

/**
 * User-portal i18n — React Context edition.
 *
 * Previous version used `useState` directly inside `useI18n()`, which meant
 * every component calling the hook got its OWN state. Toggling language in
 * one place (LangToggle) didn't propagate to other consumers — they only
 * caught up after a page refresh forced remount.
 *
 * This module exposes:
 *   - <I18nProvider>  — mount once at the layout root (app/user/layout.tsx)
 *   - useI18n()       — read + update the shared language state
 *
 * The state persists to localStorage; on mount the provider hydrates from
 * there (or navigator.language, falling back to 'fa').
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import fa from './locales/user-portal/fa.json'
import en from './locales/user-portal/en.json'

export type Lang = 'fa' | 'en'

const messages: Record<Lang, Record<string, string>> = { fa, en }

const STORAGE_KEY = 'user_portal_lang'

interface I18nContextValue {
  lang: Lang
  setLang: (next: Lang) => void
  toggleLang: () => void
  t: (key: string) => string
}

const I18nContext = createContext<I18nContextValue | null>(null)

/**
 * Resolve initial language from (in order):
 *   1. localStorage (if set)
 *   2. navigator.language (browser preference, if it starts with fa/en)
 *   3. 'fa' default (Persian is the primary audience)
 *
 * Guarded for SSR — returns 'fa' on server, real value after hydration.
 */
function resolveInitialLang(): Lang {
  if (typeof window === 'undefined') return 'fa'
  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (stored === 'fa' || stored === 'en') return stored
  const nav = window.navigator.language?.toLowerCase() ?? ''
  if (nav.startsWith('fa')) return 'fa'
  if (nav.startsWith('en')) return 'en'
  return 'fa'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>('fa')

  // Hydrate from localStorage after mount (avoids SSR mismatch).
  useEffect(() => {
    setLangState(resolveInitialLang())
  }, [])

  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, next)
    }
  }, [])

  const toggleLang = useCallback(() => {
    setLangState((prev) => {
      const next = prev === 'fa' ? 'en' : 'fa'
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(STORAGE_KEY, next)
      }
      return next
    })
  }, [])

  const t = useCallback(
    (key: string): string => messages[lang]?.[key] ?? key,
    [lang]
  )

  return (
    <I18nContext.Provider value={{ lang, setLang, toggleLang, t }}>
      {children}
    </I18nContext.Provider>
  )
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext)
  if (!ctx) {
    throw new Error('useI18n must be used inside <I18nProvider>')
  }
  return ctx
}
