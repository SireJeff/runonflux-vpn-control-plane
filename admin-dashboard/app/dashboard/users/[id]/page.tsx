'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatDate, formatTraffic, getStatusColor } from '@/lib/utils'
import { useRouter } from 'next/navigation'
import {
  ArrowLeft,
  Edit3,
  Check,
  X,
  Copy,
  Link as LinkIcon,
  Loader2,
} from 'lucide-react'
import Link from 'next/link'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import toast from 'react-hot-toast'

const MACRO_REGIONS: Record<string, { name: string; flag: string; countries: string[] }> = {
  eu: { name: "Europe", flag: "\u{1F1EA}\u{1F1FA}", countries: ["NL","CH","DE","FR","GB","PL","SE","FI","NO","DK","IT","ES","PT","IE","AT","BE","LU","CZ","RO","BG","HU","UA","RS","HR","SK","SI","LT","LV","EE","GR"] },
  as: { name: "Asia", flag: "\u{1F30F}", countries: ["SG","JP","HK","KR","IN","AE","TR","TH","MY","PH","ID","VN","TW","IL","SA","QA","KW","BH","OM","PK","BD","LK","MM","KH","LA"] },
  na: { name: "North America", flag: "\u{1F30E}", countries: ["US","CA","MX"] },
  row: { name: "Rest of World", flag: "\u{1F30D}", countries: ["BR","AR","CL","CO","PE","AU","NZ","ZA","NG","EG","KE","GH","MA","TN"] },
}

