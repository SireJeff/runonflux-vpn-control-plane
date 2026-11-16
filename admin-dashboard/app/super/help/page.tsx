'use client'

import superadminGuide from '@/content/guides/superadmin-guide'
import { GuideRenderer } from '@/components/help/GuideRenderer'
import { GuideTableOfContents } from '@/components/help/GuideTableOfContents'

export default function SuperHelpPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Help &amp; Runbook</h2>
        <p className="text-muted-foreground">Super-admin operating guide.</p>
      </div>
      <div className="grid gap-8 lg:grid-cols-[240px_1fr]">
        <aside className="hidden lg:block">
          <GuideTableOfContents content={superadminGuide} />
        </aside>
        <GuideRenderer content={superadminGuide} />
      </div>
    </div>
  )
}
