'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatRelativeTime } from '@/lib/utils'
import {
  Plus,
  RefreshCw,
  Trash2,
  Edit3,
  Server,
  Loader2,
  Power,
  PowerOff,
  MoreHorizontal,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import toast from 'react-hot-toast'

const PROTOCOL_FIELDS = [
  { key: 'ssh', label: 'SSH', default: 32442 },
  { key: 'ss', label: 'Shadowsocks', default: 37734 },
  { key: 'vless', label: 'VLESS', default: 34083 },
  { key: 'trojan', label: 'Trojan', default: 31889 },
  { key: 'outline', label: 'Outline', default: 38527 },
  { key: 'http_proxy', label: 'HTTP Proxy', default: 31868 },
]

export default function SuperAdminAppsPage() {
  const queryClient = useQueryClient()

  // Register dialog state
  const [registerDialogOpen, setRegisterDialogOpen] = useState(false)
  const [registerAppName, setRegisterAppName] = useState('')
  const [registerPorts, setRegisterPorts] = useState<Record<string, string>>(
    Object.fromEntries(PROTOCOL_FIELDS.map((f) => [f.key, String(f.default)]))
  )

  // Edit dialog state
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [editAppId, setEditAppId] = useState<number | null>(null)
  const [editAppName, setEditAppName] = useState('')
  const [editPorts, setEditPorts] = useState<Record<string, string>>({})
  const [editIsActive, setEditIsActive] = useState(true)

  // Delete dialog state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteAppId, setDeleteAppId] = useState<number | null>(null)
  const [deleteAppName, setDeleteAppName] = useState('')

  // Fetch apps
  const { data: apps = [], isLoading } = useQuery({
    queryKey: ['super', 'apps'],
    queryFn: () => api.superAdmin.listApps(),
  })

  // Register mutation
  const registerMutation = useMutation({
    mutationFn: (data: { app_name: string; protocol_ports: Record<string, number> }) =>
      api.superAdmin.registerApp(data),
    onSuccess: (response) => {
      toast.success(`App "${response.app_name}" registered (ID: ${response.id})`)
      setRegisterDialogOpen(false)
      setRegisterAppName('')
      setRegisterPorts(
        Object.fromEntries(PROTOCOL_FIELDS.map((f) => [f.key, String(f.default)]))
      )
      queryClient.invalidateQueries({ queryKey: ['super', 'apps'] })
    },
    onError: () => {
      toast.error('Failed to register app')
    },
  })

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: {
      appId: number
      request: { protocol_ports?: Record<string, number>; is_active?: boolean }
    }) => api.superAdmin.updateApp(data.appId, data.request),
    onSuccess: (response) => {
      toast.success(response.message)
      setEditDialogOpen(false)
      setEditAppId(null)
      queryClient.invalidateQueries({ queryKey: ['super', 'apps'] })
    },
    onError: () => {
      toast.error('Failed to update app')
    },
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (appId: number) => api.superAdmin.deleteApp(appId),
    onSuccess: (response) => {
      toast.success(response.message)
      setDeleteDialogOpen(false)
      setDeleteAppId(null)
      setDeleteAppName('')
      queryClient.invalidateQueries({ queryKey: ['super', 'apps'] })
    },
    onError: () => {
      toast.error('Failed to delete app')
    },
  })

  // Sync mutation
  const syncMutation = useMutation({
    mutationFn: (appId: number) => api.superAdmin.syncApp(appId),
    onSuccess: (response) => {
      toast.success(response.message)
      queryClient.invalidateQueries({ queryKey: ['super', 'apps'] })
    },
    onError: () => {
      toast.error('Failed to sync app')
    },
  })

  // Toggle active mutation
  const toggleActiveMutation = useMutation({
    mutationFn: (data: { appId: number; is_active: boolean }) =>
      api.superAdmin.updateApp(data.appId, { is_active: data.is_active }),
    onSuccess: (response) => {
      toast.success(response.message)
      queryClient.invalidateQueries({ queryKey: ['super', 'apps'] })
    },
    onError: () => {
      toast.error('Failed to toggle app status')
    },
  })

  const handleRegisterSubmit = () => {
    if (!registerAppName.trim()) {
      toast.error('App name is required')
      return
    }
    const ports: Record<string, number> = {}
    for (const field of PROTOCOL_FIELDS) {
      const val = parseInt(registerPorts[field.key], 10)
      if (isNaN(val) || val < 1 || val > 65535) {
        toast.error(`Invalid port for ${field.label}`)
        return
      }
      ports[field.key] = val
    }
    registerMutation.mutate({ app_name: registerAppName.trim(), protocol_ports: ports })
  }

  const handleEditSubmit = () => {
    if (!editAppId) return
    const ports: Record<string, number> = {}
    for (const field of PROTOCOL_FIELDS) {
      const val = parseInt(editPorts[field.key], 10)
      if (isNaN(val) || val < 1 || val > 65535) {
        toast.error(`Invalid port for ${field.label}`)
        return
      }
      ports[field.key] = val
    }
    updateMutation.mutate({
      appId: editAppId,
      request: { protocol_ports: ports, is_active: editIsActive },
    })
  }

  const handleDeleteSubmit = () => {
    if (!deleteAppId) return
    deleteMutation.mutate(deleteAppId)
  }

  const openEditDialog = (app: (typeof apps)[0]) => {
    setEditAppId(app.id)
    setEditAppName(app.app_name)
    setEditPorts(
      Object.fromEntries(
        PROTOCOL_FIELDS.map((f) => [
          f.key,
          String(app.protocol_ports?.[f.key] ?? f.default),
        ])
      )
    )
    setEditIsActive(app.is_active)
    setEditDialogOpen(true)
  }

  const openDeleteDialog = (app: (typeof apps)[0]) => {
    setDeleteAppId(app.id)
    setDeleteAppName(app.app_name)
    setDeleteDialogOpen(true)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Flux Apps</h2>
          <p className="text-muted-foreground">Manage Flux app registrations and protocol ports</p>
        </div>
        <Button onClick={() => setRegisterDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Register App
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Registered Apps</CardTitle>
            <CardDescription>{apps.length} app{apps.length !== 1 ? 's' : ''} registered</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              {[...Array(4)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : apps.length === 0 ? (
            <div className="text-center py-10">
              <Server className="mx-auto h-10 w-10 text-muted-foreground/50" />
              <p className="mt-2 text-sm text-muted-foreground">No apps registered yet</p>
            </div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>App Name</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="hidden md:table-cell">Regions</TableHead>
                    <TableHead className="hidden sm:table-cell">Healthy Instances</TableHead>
                    <TableHead className="hidden lg:table-cell">Protocols</TableHead>
                    <TableHead className="hidden lg:table-cell">Last Sync</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {apps.map((app) => (
                    <TableRow key={app.id}>
                      <TableCell className="font-mono font-bold">{app.app_name}</TableCell>
                      <TableCell>
                        <Badge
                          className={
                            app.is_active
                              ? 'bg-green-500/15 text-green-700 hover:bg-green-500/25'
                              : 'bg-gray-500/15 text-gray-700 hover:bg-gray-500/25'
                          }
                        >
                          {app.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </TableCell>
                      <TableCell className="hidden md:table-cell">
                        {app.regions && app.regions.length > 0
                          ? app.regions.map((r) => r.toUpperCase()).join(', ')
                          : 'Pending sync'}
                      </TableCell>
                      <TableCell className="hidden sm:table-cell">
                        <span
                          className={
                            app.healthy_instances > 0
                              ? 'text-green-600 font-medium'
                              : 'text-red-600 font-medium'
                          }
                        >
                          {app.healthy_instances}
                        </span>
                      </TableCell>
                      <TableCell className="hidden lg:table-cell">
                        {Object.keys(app.protocol_ports || {}).length}
                      </TableCell>
                      <TableCell className="hidden lg:table-cell">
                        {app.last_discovery_at
                          ? formatRelativeTime(app.last_discovery_at)
                          : 'Never'}
                      </TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuLabel>Actions</DropdownMenuLabel>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              onClick={() => openEditDialog(app)}
                              disabled={updateMutation.isPending}
                            >
                              <Edit3 className="mr-2 h-4 w-4" />
                              Edit
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => syncMutation.mutate(app.id)}
                              disabled={syncMutation.isPending}
                            >
                              {syncMutation.isPending ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              ) : (
                                <RefreshCw className="mr-2 h-4 w-4" />
                              )}
                              Sync
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() =>
                                toggleActiveMutation.mutate({
                                  appId: app.id,
                                  is_active: !app.is_active,
                                })
                              }
                              disabled={toggleActiveMutation.isPending}
                            >
                              {app.is_active ? (
                                <>
                                  <PowerOff className="mr-2 h-4 w-4" />
                                  Deactivate
                                </>
                              ) : (
                                <>
                                  <Power className="mr-2 h-4 w-4" />
                                  Activate
                                </>
                              )}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onClick={() => openDeleteDialog(app)}
                              disabled={deleteMutation.isPending}
                            >
                              <Trash2 className="mr-2 h-4 w-4" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Register Dialog */}
      <Dialog open={registerDialogOpen} onOpenChange={setRegisterDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Register Flux App</DialogTitle>
            <DialogDescription>
              Register a new Flux app with protocol port mappings.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="register-app-name">App Name</Label>
              <Input
                id="register-app-name"
                placeholder="e.g. fluxvpn-prod-01"
                value={registerAppName}
                onChange={(e) => setRegisterAppName(e.target.value)}
              />
            </div>
            <div className="space-y-3">
              <Label>Protocol Ports</Label>
              <div className="grid grid-cols-2 gap-3">
                {PROTOCOL_FIELDS.map((field) => (
                  <div key={field.key} className="space-y-1">
                    <Label htmlFor={`register-port-${field.key}`} className="text-xs text-muted-foreground">
                      {field.label}
                    </Label>
                    <Input
                      id={`register-port-${field.key}`}
                      type="number"
                      min="1"
                      max="65535"
                      placeholder={String(field.default)}
                      value={registerPorts[field.key]}
                      onChange={(e) =>
                        setRegisterPorts((prev) => ({
                          ...prev,
                          [field.key]: e.target.value,
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRegisterDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleRegisterSubmit}
              disabled={!registerAppName.trim() || registerMutation.isPending}
            >
              {registerMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Register
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Edit App: {editAppName}</DialogTitle>
            <DialogDescription>
              Update protocol ports and active status.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border p-3">
              <Label htmlFor="edit-active">Active</Label>
              <Switch
                id="edit-active"
                checked={editIsActive}
                onCheckedChange={setEditIsActive}
              />
            </div>
            <div className="space-y-3">
              <Label>Protocol Ports</Label>
              <div className="grid grid-cols-2 gap-3">
                {PROTOCOL_FIELDS.map((field) => (
                  <div key={field.key} className="space-y-1">
                    <Label htmlFor={`edit-port-${field.key}`} className="text-xs text-muted-foreground">
                      {field.label}
                    </Label>
                    <Input
                      id={`edit-port-${field.key}`}
                      type="number"
                      min="1"
                      max="65535"
                      value={editPorts[field.key]}
                      onChange={(e) =>
                        setEditPorts((prev) => ({
                          ...prev,
                          [field.key]: e.target.value,
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleEditSubmit} disabled={updateMutation.isPending}>
              {updateMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete App</DialogTitle>
            <DialogDescription>
              This action cannot be undone. This will permanently remove the app registration and
              cascade cleanup all associated domains, deployments, and linked records.
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-3">
            <p className="text-sm text-destructive font-medium">
              Are you sure you want to delete <span className="font-mono font-bold">{deleteAppName}</span>?
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              All associated domains, deployments, and linked records will be permanently removed.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteSubmit}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Delete App
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
