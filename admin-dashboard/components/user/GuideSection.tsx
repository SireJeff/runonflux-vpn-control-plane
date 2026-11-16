'use client'

/**
 * Single platform section for /user/guide. Renders recommended clients,
 * setup steps, and troubleshooting notes.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ExternalLink } from 'lucide-react'
import type { GuideContent, Platform } from '@/lib/content/guides'

interface Props {
  id: Platform
  icon: string
  title: string
  content: GuideContent
  labels: {
    recommended_clients: string
    setup_steps: string
    common_issues: string
    free: string
  }
}

export function GuideSection({ id, icon, title, content, labels }: Props) {
  return (
    <Card id={id} className="scroll-mt-20">
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <span className="text-2xl">{icon}</span>
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Recommended clients */}
        <div>
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            {labels.recommended_clients}
          </h4>
          <div className="space-y-2">
            {content.recommendedClients.map((client) => (
              <a
                key={client.name}
                href={client.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-between rounded-md border border-border bg-muted/30 px-3 py-2 hover:bg-muted/60 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{client.name}</span>
                  {client.free && (
                    <span className="text-xs text-green-700 dark:text-green-400">
                      ({labels.free})
                    </span>
                  )}
                </div>
                <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
              </a>
            ))}
          </div>
        </div>

        {/* Setup steps */}
        <div>
          <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
            {labels.setup_steps}
          </h4>
          <ol className="space-y-1.5">
            {content.steps.map((step, i) => (
              <li key={i} className="flex gap-2 text-sm">
                <span className="font-mono text-xs bg-primary/10 text-primary rounded-full h-5 w-5 flex items-center justify-center shrink-0 mt-0.5">
                  {i + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </div>

        {/* Troubleshooting */}
        {content.troubleshooting.length > 0 && (
          <div>
            <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">
              {labels.common_issues}
            </h4>
            <ul className="space-y-1.5">
              {content.troubleshooting.map((note, i) => (
                <li key={i} className="flex gap-2 text-sm text-muted-foreground">
                  <span className="text-amber-500 shrink-0">⚠️</span>
                  <span>{note}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
