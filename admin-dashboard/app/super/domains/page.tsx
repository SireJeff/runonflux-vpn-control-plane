'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
  TldEntry,
  TldListResponse,
  TldCreateRequest,
  TldActivateResponse,
} from '@/lib/api/endpoints/super-admin'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import toast from 'react-hot-toast'

const PURPOSES = ['fdm', 'subscription', 'dashboard', 'admin_panel'] as const
type Purpose = (typeof PURPOSES)[number]
const PURPOSE_LABEL: Record<Purpose, string> = {
  fdm: 'VPN Connection',
  subscription: 'Subscription Link',
  dashboard: 'User Dashboard',
  admin_panel: 'Admin Panel (Reseller Dashboard)',
}

const PURPOSE_DESCRIPTION: Record<Purpose, string> = {
  fdm: 'VPN Connection Strings',
  subscription: 'Subscription Links',
  dashboard: 'User Dashboard',
  admin_panel: 'Reseller Admin Panel',
}

export default function SuperAdminDomainsPage() {
  const queryClient = useQueryClient()

  // --- TLD CRUD (migrated from /super/settings) ---
  const [addTldDialogOpen, setAddTldDialogOpen] = useState(false)
  const [addTldPurpose, setAddTldPurpose] = useState<Purpose>('fdm')
  const [activateDialogOpen, setActivateDialogOpen] = useState(false)
  const [activateTld, setActivateTld] = useState<TldEntry | null>(null)
  const [newTldDomain, setNewTldDomain] = useState('')
  const [newTldProvider, setNewTldProvider] = useState<'cloudflare' | 'arvancloud'>('cloudflare')
  const [newTldZoneId, setNewTldZoneId] = useState('')

  const { data: tldData } = useQuery({
    queryKey: ['tlds'],
    queryFn: () => api.superAdmin.listTlds(),
  })
  const tlds: TldListResponse = tldData || { fdm: [], subscription: [], dashboard: [], admin_panel: [] }

  const invalidateTlds = () => {
    queryClient.invalidateQueries({ queryKey: ['tlds'] })
    queryClient.invalidateQueries({ queryKey: ['super', 'tld-analytics'] })
    queryClient.invalidateQueries({ queryKey: ['super', 'tld-assignments'] })
  }

  const createTldMutation = useMutation({
    mutationFn: (data: TldCreateRequest) => api.superAdmin.createTld(data),
    onSuccess: () => {
      toast.success('Domain registered successfully')
      invalidateTlds()
      setAddTldDialogOpen(false)
      setNewTldDomain('')
      setNewTldZoneId('')
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to register domain'),
  })
  const deleteTldMutation = useMutation({
    mutationFn: (tldId: number) => api.superAdmin.deleteTld(tldId),
    onSuccess: () => { toast.success('Domain removed'); invalidateTlds() },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to remove domain'),
  })
  const activateTldMutation = useMutation({
    mutationFn: (tldId: number) => api.superAdmin.activateTld(tldId),
    onSuccess: (data: TldActivateResponse) => {
      toast.success(data.message)
      invalidateTlds()
      setActivateDialogOpen(false)
      setActivateTld(null)
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to activate domain'),
  })
  const deactivateTldMutation = useMutation({
    mutationFn: (tldId: number) => api.superAdmin.deactivateTld(tldId),
    onSuccess: (data: TldActivateResponse) => { toast.success(data.message); invalidateTlds() },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to deactivate domain'),
  })

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Domains</h2>
        <p className="text-muted-foreground">Manage TLDs per purpose and assign them to resellers</p>
      </div>

      <Tabs defaultValue="tlds">
        <TabsList>
          <TabsTrigger value="tlds">TLDs</TabsTrigger>
          <TabsTrigger value="matrix">Assignments</TabsTrigger>
        </TabsList>

        {/* ---- Tab 1: TLD CRUD (migrated sections) ---- */}
        <TabsContent value="tlds">
          <Card>
            <CardHeader><CardTitle>Domain Management</CardTitle></CardHeader>
            <CardContent className="space-y-6">
              {PURPOSES.map((purpose, i) => (
                <div key={purpose}>
                  {i > 0 && <hr className="border-gray-200 mb-4" />}
                  <h3 className="text-sm font-semibold mb-3">{PURPOSE_LABEL[purpose]}</h3>
                  <TldSection
                    tlds={tlds[purpose]}
                    onAdd={() => { setAddTldPurpose(purpose); setAddTldDialogOpen(true) }}
                    onActivate={(tld) => { setActivateTld(tld); setActivateDialogOpen(true) }}
                    onDeactivate={(tld) => deactivateTldMutation.mutate(tld.id)}
                    onDelete={(tld) => deleteTldMutation.mutate(tld.id)}
                  />
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---- Tab 2: assignment matrix ---- */}
        <TabsContent value="matrix">
          <AssignmentMatrix />
        </TabsContent>
      </Tabs>

      {/* Add TLD Dialog (ported from /super/settings) */}
      <Dialog open={addTldDialogOpen} onOpenChange={setAddTldDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Domain</DialogTitle>
            <DialogDescription>{PURPOSE_DESCRIPTION[addTldPurpose]}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <label className="text-sm font-medium">Domain Name</label>
              <Input
                value={newTldDomain}
                onChange={(e) => setNewTldDomain(e.target.value)}
                placeholder={addTldPurpose === 'fdm' ? 'e.g., operator4.example.invalid (base domain only)' : 'e.g., cdn.operator4.example.invalid'}
              />
              {addTldPurpose === 'fdm' && (
                <p className="text-xs text-muted-foreground mt-1">
                  Base TLD only — FDM creates subdomains automatically (e.g., de-ssh-01.operator4.example.invalid)
                </p>
              )}
            </div>
            <div>
              <label className="text-sm font-medium">DNS Provider</label>
              <select
                className="w-full border rounded-md p-2 text-sm"
                value={newTldProvider}
                onChange={(e) => { setNewTldProvider(e.target.value as 'cloudflare' | 'arvancloud'); setNewTldZoneId('') }}
              >
                <option value="cloudflare">Cloudflare</option>
                <option value="arvancloud">ArvanCloud</option>
              </select>
            </div>
            {newTldProvider === 'cloudflare' && (
              <div>
                <label className="text-sm font-medium">Zone ID</label>
                <Input value={newTldZoneId} onChange={(e) => setNewTldZoneId(e.target.value)} placeholder="Cloudflare Zone ID" />
              </div>
            )}
            {newTldProvider === 'arvancloud' && addTldPurpose !== 'fdm' && (
              <div>
                <label className="text-sm font-medium">Zone Domain</label>
                <Input value={newTldZoneId} onChange={(e) => setNewTldZoneId(e.target.value)} placeholder="e.g., operator4.example.invalid" />
                <p className="text-xs text-muted-foreground mt-1">The base domain registered in your ArvanCloud CDN</p>
              </div>
            )}
            {newTldProvider === 'arvancloud' && addTldPurpose === 'fdm' && (
              <p className="text-xs text-muted-foreground">
                Zone domain auto-set to the base domain above (FDM creates subdomains automatically)
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddTldDialogOpen(false)}>Cancel</Button>
            <Button
              onClick={() => createTldMutation.mutate({
                domain: newTldDomain,
                dns_provider: newTldProvider,
                zone_id: newTldProvider === 'arvancloud' && addTldPurpose === 'fdm'
                  ? newTldDomain // Auto-set zone = domain for FDM
                  : (newTldZoneId || null),
                purpose: addTldPurpose,
              })}
              disabled={!newTldDomain || (newTldProvider === 'cloudflare' && !newTldZoneId) || (newTldProvider === 'arvancloud' && addTldPurpose !== 'fdm' && !newTldZoneId) || createTldMutation.isPending}
            >
              {createTldMutation.isPending ? 'Validating...' : 'Add Domain'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Activate TLD Dialog (ported from /super/settings) */}
      <Dialog open={activateDialogOpen} onOpenChange={setActivateDialogOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Activate Domain</DialogTitle></DialogHeader>
          {activateTld && (
            <div className="space-y-3">
              <p className="text-sm">
                Activate <strong>{activateTld.domain}</strong> ({activateTld.dns_provider})?
              </p>
              <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3 text-sm">
                <p className="font-medium text-yellow-800">This will:</p>
                <ul className="mt-1 space-y-1 text-yellow-700 list-disc list-inside">
                  <li>Create DNS records on {activateTld.domain}</li>
                  {activateTld.purpose === 'fdm' ? (
                    <>
                      <li>Add this TLD to the active fdm pool (multi-active)</li>
                      <li>Generate FDM subdomains + DNS on the next sync</li>
                      <li>No admins are migrated — existing user URLs stay unchanged</li>
                    </>
                  ) : (
                    <li>Add to the active pool (multi-active) — existing user URLs are unaffected</li>
                  )}
                </ul>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => { setActivateDialogOpen(false); setActivateTld(null) }}>Cancel</Button>
            <Button variant="destructive" onClick={() => activateTld && activateTldMutation.mutate(activateTld.id)} disabled={activateTldMutation.isPending}>
              {activateTldMutation.isPending ? 'Activating...' : 'Activate'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// --- TLD section (ported from /super/settings) ---
function TldSection({ tlds, onAdd, onActivate, onDeactivate, onDelete }: {
  tlds: TldEntry[]
  onAdd: () => void
  onActivate: (tld: TldEntry) => void
  onDeactivate: (tld: TldEntry) => void
  onDelete: (tld: TldEntry) => void
}) {
  const activeCount = tlds.filter((t) => t.is_active).length
  if (tlds.length === 0) {
    return (
      <div>
        <p className="text-sm text-gray-500 mb-3">No domains registered</p>
        <Button size="sm" variant="outline" onClick={onAdd}>+ Add Domain</Button>
      </div>
    )
  }
  return (
    <div className="space-y-2">
      {activeCount > 1 && <p className="text-xs text-blue-600">{activeCount} active — multi-active pool</p>}
      {tlds.map((tld) => (
        <div key={tld.id} className="flex items-center justify-between p-3 border rounded-md">
          <div className="flex items-center gap-2">
            <span className={`w-3 h-3 rounded-full ${tld.is_active ? 'bg-green-500' : 'bg-gray-300'}`} />
            <span className="font-medium text-sm">{tld.domain}</span>
            <span className="text-xs text-gray-500">({tld.dns_provider})</span>
          </div>
          <div className="flex gap-2 items-center">
            {tld.is_active ? (
              <>
                <span className="text-xs font-medium text-green-600 px-2 py-1 bg-green-50 rounded">Active</span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onDeactivate(tld)}
                  disabled={activeCount <= 1}
                  title={activeCount <= 1 ? 'Activate another domain first' : 'Remove from the active pool (migrates affected admins)'}
                >
                  Deactivate
                </Button>
              </>
            ) : (
              <>
                <Button size="sm" variant="outline" onClick={() => onActivate(tld)}>Activate</Button>
                <Button size="sm" variant="ghost" className="text-red-500 hover:text-red-700" onClick={() => onDelete(tld)}>Remove</Button>
              </>
            )}
          </div>
        </div>
      ))}
      <Button size="sm" variant="outline" className="mt-2" onClick={onAdd}>+ Add Domain</Button>
    </div>
  )
}

// --- Assignment matrix (new) ---
function AssignmentMatrix() {
  const queryClient = useQueryClient()
  const { data: tldData } = useQuery({ queryKey: ['tlds'], queryFn: () => api.superAdmin.listTlds() })
  const { data: assignsResp, isLoading } = useQuery({
    queryKey: ['super', 'tld-assignments'],
    queryFn: () => api.superAdmin.getTldAssignments(),
  })

  const pinMutation = useMutation({
    mutationFn: (vars: { admin_id: number; purpose: string; tld_id: number | null }) =>
      api.superAdmin.setTldPin(vars),
    onSuccess: () => {
      toast.success('Assignment updated')
      queryClient.invalidateQueries({ queryKey: ['super', 'tld-assignments'] })
      queryClient.invalidateQueries({ queryKey: ['super', 'tld-analytics'] })
    },
    onError: (err: any) => toast.error(err.response?.data?.detail || 'Failed to update assignment'),
  })

  const tldsByPurpose: TldListResponse = tldData || { fdm: [], subscription: [], dashboard: [], admin_panel: [] }
  const rows = assignsResp?.assignments || []

  return (
    <Card>
      <CardHeader>
        <CardTitle>Assignments</CardTitle>
        <p className="text-xs text-muted-foreground">
          pin = override; (default) = load-balanced (least active users)
        </p>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No active admins</p>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Admin</TableHead>
                  {PURPOSES.map((p) => <TableHead key={p}>{PURPOSE_LABEL[p]}</TableHead>)}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((a) => (
                  <TableRow key={a.admin_id}>
                    <TableCell className="font-medium">{a.username}</TableCell>
                    {PURPOSES.map((purpose) => {
                      const cell = a.assignments[purpose]
                      const active = tldsByPurpose[purpose].filter((t) => t.is_active)
                      const current = cell.pinned_tld_id ?? cell.effective_tld_id
                      return (
                        <TableCell key={purpose}>
                          <Select
                            value={cell.pinned_tld_id ? String(cell.pinned_tld_id) : '__default__'}
                            onValueChange={(val) => pinMutation.mutate({
                              admin_id: a.admin_id,
                              purpose,
                              tld_id: val === '__default__' ? null : Number(val),
                            })}
                          >
                            <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="__default__">(default)</SelectItem>
                              {active.map((t) => (
                                <SelectItem key={t.id} value={String(t.id)}>{t.domain}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          {cell.source === 'lb' && current && (
                            <span className="text-[10px] text-muted-foreground">→ {current}</span>
                          )}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
