'use client'

import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { useRouter } from 'next/navigation'
import { TicketResponse } from '@/types/api'
import { TicketsTable } from '@/components/support/TicketsTable'
import { TicketFilters, TicketFilters as TicketFiltersType } from '@/components/support/TicketFilters'
import { TicketStats } from '@/components/support/TicketStats'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { MessageSquare, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'

export default function SupportPage() {
  const { user, isLoading: authLoading, isAuthenticated } = useAuth()
  const router = useRouter()
  const queryClient = useQueryClient()

  // State
  const [filters, setFilters] = React.useState<TicketFiltersType>({
    search: '',
    status: 'all',
    priority: 'all',
    category: 'all',
    assigned: 'all',
  })
  const [selectedTicketIds, setSelectedTicketIds] = React.useState<number[]>([])

  // Redirect if not authenticated
  React.useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [authLoading, isAuthenticated, router])

  // Fetch tickets
  const { data: tickets, isLoading: ticketsLoading } = useQuery({
    queryKey: ['tickets', filters],
    queryFn: async () => {
      const params: any = {}

      if (filters.search) {
        params.search = filters.search
      }
      if (filters.status && filters.status !== 'all') {
        params.status_filter = filters.status
      }
      if (filters.priority && filters.priority !== 'all') {
        params.priority_filter = filters.priority
      }
      if (filters.category && filters.category !== 'all') {
        params.category_filter = filters.category
      }
      if (filters.assigned === 'assigned') {
        params.assigned_filter = true
      } else if (filters.assigned === 'unassigned') {
        params.assigned_filter = false
      }

      return api.support.listAllTickets(params)
    },
    enabled: isAuthenticated && !!user?.is_admin,
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  // Fetch ticket stats
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['ticket-stats'],
    queryFn: api.support.getStats,
    enabled: isAuthenticated && !!user?.is_admin,
    refetchInterval: 30000,
  })

  // Assign ticket mutation
  const assignMutation = useMutation({
    mutationFn: (ticketId: number) => api.support.assignTicket(ticketId, user?.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tickets'] })
      queryClient.invalidateQueries({ queryKey: ['ticket-stats'] })
      toast.success('Ticket assigned to you')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to assign ticket')
    },
  })

  // Resolve ticket mutation
  const resolveMutation = useMutation({
    mutationFn: (ticketId: number) => api.support.resolveTicket(ticketId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tickets'] })
      queryClient.invalidateQueries({ queryKey: ['ticket-stats'] })
      toast.success('Ticket marked as resolved')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to resolve ticket')
    },
  })

  // Handlers
  const handleAssignTicket = (ticket: TicketResponse) => {
    assignMutation.mutate(ticket.id)
  }

  const handleResolveTicket = (ticket: TicketResponse) => {
    if (
      confirm(
        `Mark ticket ${ticket.ticket_number} as resolved?\n\nThis will notify the user that their issue has been addressed.`
      )
    ) {
      resolveMutation.mutate(ticket.id)
    }
  }

  const handleClearFilters = () => {
    setFilters({
      search: '',
      status: 'all',
      priority: 'all',
      category: 'all',
      assigned: 'all',
    })
  }

  // Loading state
  if (authLoading || (ticketsLoading && !tickets)) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-primary" />
          <p className="text-muted-foreground">Loading tickets...</p>
        </div>
      </div>
    )
  }

  // Access denied
  if (!user?.is_admin) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-2">Access Denied</h1>
          <p className="text-muted-foreground">Admin privileges required</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <MessageSquare className="h-8 w-8" />
          Support Tickets
        </h1>
        <p className="text-muted-foreground mt-1">
          Manage customer support requests and inquiries
        </p>
      </div>

      {/* Stats Cards */}
      <TicketStats stats={stats} loading={statsLoading} />

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
          <CardDescription>Filter tickets by status, priority, category, and more</CardDescription>
        </CardHeader>
        <CardContent>
          <TicketFilters
            filters={filters}
            onFiltersChange={setFilters}
            onClear={handleClearFilters}
          />
        </CardContent>
      </Card>

      {/* Tickets Table */}
      <Card>
        <CardHeader>
          <CardTitle>All Tickets ({tickets?.length || 0})</CardTitle>
          <CardDescription>
            Click on any ticket to view details and respond
          </CardDescription>
        </CardHeader>
        <CardContent>
          <TicketsTable
            data={tickets || []}
            loading={ticketsLoading}
            onAssign={handleAssignTicket}
            onResolve={handleResolveTicket}
            selectedTickets={selectedTicketIds}
            onSelectTickets={setSelectedTicketIds}
          />
        </CardContent>
      </Card>
    </div>
  )
}