export default function UserDetailPage({ params }: { params: { id: string } }) {
  const userId = parseInt(params.id, 10)
  const router = useRouter()
  const queryClient = useQueryClient()

  // Edit state
  const [isEditing, setIsEditing] = useState(false)
  const [editDisplayName, setEditDisplayName] = useState('')
  const [editRemark, setEditRemark] = useState('')
  const [editTrafficLimit, setEditTrafficLimit] = useState('')

  // Password reset state
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false)
  const [newPassword, setNewPassword] = useState('')
  const [revealedPassword, setRevealedPassword] = useState('')

  // Renewal & adjustments state
  const [extendDays, setExtendDays] = useState('')
  const [topupGb, setTopupGb] = useState('')
  const [setDate, setSetDate] = useState('')
  const [selectedRegions, setSelectedRegions] = useState<string[]>([])

  // New user-management state
  const [renameOpen, setRenameOpen] = useState(false)
  const [newUsername, setNewUsername] = useState('')
  const [renameNotice, setRenameNotice] = useState(false)
  const [tgId, setTgId] = useState('')
  const [tgChatId, setTgChatId] = useState('')
  const [absLimit, setAbsLimit] = useState('')
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState('')

  // Fetch user detail
  const { data: user, isLoading } = useQuery({
    queryKey: ['admin', 'user', userId],
    queryFn: () => api.adminNew.getUser(userId),
    enabled: !isNaN(userId),
    refetchInterval: 30000,
  })

  const { data: availableRegions } = useQuery({
    queryKey: ['available-regions'],
    queryFn: () => api.adminNew.getAvailableRegions(),
  })

  useEffect(() => {
    if (user?.macro_regions) setSelectedRegions(user.macro_regions)
  }, [user?.macro_regions])

  useEffect(() => {
    setTgId(user?.telegram_id != null ? String(user.telegram_id) : '')
    setTgChatId(user?.telegram_chat_id != null ? String(user.telegram_chat_id) : '')
  }, [user?.telegram_id, user?.telegram_chat_id])

  const toggleRegion = (code: string) =>
    setSelectedRegions((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    )

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: { display_name?: string; remark?: string; traffic_limit_gb?: number | null }) =>
      api.adminNew.updateUser(userId, data),
    onSuccess: () => {
      toast.success('User updated')
      setIsEditing(false)
      queryClient.invalidateQueries({ queryKey: ['admin', 'user', userId] })
    },
    onError: () => {
      toast.error('Failed to update user')
    },
  })

  // Password reset mutation
  const passwordMutation = useMutation({
    mutationFn: (password: string) =>
      api.adminNew.updateUser(userId, { new_password: password }),
    onSuccess: () => {
      toast.success('Password reset')
      setPasswordDialogOpen(false)
      setRevealedPassword(newPassword)
      // Reveal the password in a separate dialog-like state
      queryClient.invalidateQueries({ queryKey: ['admin', 'user', userId] })
    },
    onError: () => {
      toast.error('Failed to reset password')
    },
  })

  const renewMutation = useMutation({
    mutationFn: (payload: {
      extend_days?: number; topup_gb?: number; set_expiry?: string; reapply_package_id?: number
      set_traffic_limit_gb?: number; set_unlimited?: boolean; reason?: string
    }) => api.adminNew.renewUser(userId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'user', userId] })
      toast.success('Subscription updated')
    },
    onError: () => toast.error('Update failed'),
  })

  const regionsMutation = useMutation({
    mutationFn: (macro_regions: string[]) => api.adminNew.setUserRegions(userId, { macro_regions }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'user', userId] })
      toast.success('Regions updated')
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'Region update failed'),
  })

  const renameMutation = useMutation({
    mutationFn: (name: string) => api.adminNew.setUsername(userId, { new_username: name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'user', userId] })
      setRenameOpen(false); setRenameNotice(true); toast.success('Username changed')
    },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'Rename failed'),
  })

  const telegramMutation = useMutation({
    mutationFn: (p: { telegram_id: number | null; telegram_chat_id: number | null }) =>
      api.adminNew.setTelegram(userId, p),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin', 'user', userId] }); toast.success('Telegram updated') },
    onError: (e: any) => toast.error(e?.response?.data?.detail ?? 'Telegram update failed'),
  })

  const parseTelegramField = (value: string): number | null | undefined => {
    const trimmed = value.trim()
    if (trimmed === '') return null
    if (!/^\d+$/.test(trimmed)) return undefined
    return Number(trimmed)
  }

  const handleSaveTelegram = () => {
    const parsedId = parseTelegramField(tgId)
    const parsedChatId = parseTelegramField(tgChatId)
    if (parsedId === undefined || parsedChatId === undefined) {
      toast.error('Telegram ID and Chat ID must be numeric')
      return
    }
    telegramMutation.mutate({ telegram_id: parsedId, telegram_chat_id: parsedChatId })
  }

  const resetTrafficMutation = useMutation({
    mutationFn: () => api.adminNew.resetTraffic(userId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin', 'user', userId] }); toast.success('Used traffic reset') },
    onError: () => toast.error('Reset failed'),
  })

  const statusMutation = useMutation({
    mutationFn: () => api.adminNew.toggleUser(userId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['admin', 'user', userId] }); toast.success('Status changed') },
    onError: () => toast.error('Status change failed'),
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.adminNew.deleteUser(userId),
    onSuccess: () => { toast.success('User deleted'); router.push('/dashboard/users') },
    onError: () => toast.error('Delete failed'),
  })

  const startEdit = () => {
    if (user) {
      setEditDisplayName(user.display_name || '')
      setEditRemark(user.remark || '')
      setEditTrafficLimit(user.traffic_limit_gb != null ? String(user.traffic_limit_gb) : '')
      setIsEditing(true)
    }
  }

  const handleSaveEdit = () => {
    const data: { display_name?: string; remark?: string; traffic_limit_gb?: number | null } = {}
    if (editDisplayName) data.display_name = editDisplayName
    if (editRemark) data.remark = editRemark
    if (editTrafficLimit === '') {
      data.traffic_limit_gb = null // unlimited
    } else {
      const val = parseFloat(editTrafficLimit)
      if (!isNaN(val) && val > 0) data.traffic_limit_gb = val
    }
    updateMutation.mutate(data)
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
        <Skeleton className="h-48" />
      </div>
    )
  }

  if (!user) {
    return (
      <div className="text-center py-20">
        <p className="text-muted-foreground">User not found</p>
        <Button variant="outline" className="mt-4" onClick={() => router.push('/dashboard/users')}>
          Back to Users
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Back button + Header */}
      <div className="flex items-center gap-4">
        <Link href="/dashboard/users">
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{user.username}</h2>
          <p className="text-muted-foreground">User details and management</p>
        </div>
        <Badge className={`ml-auto ${getStatusColor(user.status)}`}>{user.status}</Badge>
      </div>

      {/* Top row: Info + Actions */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* User Info Card */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">User Information</CardTitle>
            {!isEditing ? (
              <Button variant="outline" size="sm" onClick={startEdit}>
                <Edit3 className="mr-1 h-3 w-3" />
                Edit
              </Button>
            ) : (
              <div className="flex gap-1">
                <Button variant="outline" size="sm" onClick={handleSaveEdit} disabled={updateMutation.isPending}>
                  {updateMutation.isPending ? (
                    <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                  ) : (
                    <Check className="mr-1 h-3 w-3" />
                  )}
                  Save
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setIsEditing(false)}>
                  <X className="mr-1 h-3 w-3" />
                  Cancel
                </Button>
              </div>
            )}
          </CardHeader>
          <CardContent>
            <dl className="space-y-3">
              <div className="flex justify-between items-center">
                <dt className="text-sm text-muted-foreground">Username</dt>
                <dd className="text-sm font-medium flex items-center gap-2">
                  {user.username}
                  <Button variant="outline" size="sm" className="h-6 px-2"
                    onClick={() => { setNewUsername(user.username); setRenameOpen(true) }}>
                    Rename
                  </Button>
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-muted-foreground">Display Name</dt>
                {isEditing ? (
                  <Input
                    value={editDisplayName}
                    onChange={(e) => setEditDisplayName(e.target.value)}
                    className="h-8 w-48 text-sm"
                  />
                ) : (
                  <dd className="text-sm font-medium">{user.display_name || '-'}</dd>
                )}
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-muted-foreground">Remark</dt>
                {isEditing ? (
                  <Input
                    value={editRemark}
                    onChange={(e) => setEditRemark(e.target.value)}
                    className="h-8 w-48 text-sm"
                  />
                ) : (
                  <dd className="text-sm font-medium text-muted-foreground">
                    {user.remark || '-'}
                  </dd>
                )}
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-muted-foreground">Traffic Limit</dt>
                {isEditing ? (
                  <div className="flex items-center gap-1">
                    <Input
                      type="number"
                      step="0.1"
                      min="0"
                      placeholder="Unlimited"
                      value={editTrafficLimit}
                      onChange={(e) => setEditTrafficLimit(e.target.value)}
                      className="h-8 w-28 text-sm"
                    />
                    <span className="text-xs text-muted-foreground">GB</span>
                  </div>
                ) : (
                  <dd className="text-sm font-medium">
                    {user.traffic_limit_gb ? formatTraffic(user.traffic_limit_gb) : 'Unlimited'}
                  </dd>
                )}
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-muted-foreground">Status</dt>
                <dd>
                  <Badge className={getStatusColor(user.status)}>{user.status}</Badge>
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-sm text-muted-foreground">Traffic Used</dt>
                <dd className="text-sm font-medium">
                  {formatTraffic(user.traffic_used_gb || 0)}
                  {user.traffic_limit_gb && (
                    <span className="text-muted-foreground"> / {formatTraffic(user.traffic_limit_gb)}</span>
                  )}
                </dd>
              </div>
              {user.traffic_limit_gb && user.traffic_limit_gb > 0 && (
                <div className="col-span-2">
                  <div className="h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        (user.traffic_used_gb || 0) / user.traffic_limit_gb > 0.9
                          ? 'bg-red-500'
                          : (user.traffic_used_gb || 0) / user.traffic_limit_gb > 0.7
                            ? 'bg-yellow-500'
                            : 'bg-primary'
                      }`}
                      style={{ width: `${Math.min((user.traffic_used_gb || 0) / user.traffic_limit_gb * 100, 100)}%` }}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {((user.traffic_used_gb || 0) / user.traffic_limit_gb * 100).toFixed(1)}% used
                  </p>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-sm text-muted-foreground">Created</dt>
                <dd className="text-sm font-medium">
                  {user.created_at ? formatDate(user.created_at, true) : '-'}
                </dd>
              </div>
            </dl>

            <div className="border-t mt-4 pt-4">
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={() => {
                  setNewPassword('')
                  setPasswordDialogOpen(true)
                }}
              >
                Reset Password
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Region Info Card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Region</CardTitle>
          </CardHeader>
          <CardContent>
            {user.macro_region ? (
              <div className="flex items-center gap-3">
                <span className="text-3xl">
                  {MACRO_REGIONS[user.macro_region]?.flag || '\u{1F30D}'}
                </span>
                <div>
                  <div className="font-medium">
                    {MACRO_REGIONS[user.macro_region]?.name || user.macro_region}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {MACRO_REGIONS[user.macro_region]?.countries.length || 0} countries
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-muted-foreground">No region assigned</p>
            )}

            <div className="border-t mt-4 pt-4">
              <Link href={`/dashboard/users/${userId}/connections`}>
                <Button variant="outline" size="sm" className="w-full gap-2">
                  <Copy className="h-3 w-3" />
                  View Connection Strings
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Subscription Link Card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Subscription Links</CardTitle>
          </CardHeader>
          <CardContent>
            {user.subscription_url ? (
              <div className="space-y-3">
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-1">
                    Standard (v2rayNG, V2Box, NetMod) — SS, VLESS, Trojan
                  </p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 text-xs bg-muted p-2 rounded break-all">
                      {user.subscription_url}
                    </code>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        navigator.clipboard.writeText(user.subscription_url!)
                        toast.success('Standard link copied')
                      }}
                    >
                      <Copy className="mr-1 h-3 w-3" />
                      Copy
                    </Button>
                  </div>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-1">
                    Sing-box (Throne, Hiddify) — All 6 protocols incl. SSH, HTTP
                  </p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 text-xs bg-muted p-2 rounded break-all">
                      {user.subscription_url}?format=singbox
                    </code>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        navigator.clipboard.writeText(`${user.subscription_url}?format=singbox`)
                        toast.success('Sing-box link copied')
                      }}
                    >
                      <Copy className="mr-1 h-3 w-3" />
                      Copy
                    </Button>
                  </div>
                </div>
                {user.expires_at && (
                  <p className="text-xs text-muted-foreground">
                    Expires: {new Date(user.expires_at).toLocaleDateString()}
                  </p>
                )}
                <Button
                  variant="destructive"
                  size="sm"
                  className="w-full"
                  onClick={async () => {
                    if (!confirm('Regenerate subscription link? The old link will stop working immediately.')) return
                    try {
                      await api.adminNew.regenerateSubToken(userId)
                      queryClient.invalidateQueries({ queryKey: ['admin', 'user', userId] })
                      toast.success('Subscription link regenerated')
                    } catch {
                      toast.error('Failed to regenerate link')
                    }
                  }}
                >
                  Regenerate Link
                </Button>
              </div>
            ) : (
              <p className="text-muted-foreground">No subscription link available</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Renewal & Adjustments */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Renewal & Adjustments</CardTitle>
          <CardDescription>Extend, top up, or re-region this subscription. All changes are logged.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label>Extend (days)</Label>
              <div className="flex gap-2">
                <Input type="number" min={1} value={extendDays} onChange={(e) => setExtendDays(e.target.value)} />
                <Button size="sm" disabled={!extendDays}
                  onClick={() => renewMutation.mutate({ extend_days: Number(extendDays) })}>Apply</Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Top-up (GB)</Label>
              <div className="flex gap-2">
                <Input type="number" min={0.1} step={0.1} value={topupGb} onChange={(e) => setTopupGb(e.target.value)} />
                <Button size="sm" disabled={!topupGb}
                  onClick={() => renewMutation.mutate({ topup_gb: Number(topupGb) })}>Apply</Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Set expiry date</Label>
              <div className="flex gap-2">
                <Input type="date" value={setDate} onChange={(e) => setSetDate(e.target.value)} />
                <Button size="sm" disabled={!setDate}
                  onClick={() => renewMutation.mutate({ set_expiry: new Date(setDate).toISOString() })}>Apply</Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Set limit (GB, absolute)</Label>
              <div className="flex gap-2">
                <Input type="number" min={0} step={0.1} placeholder="blank = unlimited"
                  value={absLimit} onChange={(e) => setAbsLimit(e.target.value)} />
                <Button size="sm" onClick={() =>
                  renewMutation.mutate(absLimit === ''
                    ? { set_unlimited: true }
                    : { set_traffic_limit_gb: Number(absLimit) })}>Set</Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Used traffic</Label>
              <Button size="sm" variant="outline" disabled={resetTrafficMutation.isPending}
                onClick={() => { if (confirm('Reset used traffic to 0?')) resetTrafficMutation.mutate() }}>
                Reset used to 0
              </Button>
            </div>
          </div>

          <div className="space-y-2">
            <Label>Regions</Label>
            <div className="flex flex-wrap gap-3">
              {availableRegions?.map((r) => (
                <label key={r.code} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={selectedRegions.includes(r.code)}
                    onChange={() => toggleRegion(r.code)} />
                  {r.flag} {r.name}
                </label>
              ))}
            </div>
            <Button size="sm" onClick={() => regionsMutation.mutate(selectedRegions)}
              disabled={selectedRegions.length === 0}>Save regions</Button>
          </div>

          <div className="space-y-1 max-h-64 overflow-y-auto">
            <Label>History</Label>
            {(user.adjustments ?? []).map((a) => (
              <div key={a.id} className="text-xs text-muted-foreground border-b py-1">
                <span className="font-mono">{new Date(a.created_at).toLocaleString()}</span>
                {' — '}{a.action}{a.reason ? ` (${a.reason})` : ''}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Telegram</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Telegram ID</Label>
              <Input inputMode="numeric" value={tgId} onChange={(e) => setTgId(e.target.value)} placeholder="empty = detach" />
            </div>
            <div className="space-y-1">
              <Label>Telegram Chat ID</Label>
              <Input inputMode="numeric" value={tgChatId} onChange={(e) => setTgChatId(e.target.value)} />
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleSaveTelegram}>Save Telegram</Button>
            <Button size="sm" variant="outline"
              onClick={() => telegramMutation.mutate({ telegram_id: null, telegram_chat_id: null })}>
              Detach
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Status</CardTitle></CardHeader>
        <CardContent>
          <Button size="sm" variant="outline" onClick={() => statusMutation.mutate()}>
            {user.status === 'active' ? 'Suspend user' : 'Activate user'}
          </Button>
        </CardContent>
      </Card>

      <Card className="border-red-300">
        <CardHeader><CardTitle className="text-base text-red-600">Danger Zone</CardTitle></CardHeader>
        <CardContent>
          <Button variant="destructive" size="sm" onClick={() => { setDeleteConfirm(''); setDeleteOpen(true) }}>
            Delete user permanently
          </Button>
        </CardContent>
      </Card>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {user.username}?</DialogTitle>
            <DialogDescription>
              This permanently deletes the user, credentials, and traffic logs. Type the username to confirm.
            </DialogDescription>
          </DialogHeader>
          <Input value={deleteConfirm} onChange={(e) => setDeleteConfirm(e.target.value)} placeholder={user.username} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>Cancel</Button>
            <Button variant="destructive" disabled={deleteConfirm !== user.username || deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename user</DialogTitle>
            <DialogDescription>
              Changing the username re-provisions VPN credentials. The user must be re-sent their
              connection strings and portal login. The subscription link stays the same.
            </DialogDescription>
          </DialogHeader>
          <Input value={newUsername} onChange={(e) => setNewUsername(e.target.value)}
            placeholder="a-z A-Z 0-9 _ (3-50)" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameOpen(false)}>Cancel</Button>
            <Button disabled={renameMutation.isPending || !/^[a-zA-Z0-9_]{3,50}$/.test(newUsername)}
              onClick={() => renameMutation.mutate(newUsername)}>Rename</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={renameNotice} onOpenChange={setRenameNotice}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Username changed</DialogTitle>
            <DialogDescription>
              Re-send this user their connection strings and new portal login — their old ssh/http
              strings and portal username no longer work. Use the Connection Strings page.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter><Button onClick={() => setRenameNotice(false)}>Got it</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Password Reset Dialog */}
      <Dialog open={passwordDialogOpen} onOpenChange={setPasswordDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset Password</DialogTitle>
            <DialogDescription>
              Set a new password for user &quot;{user.username}&quot;.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new-password">New Password</Label>
              <Input
                id="new-password"
                type="text"
                placeholder="Enter new password (min 8 characters)"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPasswordDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => passwordMutation.mutate(newPassword)}
              disabled={newPassword.length < 8 || passwordMutation.isPending}
            >
              {passwordMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Reset Password
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Password Revealed Dialog (shows after reset) */}
      <Dialog
        open={!!revealedPassword && !passwordDialogOpen}
        onOpenChange={(open) => {
          if (!open) setRevealedPassword('')
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Password Reset Successfully</DialogTitle>
            <DialogDescription>Copy the new password below.</DialogDescription>
          </DialogHeader>
          <div className="flex items-center gap-2">
            <code className="flex-1 rounded-md bg-muted px-3 py-2 text-sm font-mono break-all">
              {revealedPassword}
            </code>
            <Button
              variant="outline"
              size="icon"
              className="h-9 w-9 shrink-0"
              onClick={() => {
                navigator.clipboard.writeText(revealedPassword)
                toast.success('Password copied')
              }}
            >
              <Copy className="h-4 w-4" />
            </Button>
          </div>
          <DialogFooter>
            <Button onClick={() => setRevealedPassword('')}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  )
}
