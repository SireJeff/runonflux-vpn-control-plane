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
import { Search, X, Calendar } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Calendar as CalendarComponent } from '@/components/ui/calendar'
import { format } from 'date-fns'
import { cn } from '@/lib/utils'

export interface UserFilters {
  search?: string
  status?: 'all' | 'new' | 'trial' | 'active'
  tier?: 'all' | 'bronze' | 'silver' | 'gold' | 'platinum'
  dateFrom?: Date
  dateTo?: Date
}

interface UserTableFiltersProps {
  filters: UserFilters
  onFiltersChange: (filters: UserFilters) => void
  onClear: () => void
}

export function UserTableFilters({
  filters,
  onFiltersChange,
  onClear,
}: UserTableFiltersProps) {
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
      status: value as UserFilters['status'],
    })
  }

  const handleTierChange = (value: string) => {
    onFiltersChange({
      ...filters,
      tier: value as UserFilters['tier'],
    })
  }

  const handleDateFromChange = (date: Date | undefined) => {
    onFiltersChange({
      ...filters,
      dateFrom: date,
    })
  }

  const handleDateToChange = (date: Date | undefined) => {
    onFiltersChange({
      ...filters,
      dateTo: date,
    })
  }

  const hasActiveFilters =
    filters.search ||
    filters.status !== 'all' ||
    filters.tier !== 'all' ||
    filters.dateFrom ||
    filters.dateTo

  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
      <div className="flex flex-1 flex-col gap-4 md:flex-row md:items-center">
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search by username, email, referral code..."
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
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="new">New</SelectItem>
            <SelectItem value="trial">Trial</SelectItem>
            <SelectItem value="active">Active</SelectItem>
          </SelectContent>
        </Select>

        {/* Tier Filter */}
        <Select value={filters.tier || 'all'} onValueChange={handleTierChange}>
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Tier" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Tiers</SelectItem>
            <SelectItem value="bronze">Bronze</SelectItem>
            <SelectItem value="silver">Silver</SelectItem>
            <SelectItem value="gold">Gold</SelectItem>
            <SelectItem value="platinum">Platinum</SelectItem>
          </SelectContent>
        </Select>

        {/* Date Range - From */}
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              className={cn(
                'w-[180px] justify-start text-left font-normal',
                !filters.dateFrom && 'text-muted-foreground'
              )}
            >
              <Calendar className="mr-2 h-4 w-4" />
              {filters.dateFrom ? (
                format(filters.dateFrom, 'PPP')
              ) : (
                <span>From date</span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <CalendarComponent
              mode="single"
              selected={filters.dateFrom}
              onSelect={handleDateFromChange}
              initialFocus
            />
          </PopoverContent>
        </Popover>

        {/* Date Range - To */}
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              className={cn(
                'w-[180px] justify-start text-left font-normal',
                !filters.dateTo && 'text-muted-foreground'
              )}
            >
              <Calendar className="mr-2 h-4 w-4" />
              {filters.dateTo ? (
                format(filters.dateTo, 'PPP')
              ) : (
                <span>To date</span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <CalendarComponent
              mode="single"
              selected={filters.dateTo}
              onSelect={handleDateToChange}
              initialFocus
            />
          </PopoverContent>
        </Popover>
      </div>

      {/* Clear Filters */}
      {hasActiveFilters && (
        <Button
          variant="ghost"
          onClick={onClear}
          className="h-9 px-3"
        >
          <X className="mr-2 h-4 w-4" />
          Clear filters
        </Button>
      )}
    </div>
  )
}
