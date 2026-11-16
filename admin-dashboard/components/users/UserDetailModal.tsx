'use client'

import React from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { UserResponse } from '@/types/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  User,
  Mail,
  Wallet,
  Users,
  TrendingUp,
  Calendar,
  Shield,
  DollarSign,
  Pencil,
} from 'lucide-react'
import { formatCurrency, formatDate } from '@/lib/utils'

interface UserDetailModalProps {
  user: UserResponse | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onEdit?: (user: UserResponse) => void
}

export function UserDetailModal({
  user,
  open,
  onOpenChange,
  onEdit,
}: UserDetailModalProps) {
  if (!user) return null

  const tierColors = {
    bronze: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200',
    silver: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
    gold: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    platinum: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
  }

  const isTrialActive =
    user.trial_expires_at && new Date(user.trial_expires_at) > new Date()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh]">
        <DialogHeader>
          <div className="flex items-start justify-between">
            <div>
              <DialogTitle className="text-2xl">User Details</DialogTitle>
              <DialogDescription>
                Complete information for user #{user.id}
              </DialogDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onEdit?.(user)}
            >
              <Pencil className="mr-2 h-4 w-4" />
              Edit
            </Button>
          </div>
        </DialogHeader>

        <ScrollArea className="h-[calc(90vh-120px)] pr-4">
          <div className="space-y-6">
            {/* Basic Information */}
            <div>
              <h3 className="text-lg font-semibold mb-4">Basic Information</h3>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-primary/10 p-2">
                    <User className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Username</p>
                    <p className="font-medium">
                      {user.telegram_username || (
                        <span className="text-muted-foreground">No username</span>
                      )}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-primary/10 p-2">
                    <Mail className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Email</p>
                    <p className="font-medium">
                      {user.email || (
                        <span className="text-muted-foreground">No email</span>
                      )}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-primary/10 p-2">
                    <Calendar className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Joined</p>
                    <p className="font-medium">{formatDate(user.created_at ?? "")}</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-primary/10 p-2">
                    <Shield className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Admin Status</p>
                    <p className="font-medium">
                      {user.is_admin ? (
                        <Badge>Admin</Badge>
                      ) : (
                        <Badge variant="secondary">User</Badge>
                      )}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <Separator />

            {/* Wallet Information */}
            <div>
              <h3 className="text-lg font-semibold mb-4">Wallet & Billing</h3>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-green-100 dark:bg-green-900 p-2">
                    <DollarSign className="h-4 w-4 text-green-600 dark:text-green-400" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Wallet Balance</p>
                    <p className="text-2xl font-bold">
                      ${formatCurrency(parseFloat(user.wallet_balance ?? "0"))}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-primary/10 p-2">
                    <Wallet className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Flux Wallet</p>
                    <p className="font-mono text-xs break-all">
                      {user.flux_wallet_address || (
                        <span className="text-muted-foreground">Not connected</span>
                      )}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <Separator />

            {/* Referral Information */}
            <div>
              <h3 className="text-lg font-semibold mb-4">Referral Program</h3>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-primary/10 p-2">
                    <Users className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Total Referrals</p>
                    <p className="text-2xl font-bold">{user.total_referrals ?? 0}</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-primary/10 p-2">
                    <TrendingUp className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Referral Earnings</p>
                    <p className="text-2xl font-bold">
                      ${formatCurrency(parseFloat(user.referral_earnings_usd ?? "0"))}
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-primary/10 p-2">
                    <Badge className={tierColors[user.referral_tier ?? 'bronze']}>
                      {user.referral_tier?.toUpperCase() ?? 'BRONZE'}
                    </Badge>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Referral Tier</p>
                    <p className="font-medium capitalize">{user.referral_tier ?? 'bronze'}</p>
                  </div>
                </div>

                {user.referral_code && (
                  <div className="flex items-start gap-3">
                    <div className="rounded-full bg-primary/10 p-2">
                      <span className="text-xs font-mono">CODE</span>
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Referral Code</p>
                      <p className="font-mono font-bold">{user.referral_code}</p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <Separator />

            {/* Trial Information */}
            <div>
              <h3 className="text-lg font-semibold mb-4">Trial Status</h3>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-primary/10 p-2">
                    <Calendar className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Trial Used</p>
                    <p className="font-medium">
                      {user.trial_used ? (
                        <Badge variant="secondary">Yes</Badge>
                      ) : (
                        <Badge>Not Used</Badge>
                      )}
                    </p>
                  </div>
                </div>

                {user.trial_used && (
                  <>
                    <div className="flex items-start gap-3">
                      <div className="rounded-full bg-primary/10 p-2">
                        <Calendar className="h-4 w-4 text-primary" />
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Trial Started</p>
                        <p className="font-medium">
                          {user.trial_started_at
                            ? formatDate(user.trial_started_at ?? "")
                            : 'N/A'}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-start gap-3">
                      <div className="rounded-full bg-primary/10 p-2">
                        <Calendar className="h-4 w-4 text-primary" />
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Trial Expires</p>
                        <p className="font-medium">
                          {user.trial_expires_at
                            ? formatDate(user.trial_expires_at ?? "")
                            : 'N/A'}
                        </p>
                        {isTrialActive && (
                          <Badge className="mt-1" variant="default">
                            Active
                          </Badge>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            <Separator />

            {/* Additional Information */}
            <div>
              <h3 className="text-lg font-semibold mb-4">Additional Details</h3>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-primary/10 p-2">
                    <User className="h-4 w-4 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Telegram User ID</p>
                    <p className="font-mono">{user.telegram_user_id ?? 'N/A'}</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <div className="rounded-full bg-primary/10 p-2">
                    <span className="text-xs">🌐</span>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Language</p>
                    <p className="font-medium uppercase">{user.language ?? 'en'}</p>
                  </div>
                </div>

                {user.referred_by && (
                  <div className="flex items-start gap-3">
                    <div className="rounded-full bg-primary/10 p-2">
                      <Users className="h-4 w-4 text-primary" />
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Referred By</p>
                      <p className="font-medium">User #{user.referred_by}</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}
