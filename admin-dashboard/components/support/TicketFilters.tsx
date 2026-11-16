'use client'

import React from 'react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Search, X } from 'lucide-react'

export interface TicketFilters {
  search?: string
  status?: 'all' | 'open' | 'in_progress' | 'waiting_customer' | 'resolved' | 'closed'
  priority?: 'all' | 'low' | 'medium' | 'high' | 'urgent'
  category?: 'all' | 'technical' | 'billing' | 'account' | 'feature_request' | 'other'
  assigned?: 'all' | 'assigned' | 'unassigned'
}

interface TicketFiltersProps {
  filters: TicketFilters
  onFiltersChange: (filters: TicketFilters) => void
  onClear: () => void
}

export function TicketFilters({
  filters,
  onFiltersChange,
  onClear,
}: TicketFiltersProps) {
  const [searchValue, setSearchValue] = React.useState(filters.search || '')

  // Debounced search
  React.useEffect(() => {
    const timer = setTimeout(() => {
      onFiltersChange({ ...filters, search: searchValue })
    }, 300)

    return () => clearTimeout(timer)
  }, [searchValue])

  const handleSearchChange = (value: string) => {
    setSearchValue(value)
  }

  const handleStatusChange = (value: string) => {
    onFiltersChange({
      ...filters,
      status: value as TicketFilters['status'],
    })
  }

  const handlePriorityChange = (value: string) => {
    onFiltersChange({
      ...filters,
      priority: value as TicketFilters['priority'],
    })
  }

  const handleCategoryChange = (value: string) => {
    onFiltersChange({
      ...filters,
      category: value as TicketFilters['category'],
    })
  }

  const handleAssignedChange = (value: string) => {
    onFiltersChange({
      ...filters,
      assigned: value as TicketFilters['assigned'],
    })
  }

  const hasActiveFilters =
    filters.search ||
    filters.status !== 'all' ||
    filters.priority !== 'all' ||
    filters.category !== 'all' ||
    filters.assigned !== 'all'

  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
      <div className="flex flex-1 flex-col gap-4 md:flex-row md:items-center">
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search by ticket # or subject..."
            value={searchValue}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="pl-9"
          />
        </div>

        {/* Status Filter */}
        <Select
          value={filters.status || 'all'}
          onValueChange={handleStatusChange}
        >
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="open">Open</SelectItem>
            <SelectItem value="in_progress">In Progress</SelectItem>
            <SelectItem value="waiting_customer">Waiting Customer</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
            <SelectItem value="closed">Closed</SelectItem>
          </SelectContent>
        </Select>

        {/* Priority Filter */}
        <Select
          value={filters.priority || 'all'}
          onValueChange={handlePriorityChange}
        >
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Priority" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Priority</SelectItem>
            <SelectItem value="low">Low</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="urgent">Urgent</SelectItem>
          </SelectContent>
        </Select>

        {/* Category Filter */}
        <Select
          value={filters.category || 'all'}
          onValueChange={handleCategoryChange}
        >
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Category" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Categories</SelectItem>
            <SelectItem value="technical">Technical</SelectItem>
            <SelectItem value="billing">Billing</SelectItem>
            <SelectItem value="account">Account</SelectItem>
            <SelectItem value="feature_request">Feature Request</SelectItem>
            <SelectItem value="other">Other</SelectItem>
          </SelectContent>
        </Select>

        {/* Assignment Filter */}
        <Select
          value={filters.assigned || 'all'}
          onValueChange={handleAssignedChange}
        >
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Assignment" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Tickets</SelectItem>
            <SelectItem value="assigned">Assigned</SelectItem>
            <SelectItem value="unassigned">Unassigned</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Clear Filters */}
      {hasActiveFilters && (
        <Button variant="ghost" onClick={onClear} className="h-9 px-3">
          <X className="mr-2 h-4 w-4" />
          Clear filters
        </Button>
      )}
    </div>
  )
}
