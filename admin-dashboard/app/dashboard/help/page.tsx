'use client'

import subadminGuide from '@/content/guides/subadmin-guide'
import { GuideRenderer } from '@/components/help/GuideRenderer'
import { GuideTableOfContents } from '@/components/help/GuideTableOfContents'

export default function DashboardHelpPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Help &amp; Runbook</h2>
        <p className="text-muted-foreground">Reseller operating guide.</p>
      </div>
      <div className="grid gap-8 lg:grid-cols-[240px_1fr]">
        <aside className="hidden lg:block">
          <GuideTableOfContents content={subadminGuide} />
        </aside>
        <GuideRenderer content={subadminGuide} />
      </div>
    </div>
  )
}
