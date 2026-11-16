'use client'

/**
 * Top-of-page hero block for /user/connections.
 *
 * Subscription-link-centric: shows sub URL (with copy + format toggle for
 * sing-box), portal URL + login creds (decrypted from password_enc), and
 * Reset Password button that calls POST /user/reset-credentials.
 */

import { useState } from 'react'
import { Copy, Check, RefreshCw, ExternalLink, KeyRound, Link2, User } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import toast from 'react-hot-toast'

interface Props {
  subUrl?: string
  username?: string
  password?: string
  dashboardUrl?: string
  expiresAt?: string
  onReset: () => void
  resetting: boolean
  labels: {
    subscription_link: string
    subscription_link_help: string
    singbox_link: string
    singbox_link_help: string
    user_portal: string
    portal_address: string
    username: string
    password: string
    reset_password: string
    reset_password_confirm: string
    expires_on: string
    days_left: string
    copied: string
  }
}

function CopyableRow({
  label,
  value,
  copiedLabel,
}: {
  label: string
  value: string
  copiedLabel: string
}) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // ignore
    }
  }
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={handleCopy}
          aria-label={`${copiedLabel} ${label}`}
        >
          {copied ? (
            <Check className="h-3 w-3 text-green-600" />
          ) : (
            <Copy className="h-3 w-3" />
          )}
        </Button>
      </div>
      <code className="block w-full rounded-md bg-muted px-3 py-2 text-xs font-mono break-all leading-relaxed select-all">
        {value}
      </code>
    </div>
  )
}

export function SubscriptionHero({
  subUrl,
  username,
  password,
  dashboardUrl,
  expiresAt,
  onReset,
  resetting,
  labels,
}: Props) {
  const handleReset = () => {
    if (!window.confirm(labels.reset_password_confirm)) return
    onReset()
  }

  if (!subUrl) return null

  const daysLeft = expiresAt
    ? Math.max(0, Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 86400000))
    : null

  return (
    <Card className="border-dashed border-primary/40 bg-primary/5">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Link2 className="h-4 w-4 text-primary" />
            {labels.subscription_link}
          </CardTitle>
          <Button
            variant="outline"
            size="sm"
            className="h-7 gap-1.5 text-xs"
            onClick={handleReset}
            disabled={resetting}
          >
            <RefreshCw className={`h-3 w-3 ${resetting ? 'animate-spin' : ''}`} />
            {labels.reset_password}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="pt-0 space-y-3">
        {/* Standard sub link */}
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-1">
            {labels.subscription_link_help}
          </div>
          <CopyableRow label={labels.subscription_link} value={subUrl} copiedLabel={labels.copied} />
        </div>

        {/* Sing-box sub link */}
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-1">
            {labels.singbox_link_help}
          </div>
          <CopyableRow
            label={labels.singbox_link}
            value={`${subUrl}?format=singbox`}
            copiedLabel={labels.copied}
          />
        </div>

        {/* Portal login */}
        {dashboardUrl && (
          <div className="pt-2 border-t border-border">
            <div className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-2">
              <ExternalLink className="h-3.5 w-3.5" />
              {labels.user_portal}
            </div>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">{labels.portal_address}:</span>
                <a
                  href={dashboardUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-mono text-primary hover:underline"
                >
                  {dashboardUrl}
                </a>
              </div>
              {username && (
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground flex items-center gap-1">
                    <User className="h-3 w-3" />
                    {labels.username}:
                  </span>
                  <code className="font-mono select-all">{username}</code>
                </div>
              )}
              {password && (
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground flex items-center gap-1">
                    <KeyRound className="h-3 w-3" />
                    {labels.password}:
                  </span>
                  <code className="font-mono select-all">{password}</code>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Expiry */}
        {expiresAt && daysLeft !== null && (
          <div className="text-xs text-muted-foreground pt-2 border-t border-border">
            {labels.expires_on}: {new Date(expiresAt).toLocaleDateString()} ({daysLeft} {labels.days_left})
          </div>
        )}
      </CardContent>
    </Card>
  )
}
