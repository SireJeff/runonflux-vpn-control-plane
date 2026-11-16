'use client'

import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatTraffic, getStatusColor, generateDisplayName, generateRemark } from '@/lib/utils'
import {
  Users,
  Search,
  MoreHorizontal,
  UserPlus,
  Ban,
  UserCheck,
  Trash2,
  Eye,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Copy,
} from 'lucide-react'
import Link from 'next/link'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import toast from 'react-hot-toast'
import type { ProtocolConnections } from '@/lib/api/endpoints/admin-api'

const STATUS_TABS = [
  { value: 'all', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'suspended', label: 'Suspended' },
]

const PER_PAGE = 20

export default function AdminUsersPage() {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState('all')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  // Create user dialog state
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createUsername, setCreateUsername] = useState('')
  const [createDisplayName, setCreateDisplayName] = useState('')
  const [createRemark, setCreateRemark] = useState('')
  const [createRegion, setCreateRegion] = useState('')
  const [createTrafficLimit, setCreateTrafficLimit] = useState('10')

  // Auto-fill touched flags
  const displayNameTouched = useRef(false)
  const remarkTouched = useRef(false)

  // useEffect for auto-fill
  useEffect(() => {
    if (!displayNameTouched.current) {
      setCreateDisplayName(generateDisplayName(createUsername))
    }
    if (!remarkTouched.current) {
      setCreateRemark(generateRemark(createUsername))
    }
  }, [createUsername, generateDisplayName, generateRemark])

  // Password reveal dialog state
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false)
  const [revealedPassword, setRevealedPassword] = useState('')
  const [revealedUsername, setRevealedUsername] = useState('')
  const [revealedConnections, setRevealedConnections] = useState<Record<string, Record<string, ProtocolConnections>>>({})
  const [revealedPortalUrl, setRevealedPortalUrl] = useState<string | null>(null)

  // Delete confirmation
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{ id: number; username: string } | null>(null)

  // Fetch available regions for create dialog
  const { data: regionsData } = useQuery({
    queryKey: ['admin', 'available-regions'],
    queryFn: () => api.adminNew.getAvailableRegions(),
    staleTime: 60000,
  })

  // Fetch users
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'users', activeTab, search, page],
    queryFn: () =>
      api.adminNew.listUsers({
        status: activeTab === 'all' ? undefined : activeTab,
        search: search || undefined,
        page,
        per_page: PER_PAGE,
      }),
    refetchInterval: 60000,
  })

  const users = data?.items || []
  const total = data?.total || 0
  const totalPages = Math.ceil(total / PER_PAGE)

  // Create user mutation
  const createMutation = useMutation({
    mutationFn: () => {
      const tl = parseFloat(createTrafficLimit)
      return api.adminNew.createUser({
        username: createUsername.trim(),
        display_name: createDisplayName || undefined,
        remark: createRemark || undefined,
        macro_region: createRegion || undefined,
        traffic_limit_gb: !isNaN(tl) && tl > 0 ? tl : undefined,
      })
    },
    onSuccess: (response) => {
      toast.success(`User "${response.username}" created`)
      setCreateDialogOpen(false)
      setCreateUsername('')
      setCreateDisplayName('')
      setCreateRemark('')
      setCreateRegion('')
      setCreateTrafficLimit('10')
      displayNameTouched.current = false
      remarkTouched.current = false
      setRevealedUsername(response.username)
      setRevealedPassword(response.password)
      setRevealedConnections(response.connection_strings || {})
      setRevealedPortalUrl(response.portal_url || null)
      setPasswordDialogOpen(true)
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
      queryClient.invalidateQueries({ queryKey: ['admin', 'analytics'] })
    },
    onError: () => {
      toast.error('Failed to create user')
    },
  })

  // Toggle user mutation
  const toggleMutation = useMutation({
    mutationFn: (userId: number) => api.adminNew.toggleUser(userId),
    onSuccess: (_data, userId) => {
      toast.success('User status updated')
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
      queryClient.invalidateQueries({ queryKey: ['admin', 'analytics'] })
    },
    onError: () => {
      toast.error('Failed to toggle user status')
    },
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (userId: number) => api.adminNew.deleteUser(userId),
    onSuccess: () => {
      toast.success('User deleted')
      setDeleteDialogOpen(false)
      setDeleteTarget(null)
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] })
      queryClient.invalidateQueries({ queryKey: ['admin', 'analytics'] })
    },
    onError: () => {
      toast.error('Failed to delete user')
    },
  })

  const handleCreateSubmit = () => {
    const uname = createUsername.trim()
    if (!uname) {
      toast.error('Username is required')
      return
    }
    // Match the backend contract (CreateUserRequest): 3-50 chars, letters,
    // digits, and underscore only. Catch it here so the reseller gets a clear
    // message instead of a server 422.
    if (!/^[a-zA-Z0-9_]{3,50}$/.test(uname)) {
      toast.error(
        'Username must be 3–50 characters: only letters, numbers, and underscore (no spaces or symbols)'
      )
      return
    }
    createMutation.mutate()
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">End Users</h2>
          <p className="text-muted-foreground">Manage VPN end users and their access</p>
        </div>
        <Button onClick={() => setCreateDialogOpen(true)}>
          <UserPlus className="mr-2 h-4 w-4" />
          Create User
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Users</CardTitle>
              <CardDescription>{total} total users</CardDescription>
            </div>
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search by username..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setPage(1)
                }}
                className="pl-9"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Tabs value={activeTab} onValueChange={(v) => { setActiveTab(v); setPage(1) }}>
            <TabsList>
              {STATUS_TABS.map((tab) => (
                <TabsTrigger key={tab.value} value={tab.value}>
                  {tab.label}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value={activeTab} className="mt-4">
              {isLoading ? (
                <div className="space-y-3">
                  {[...Array(5)].map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              ) : users.length === 0 ? (
                <div className="text-center py-10">
                  <Users className="mx-auto h-10 w-10 text-muted-foreground/50" />
                  <p className="mt-2 text-sm text-muted-foreground">
                    {search ? 'No users match your search' : 'No users found'}
                  </p>
                </div>
              ) : (
                <>
                  <div className="rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Username</TableHead>
                          <TableHead className="hidden md:table-cell">Display Name</TableHead>
                          <TableHead className="hidden lg:table-cell">Remark</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead className="hidden sm:table-cell">Traffic</TableHead>
                          <TableHead className="hidden md:table-cell">Region</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {users.map((user) => (
                          <TableRow key={user.id}>
                            <TableCell>
                              <Link
                                href={`/dashboard/users/${user.id}`}
                                className="font-medium text-primary hover:underline"
                              >
                                {user.username}
                              </Link>
                            </TableCell>
                            <TableCell className="hidden md:table-cell">
                              {user.display_name || '-'}
                            </TableCell>
                            <TableCell className="hidden lg:table-cell text-muted-foreground text-xs truncate max-w-[150px]">
                              {user.remark || '-'}
                            </TableCell>
                            <TableCell>
                              <Badge className={getStatusColor(user.status)}>
                                {user.status}
                              </Badge>
                            </TableCell>
                            <TableCell className="hidden sm:table-cell">
                              <div className="text-xs">
                                <span>{formatTraffic(user.traffic_used_gb || 0)}</span>
                                {user.traffic_limit_gb && (
                                  <span className="text-muted-foreground"> / {formatTraffic(user.traffic_limit_gb)}</span>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="hidden md:table-cell">
                              {user.macro_region || '-'}
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
                                  <DropdownMenuItem asChild>
                                    <Link href={`/dashboard/users/${user.id}`}>
                                      <Eye className="mr-2 h-4 w-4" />
                                      View Details
                                    </Link>
                                  </DropdownMenuItem>
                                  <DropdownMenuItem asChild>
                                    <Link href={`/dashboard/users/${user.id}/connections`}>
                                      <Copy className="mr-2 h-4 w-4" />
                                      Connection Strings
                                    </Link>
                                  </DropdownMenuItem>
                                  <DropdownMenuSeparator />
                                  <DropdownMenuItem
                                    onClick={() => toggleMutation.mutate(user.id)}
                                    disabled={toggleMutation.isPending}
                                  >
                                    {user.status === 'active' ? (
                                      <>
                                        <Ban className="mr-2 h-4 w-4" />
                                        Suspend
                                      </>
                                    ) : (
                                      <>
                                        <UserCheck className="mr-2 h-4 w-4" />
                                        Activate
                                      </>
                                    )}
                                  </DropdownMenuItem>
                                  <DropdownMenuItem
                                    className="text-red-600"
                                    onClick={() => {
                                      setDeleteTarget({ id: user.id, username: user.username })
                                      setDeleteDialogOpen(true)
                                    }}
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

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-between mt-4">
                      <p className="text-sm text-muted-foreground">
                        Showing {(page - 1) * PER_PAGE + 1}-
                        {Math.min(page * PER_PAGE, total)} of {total}
                      </p>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setPage((p) => Math.max(1, p - 1))}
                          disabled={page <= 1}
                        >
                          <ChevronLeft className="h-4 w-4" />
                          Previous
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                          disabled={page >= totalPages}
                        >
                          Next
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      {/* Create User Dialog */}
      <Dialog
        open={createDialogOpen}
        onOpenChange={(open) => {
          if (!open) {
            setCreateUsername('')
            setCreateDisplayName('')
            setCreateRemark('')
            setCreateRegion('')
            setCreateTrafficLimit('10')
            displayNameTouched.current = false
            remarkTouched.current = false
          }
          setCreateDialogOpen(open)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New User</DialogTitle>
            <DialogDescription>
              Create a VPN end user. A password will be generated automatically.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="create-username">Username *</Label>
              <Input
                id="create-username"
                placeholder="e.g. user123"
                value={createUsername}
                onChange={(e) => setCreateUsername(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-display-name">Display Name</Label>
              <Input
                id="create-display-name"
                placeholder="Optional display name"
                value={createDisplayName}
                onChange={(e) => {
                  displayNameTouched.current = true
                  setCreateDisplayName(e.target.value)
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-remark">Remark</Label>
              <Textarea
                id="create-remark"
                placeholder="Optional note about this user"
                value={createRemark}
                onChange={(e) => {
                  remarkTouched.current = true
                  setCreateRemark(e.target.value)
                }}
                rows={2}
              />
            </div>
            {/* Macro Region Selection */}
            <div className="space-y-2">
              <Label>Region</Label>
              <div className="grid grid-cols-2 gap-2">
                {(regionsData || [])
                  .filter(r => (r as any).countries !== undefined)  // filter to MacroRegionInfo only
                  .map((region) => (
                    <button
                      key={region.code}
                      type="button"
                      onClick={() => setCreateRegion(region.code)}
                      className={`p-3 rounded-lg border text-left transition-colors ${
                        createRegion === region.code
                          ? 'border-primary bg-primary/5 ring-1 ring-primary'
                          : 'border-border hover:border-primary/50'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-xl">{region.flag}</span>
                        <div>
                          <div className="font-medium text-sm">{region.name}</div>
                          <div className="text-xs text-muted-foreground">
                            {region.healthy_instances} instances
                          </div>
                        </div>
                      </div>
                    </button>
                  ))}
              </div>
              {!createRegion && (
                <p className="text-xs text-muted-foreground">Auto-assign if not selected</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-traffic-limit">Traffic Limit (GB)</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="create-traffic-limit"
                  type="number"
                  step="0.1"
                  min="0"
                  placeholder="10"
                  value={createTrafficLimit}
                  onChange={(e) => setCreateTrafficLimit(e.target.value)}
                  className="w-28"
                />
                <span className="text-sm text-muted-foreground">GB (leave empty for unlimited)</span>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreateSubmit}
              disabled={!createUsername.trim() || createMutation.isPending}
            >
              {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create User
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Password Reveal Dialog */}
      <Dialog open={passwordDialogOpen} onOpenChange={setPasswordDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>User Created Successfully</DialogTitle>
            <DialogDescription>
              Copy the credentials below and share them with the user.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Username</Label>
              <div className="flex items-center gap-2">
                <code className="flex-1 rounded-md bg-muted px-3 py-2 text-sm">
                  {revealedUsername}
                </code>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-9 w-9"
                  onClick={() => {
                    navigator.clipboard.writeText(revealedUsername)
                    toast.success('Username copied')
                  }}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Password (auto-generated)</Label>
              <div className="flex items-center gap-2">
                <code className="flex-1 rounded-md bg-muted px-3 py-2 text-sm font-mono">
                  {revealedPassword}
                </code>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-9 w-9"
                  onClick={() => {
                    navigator.clipboard.writeText(revealedPassword)
                    toast.success('Password copied')
                  }}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
            {Object.keys(revealedConnections).length > 0 && (
              <div className="space-y-2">
                <Label>Connection Strings</Label>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {Object.entries(revealedConnections).map(([countryCode, protocols]) => (
                    <div key={countryCode} className="space-y-1.5">
                      <h4 className="font-medium text-xs text-muted-foreground border-b pb-1">
                        {countryCode}
                      </h4>
                      {Object.entries(protocols).map(([protocol, conn]) => (
                        <div key={protocol}>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="text-xs w-20 shrink-0 justify-center">
                              {protocol.toUpperCase()}
                            </Badge>
                            <code className="flex-1 rounded-md bg-muted px-2 py-1 text-xs font-mono break-all leading-relaxed">
                              {conn.primary}
                            </code>
                            <Button
                              variant="outline"
                              size="icon"
                              className="h-7 w-7 shrink-0"
                              onClick={() => {
                                navigator.clipboard.writeText(conn.primary)
                                toast.success(`${protocol.toUpperCase()} primary copied`)
                              }}
                            >
                              <Copy className="h-3 w-3" />
                            </Button>
                          </div>
                          {conn.fallbacks.map((fb, i) => (
                            <div key={i} className="flex items-center gap-2 mt-1 ml-5">
                              <Badge variant="outline" className="text-xs w-20 shrink-0 justify-center opacity-60">
                                F{i + 1}
                              </Badge>
                              <code className="flex-1 rounded-md bg-muted px-2 py-1 text-xs font-mono break-all leading-relaxed opacity-70">
                                {fb}
                              </code>
                              <Button
                                variant="outline"
                                size="icon"
                                className="h-7 w-7 shrink-0"
                                onClick={() => {
                                  navigator.clipboard.writeText(fb)
                                  toast.success(`${protocol.toUpperCase()} fallback ${i + 1} copied`)
                                }}
                              >
                                <Copy className="h-3 w-3" />
                              </Button>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {revealedPortalUrl && (
              <div className="space-y-2">
                <Label>User Portal</Label>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded-md bg-muted px-3 py-2 text-sm">
                    {revealedPortalUrl}
                  </code>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-9 w-9"
                    onClick={() => {
                      navigator.clipboard.writeText(revealedPortalUrl)
                      toast.success('Portal URL copied')
                    }}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              This password will not be shown again. Make sure to copy it now.
            </p>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                const allText = [
                  `Username: ${revealedUsername}`,
                  `Password: ${revealedPassword}`,
                ]
                if (Object.keys(revealedConnections).length > 0) {
                  allText.push('')
                  Object.entries(revealedConnections).forEach(([countryCode, protocols]) => {
                    allText.push(`[${countryCode}]`)
                    Object.entries(protocols).forEach(([p, conn]) => {
                      allText.push(`${p.toUpperCase()}: ${conn.primary}`)
                      conn.fallbacks.forEach((fb, i) => {
                        allText.push(`  Fallback ${i + 1}: ${fb}`)
                      })
                    })
                    allText.push('')
                  })
                }
                if (revealedPortalUrl) {
                  allText.push(`Dashboard: ${revealedPortalUrl}`)
                }
                navigator.clipboard.writeText(allText.join('\n'))
                toast.success('All credentials copied')
              }}
            >
              <Copy className="mr-1 h-3 w-3" />
              Copy All
            </Button>
            <Button onClick={() => setPasswordDialogOpen(false)}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete User</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete user &quot;{deleteTarget?.username}&quot;? This action
              cannot be undone. All credentials and regions will be removed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
