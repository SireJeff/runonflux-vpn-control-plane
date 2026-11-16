'use client'

import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { Copy, Globe, KeyRound, Loader2, User } from 'lucide-react'

import { useAuth } from '@/hooks/useAuth'
import { apiClient } from '@/lib/api/client'
import { adminNewApi } from '@/lib/api/endpoints/admin-api'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'

export default function SettingsPage() {
  const { user } = useAuth()

  const { data: panel } = useQuery({
    queryKey: ['panel-url'],
    queryFn: () => adminNewApi.getPanelUrl(),
  })

  // Password change state
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const changePasswordMutation = useMutation({
    mutationFn: async () => {
      if (newPassword !== confirmPassword) {
        throw new Error('Passwords do not match')
      }
      if (newPassword.length < 8) {
        throw new Error('Password must be at least 8 characters')
      }
      const response = await apiClient.put('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      return response.data
    },
    onSuccess: () => {
      toast.success('Password changed successfully')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    },
    onError: (error: any) => {
      const msg =
        error.message ||
        error.response?.data?.detail ||
        'Failed to change password'
      toast.error(msg)
    },
  })

  const handleChangePassword = () => {
    if (!currentPassword || !newPassword || !confirmPassword) {
      toast.error('Please fill in all password fields')
      return
    }
    if (newPassword !== confirmPassword) {
      toast.error('New passwords do not match')
      return
    }
    if (newPassword.length < 8) {
      toast.error('Password must be at least 8 characters')
      return
    }
    changePasswordMutation.mutate()
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Manage your account and security
        </p>
      </div>

      {/* Account Info */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            Account Information
          </CardTitle>
          <CardDescription>Your reseller account details</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Username</Label>
              <p className="text-sm font-medium">{user?.username || '—'}</p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Display Name</Label>
              <p className="text-sm font-medium">{user?.display_name || '—'}</p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Status</Label>
              <p className="text-sm font-medium capitalize">{user?.status || '—'}</p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Role</Label>
              <p className="text-sm font-medium capitalize">
                {user?.role === 'admin' ? 'Reseller' : user?.role || '—'}
              </p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Telegram ID</Label>
              <p className="text-sm font-medium">{user?.telegram_user_id || '—'}</p>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Wallet Balance</Label>
              <p className="text-sm font-medium">
                ${parseFloat(user?.wallet_balance || '0').toFixed(2)}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Panel Domain */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Globe className="h-5 w-5" />
            Panel Domain
          </CardTitle>
          <CardDescription>The domain you use to reach this dashboard</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3">
            <p className="text-sm font-medium">{panel?.domain || panel?.panel_url || '—'}</p>
            {panel?.panel_url && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  navigator.clipboard.writeText(panel.panel_url)
                  toast.success('Copied')
                }}
              >
                <Copy className="mr-2 h-4 w-4" />
                Copy
              </Button>
            )}
          </div>
          {panel?.is_fallback && (
            <p className="mt-2 text-xs text-muted-foreground">
              Using the platform default domain — no dedicated domain is assigned yet.
            </p>
          )}
        </CardContent>
      </Card>

      <Separator />

      {/* Change Password */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <KeyRound className="h-5 w-5" />
            Change Password
          </CardTitle>
          <CardDescription>
            Update your account password. Minimum 8 characters.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="max-w-sm space-y-4">
            <div className="space-y-2">
              <Label htmlFor="current-password">Current Password</Label>
              <Input
                id="current-password"
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                placeholder="Enter current password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-password">New Password</Label>
              <Input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Enter new password"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm-password">Confirm New Password</Label>
              <Input
                id="confirm-password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm new password"
              />
            </div>
            <Button
              onClick={handleChangePassword}
              disabled={
                !currentPassword ||
                !newPassword ||
                !confirmPassword ||
                changePasswordMutation.isPending
              }
            >
              {changePasswordMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Changing...
                </>
              ) : (
                <>
                  <KeyRound className="mr-2 h-4 w-4" />
                  Change Password
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
