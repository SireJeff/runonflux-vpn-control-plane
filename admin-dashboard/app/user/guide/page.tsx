'use client'

/**
 * /user/guide — single page with 3 platform sections (Android, iOS, Windows)
 * and anchor nav at top. Bilingual via useI18n().
 */

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { ArrowLeft } from 'lucide-react'
import { useI18n } from '@/lib/i18n/user-portal'
import { LangToggle } from '@/components/user/LangToggle'
import { GuideSection } from '@/components/user/GuideSection'
import { guides, platformMeta, type Platform } from '@/lib/content/guides'

const PLATFORMS: Platform[] = ['android', 'ios', 'windows']

export default function UserGuidePage() {
  const { t, lang } = useI18n()
  const content = guides[lang]

  return (
    <div className="space-y-6" dir={lang === 'fa' ? 'rtl' : 'ltr'}>
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{t('setup_guides_title')}</h2>
          <p className="text-muted-foreground text-sm">{t('copy_to_client')}</p>
        </div>
        <div className="flex items-center gap-2">
          <LangToggle />
          <Link href="/user/connections">
            <Button variant="outline" size="sm" className="gap-1.5">
              <ArrowLeft className="h-3.5 w-3.5" />
              {t('your_connections')}
            </Button>
          </Link>
        </div>
      </div>

      {/* Anchor nav */}
      <nav className="flex flex-wrap gap-2">
        {PLATFORMS.map((platform) => {
          const meta = platformMeta[platform]
          const name = lang === 'fa' ? meta.faName : meta.enName
          return (
            <a
              key={platform}
              href={`#${platform}`}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-3 py-1.5 text-sm hover:bg-accent transition-colors"
            >
              <span className="text-base">{meta.icon}</span>
              {name}
            </a>
          )
        })}
      </nav>

      {/* Sections */}
      <div className="space-y-4">
        {PLATFORMS.map((platform) => {
          const meta = platformMeta[platform]
          const name = lang === 'fa' ? meta.faName : meta.enName
          return (
            <GuideSection
              key={platform}
              id={platform}
              icon={meta.icon}
              title={name}
              content={content[platform]}
              labels={{
                recommended_clients: t('recommended_clients'),
                setup_steps: t('setup_steps'),
                common_issues: t('common_issues'),
                free: t('free'),
              }}
            />
          )
        })}
      </div>
    </div>
  )
}
