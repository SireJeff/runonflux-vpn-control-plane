'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Package } from '@/lib/api'
import { formatDate } from '@/lib/utils'
import {
  Package as PackageIcon,
  Plus,
  Loader2,
  Pencil,
  Archive,
  Trash2,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import toast from 'react-hot-toast'

interface PackageFormData {
  name: string
  traffic_limit_gb: string
  duration_days: string
  price_tomans: string
  display_order: string
  is_active: boolean
  region_count: string
  all_regions: boolean
}

const emptyForm: PackageFormData = {
  name: '',
  traffic_limit_gb: '',
  duration_days: '30',
  price_tomans: '',
  display_order: '0',
  is_active: true,
  region_count: '1',
  all_regions: false,
}

function formatTomans(value: string | number): string {
  return Number(value).toLocaleString()
}

function estimatedRegionCost(form: PackageFormData): string {
  const PRICE_PER_REGION_USD = 2 // matches PlatformSetting price_per_region_monthly default
  const count = form.all_regions ? 4 : Math.max(1, Number(form.region_count) || 1)
  const extra = Math.max(0, count - 1) // primary region is free
  const months = Math.max(1, Math.round(Number(form.duration_days || '30') / 30))
  const cost = extra * PRICE_PER_REGION_USD * months
  return cost === 0 ? '$0 (single region)' : `~$${cost} over ${months} mo`
}

export default function PackagesPage() {
  const queryClient = useQueryClient()
  const [showInactive, setShowInactive] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingPackage, setEditingPackage] = useState<Package | null>(null)
  const [form, setForm] = useState<PackageFormData>(emptyForm)

  // Fetch packages
  const { data: packages, isLoading } = useQuery({
    queryKey: ['packages', showInactive],
    queryFn: () => api.packages.list(showInactive),
  })

  // Create mutation
  const createMutation = useMutation({
    mutationFn: () =>
      api.packages.create({
        name: form.name,
        traffic_limit_gb: Number(form.traffic_limit_gb),
        duration_days: Number(form.duration_days),
        price_tomans: Number(form.price_tomans),
        display_order: Number(form.display_order),
        region_count: form.all_regions ? 1 : Number(form.region_count),
        all_regions: form.all_regions,
      }),
    onSuccess: () => {
      toast.success('Package created')
      closeDialog()
      queryClient.invalidateQueries({ queryKey: ['packages'] })
    },
    onError: (err: any) => {
      if (err.response?.status === 409) {
        toast.error('A package with this name already exists')
      } else {
        toast.error('Failed to create package')
      }
    },
  })

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: () => {
      if (!editingPackage) return Promise.reject('No package selected')
      return api.packages.update(editingPackage.id, {
        name: form.name,
        traffic_limit_gb: Number(form.traffic_limit_gb),
        duration_days: Number(form.duration_days),
        price_tomans: Number(form.price_tomans),
        display_order: Number(form.display_order),
        is_active: form.is_active,
        region_count: form.all_regions ? 1 : Number(form.region_count),
        all_regions: form.all_regions,
      })
    },
    onSuccess: () => {
      toast.success('Package updated')
      closeDialog()
      queryClient.invalidateQueries({ queryKey: ['packages'] })
    },
    onError: (err: any) => {
      if (err.response?.status === 409) {
        toast.error('A package with this name already exists')
      } else {
        toast.error('Failed to update package')
      }
    },
  })

  // Archive mutation
  const archiveMutation = useMutation({
    mutationFn: (id: number) => api.packages.archive(id),
    onSuccess: () => {
      toast.success('Package archived')
      queryClient.invalidateQueries({ queryKey: ['packages'] })
    },
    onError: () => {
      toast.error('Failed to archive package')
    },
  })

  const openCreateDialog = () => {
    setEditingPackage(null)
    setForm(emptyForm)
    setDialogOpen(true)
  }

  const openEditDialog = (pkg: Package) => {
    setEditingPackage(pkg)
    setForm({
      name: pkg.name,
      traffic_limit_gb: pkg.traffic_limit_gb,
      duration_days: String(pkg.duration_days),
      price_tomans: pkg.price_tomans,
      display_order: String(pkg.display_order),
      is_active: pkg.is_active,
      region_count: String(pkg.region_count),
      all_regions: pkg.all_regions,
    })
    setDialogOpen(true)
  }

  const closeDialog = () => {
    setDialogOpen(false)
    setEditingPackage(null)
    setForm(emptyForm)
  }

  const handleSubmit = () => {
    if (!form.name.trim()) {
      toast.error('Package name is required')
      return
    }
    if (!form.traffic_limit_gb || Number(form.traffic_limit_gb) <= 0) {
      toast.error('Traffic limit must be greater than 0')
      return
    }
    if (!form.duration_days || Number(form.duration_days) <= 0) {
      toast.error('Duration must be greater than 0')
      return
    }
    if (!form.price_tomans || Number(form.price_tomans) <= 0) {
      toast.error('Price must be greater than 0')
      return
    }
    if (editingPackage) {
      updateMutation.mutate()
    } else {
      createMutation.mutate()
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Packages</h2>
          <p className="text-muted-foreground">Manage subscription packages</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Switch
              id="show-inactive"
              checked={showInactive}
              onCheckedChange={setShowInactive}
            />
            <Label htmlFor="show-inactive" className="text-sm">
              Show inactive
            </Label>
          </div>
          <Button onClick={openCreateDialog}>
            <Plus className="mr-2 h-4 w-4" />
            Create Package
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : !packages || packages.length === 0 ? (
            <div className="p-12 text-center">
              <PackageIcon className="mx-auto h-12 w-12 text-muted-foreground/50" />
              <p className="mt-4 text-muted-foreground">
                {showInactive ? 'No packages found' : 'No active packages. Create one to get started.'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Traffic</TableHead>
                    <TableHead>Duration</TableHead>
                    <TableHead>Price</TableHead>
                    <TableHead>Regions</TableHead>
                    <TableHead>Order</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Updated</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {packages.map((pkg) => (
                    <TableRow key={pkg.id}>
                      <TableCell className="font-medium">{pkg.name}</TableCell>
                      <TableCell>
                        {Number(pkg.traffic_limit_gb).toFixed(1)} GB
                      </TableCell>
                      <TableCell>{pkg.duration_days} days</TableCell>
                      <TableCell>{formatTomans(pkg.price_tomans)} T</TableCell>
                      <TableCell>{pkg.all_regions ? 'All' : pkg.region_count}</TableCell>
                      <TableCell>{pkg.display_order}</TableCell>
                      <TableCell>
                        <Badge
                          className={
                            pkg.is_active
                              ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300'
                              : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300'
                          }
                        >
                          {pkg.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDate(pkg.updated_at, true)}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => openEditDialog(pkg)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          {pkg.is_active && (
                            <AlertDialog>
                              <AlertDialogTrigger asChild>
                                <Button variant="ghost" size="sm">
                                  <Archive className="h-4 w-4" />
                                </Button>
                              </AlertDialogTrigger>
                              <AlertDialogContent>
                                <AlertDialogHeader>
                                  <AlertDialogTitle>Archive Package?</AlertDialogTitle>
                                  <AlertDialogDescription>
                                    This will deactivate the package &quot;{pkg.name}&quot;. Existing
                                    subscriptions will not be affected.
                                  </AlertDialogDescription>
                                </AlertDialogHeader>
                                <AlertDialogFooter>
                                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                                  <AlertDialogAction
                                    onClick={() => archiveMutation.mutate(pkg.id)}
                                    disabled={archiveMutation.isPending}
                                  >
                                    Archive
                                  </AlertDialogAction>
                                </AlertDialogFooter>
                              </AlertDialogContent>
                            </AlertDialog>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={(open) => !open && closeDialog()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {editingPackage ? 'Edit Package' : 'Create Package'}
            </DialogTitle>
            <DialogDescription>
              {editingPackage
                ? 'Update package details'
                : 'Define a new subscription package'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="pkg-name">Name *</Label>
              <Input
                id="pkg-name"
                placeholder="e.g. Basic, Premium, Gold"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="pkg-traffic">Traffic (GB) *</Label>
                <Input
                  id="pkg-traffic"
                  type="number"
                  min={0.1}
                  step={0.1}
                  placeholder="10"
                  value={form.traffic_limit_gb}
                  onChange={(e) => setForm({ ...form, traffic_limit_gb: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="pkg-duration">Duration (days) *</Label>
                <Input
                  id="pkg-duration"
                  type="number"
                  min={1}
                  placeholder="30"
                  value={form.duration_days}
                  onChange={(e) => setForm({ ...form, duration_days: e.target.value })}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="pkg-price">Price (Tomans) *</Label>
                <Input
                  id="pkg-price"
                  type="number"
                  min={0}
                  step={1000}
                  placeholder="150000"
                  value={form.price_tomans}
                  onChange={(e) => setForm({ ...form, price_tomans: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="pkg-order">Display Order</Label>
                <Input
                  id="pkg-order"
                  type="number"
                  min={0}
                  placeholder="0"
                  value={form.display_order}
                  onChange={(e) => setForm({ ...form, display_order: e.target.value })}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="pkg-regions">Regions included *</Label>
                <Input
                  id="pkg-regions"
                  type="number"
                  min={1}
                  max={4}
                  disabled={form.all_regions}
                  value={form.region_count}
                  onChange={(e) => setForm({ ...form, region_count: e.target.value })}
                />
              </div>
              <div className="flex items-end gap-2 pb-2">
                <Switch
                  id="pkg-all-regions"
                  checked={form.all_regions}
                  onCheckedChange={(checked) => setForm({ ...form, all_regions: checked })}
                />
                <Label htmlFor="pkg-all-regions">All available regions</Label>
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              Est. platform cost: {estimatedRegionCost(form)} — for guidance only, not enforced.
            </p>

            {editingPackage && (
              <div className="flex items-center gap-2">
                <Switch
                  id="pkg-active"
                  checked={form.is_active}
                  onCheckedChange={(checked) => setForm({ ...form, is_active: checked })}
                />
                <Label htmlFor="pkg-active">Active</Label>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeDialog}>
              Cancel
            </Button>
            <Button onClick={handleSubmit} disabled={isSaving}>
              {isSaving ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              {editingPackage ? 'Save Changes' : 'Create Package'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
