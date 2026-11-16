'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { formatCurrency, formatDate, getStatusColor } from '@/lib/utils'
import {
  Users,
  Search,
  MoreHorizontal,
  CheckCircle2,
  Ban,
  UserCheck,
  ChevronLeft,
  ChevronRight,
  Loader2,
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
import toast from 'react-hot-toast'

const STATUS_TABS = [
  { value: 'all', label: 'All' },
  { value: 'pending', label: 'Pending' },
  { value: 'active', label: 'Active' },
  { value: 'suspended', label: 'Suspended' },
]

const PER_PAGE = 20

export default function SuperAdminAdminsPage() {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState('all')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  // Approve dialog state
  const [approveDialogOpen, setApproveDialogOpen] = useState(false)
  const [selectedAdmin, setSelectedAdmin] = useState<number | null>(null)
  const [approvePassword, setApprovePassword] = useState('')

  // Fetch admins
  const { data, isLoading } = useQuery({
    queryKey: ['super', 'admins', activeTab, search, page],
    queryFn: () =>
      api.superAdmin.listAdmins({
        status: activeTab === 'all' ? undefined : activeTab,
        search: search || undefined,
        page,
        per_page: PER_PAGE,
      }),
  })

  const admins = data?.items || []
  const total = data?.total || 0
  const totalPages = Math.ceil(total / PER_PAGE)

  // Approve mutation
  const approveMutation = useMutation({
    mutationFn: (data: { adminId: number; password: string }) =>
      api.superAdmin.approveAdmin(data.adminId, data.password),
    onSuccess: (response) => {
      toast.success(`Admin approved. Password: ${response.assigned_password}`)
      setApproveDialogOpen(false)
      setApprovePassword('')
      setSelectedAdmin(null)
      queryClient.invalidateQueries({ queryKey: ['super', 'admins'] })
      queryClient.invalidateQueries({ queryKey: ['super', 'analytics'] })
    },
    onError: () => {
      toast.error('Failed to approve admin')
    },
  })

  // Suspend mutation
  const suspendMutation = useMutation({
    mutationFn: (adminId: number) => api.superAdmin.suspendAdmin(adminId),
    onSuccess: (response) => {
      toast.success(response.message)
      queryClient.invalidateQueries({ queryKey: ['super', 'admins'] })
      queryClient.invalidateQueries({ queryKey: ['super', 'analytics'] })
    },
    onError: () => {
      toast.error('Failed to suspend admin')
    },
  })

  // Activate mutation
  const activateMutation = useMutation({
    mutationFn: (adminId: number) => api.superAdmin.activateAdmin(adminId),
    onSuccess: (response) => {
      toast.success(response.message)
      queryClient.invalidateQueries({ queryKey: ['super', 'admins'] })
      queryClient.invalidateQueries({ queryKey: ['super', 'analytics'] })
    },
    onError: () => {
      toast.error('Failed to activate admin')
    },
  })

  const handleApproveSubmit = () => {
    if (!selectedAdmin || approvePassword.length < 8) return
    approveMutation.mutate({ adminId: selectedAdmin, password: approvePassword })
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Manage Admins</h2>
        <p className="text-muted-foreground">View and manage platform administrators</p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Admin Users</CardTitle>
              <CardDescription>{total} total administrators</CardDescription>
            </div>
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search by username, name, telegram..."
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
              ) : admins.length === 0 ? (
                <div className="text-center py-10">
                  <Users className="mx-auto h-10 w-10 text-muted-foreground/50" />
                  <p className="mt-2 text-sm text-muted-foreground">
                    {search ? 'No admins match your search' : 'No admins found'}
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
                          <TableHead className="hidden sm:table-cell">Telegram</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead>Wallet</TableHead>
                          <TableHead className="hidden lg:table-cell">Users</TableHead>
                          <TableHead className="hidden lg:table-cell">Created</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {admins.map((admin) => (
                          <TableRow key={admin.id}>
                            <TableCell>
                              <Link
                                href={`/super/admins/${admin.id}`}
                                className="font-medium text-primary hover:underline"
                              >
                                {admin.username}
                              </Link>
                            </TableCell>
                            <TableCell className="hidden md:table-cell">
                              {admin.display_name || '-'}
                            </TableCell>
                            <TableCell className="hidden sm:table-cell">
                              {admin.telegram_id || '-'}
                            </TableCell>
                            <TableCell>
                              <Badge className={getStatusColor(admin.status)}>
                                {admin.status}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              {formatCurrency(Number(admin.wallet_balance))}
                            </TableCell>
                            <TableCell className="hidden lg:table-cell">
                              {admin.user_count}
                            </TableCell>
                            <TableCell className="hidden lg:table-cell">
                              {admin.created_at ? formatDate(admin.created_at) : '-'}
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
                                    <Link href={`/super/admins/${admin.id}`}>
                                      <Users className="mr-2 h-4 w-4" />
                                      View Details
                                    </Link>
                                  </DropdownMenuItem>
                                  {admin.status === 'pending' && (
                                    <DropdownMenuItem
                                      onClick={() => {
                                        setSelectedAdmin(admin.id)
                                        setApproveDialogOpen(true)
                                      }}
                                    >
                                      <CheckCircle2 className="mr-2 h-4 w-4" />
                                      Approve
                                    </DropdownMenuItem>
                                  )}
                                  {admin.status === 'active' && (
                                    <DropdownMenuItem
                                      onClick={() => suspendMutation.mutate(admin.id)}
                                      disabled={suspendMutation.isPending}
                                    >
                                      <Ban className="mr-2 h-4 w-4" />
                                      Suspend
                                    </DropdownMenuItem>
                                  )}
                                  {admin.status === 'suspended' && (
                                    <DropdownMenuItem
                                      onClick={() => activateMutation.mutate(admin.id)}
                                      disabled={activateMutation.isPending}
                                    >
                                      <UserCheck className="mr-2 h-4 w-4" />
                                      Activate
                                    </DropdownMenuItem>
                                  )}
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

      {/* Approve Dialog */}
      <Dialog open={approveDialogOpen} onOpenChange={setApproveDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Approve Admin</DialogTitle>
            <DialogDescription>
              Set a password for this admin. They will need this to log in. Minimum 8 characters.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="approve-password">Password</Label>
              <Input
                id="approve-password"
                type="password"
                placeholder="Enter password (min 8 characters)"
                value={approvePassword}
                onChange={(e) => setApprovePassword(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setApproveDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleApproveSubmit}
              disabled={approvePassword.length < 8 || approveMutation.isPending}
            >
              {approveMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Approve
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
