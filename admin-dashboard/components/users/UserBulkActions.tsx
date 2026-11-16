'use client'

import React from 'react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { UserResponse } from '@/types/api'
import { Download, Trash2, FileJson, ChevronDown } from 'lucide-react'

interface UserBulkActionsProps {
  selectedUsers: UserResponse[]
  onDelete?: (users: UserResponse[]) => void
  disabled?: boolean
}

export function UserBulkActions({
  selectedUsers,
  onDelete,
  disabled = false,
}: UserBulkActionsProps) {
  const [showDeleteDialog, setShowDeleteDialog] = React.useState(false)

  const exportToCSV = () => {
    if (selectedUsers.length === 0) return

    // CSV headers
    const headers = [
      'ID',
      'Username',
      'Email',
      'Wallet Balance',
      'Total Referrals',
      'Referral Tier',
      'Referral Earnings',
      'Trial Used',
      'Created At',
    ]

    // CSV rows
    const rows = selectedUsers.map((user) => [
      user.id,
      user.telegram_username || '',
      user.email || '',
      user.wallet_balance,
      user.total_referrals,
      user.referral_tier,
      user.referral_earnings_usd,
      user.trial_used ? 'Yes' : 'No',
      user.created_at,
    ])

    // Create CSV content
    const csvContent = [
      headers.join(','),
      ...rows.map((row) =>
        row.map((cell) => `"${cell}"`).join(',')
      ),
    ].join('\n')

    // Download CSV
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.setAttribute('href', url)
    link.setAttribute(
      'download',
      `users_export_${new Date().toISOString().split('T')[0]}.csv`
    )
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const exportToJSON = () => {
    if (selectedUsers.length === 0) return

    // Create JSON content
    const jsonContent = JSON.stringify(selectedUsers, null, 2)

    // Download JSON
    const blob = new Blob([jsonContent], { type: 'application/json;charset=utf-8;' })
    const link = document.createElement('a')
    const url = URL.createObjectURL(blob)
    link.setAttribute('href', url)
    link.setAttribute(
      'download',
      `users_export_${new Date().toISOString().split('T')[0]}.json`
    )
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const handleDelete = () => {
    if (onDelete && selectedUsers.length > 0) {
      onDelete(selectedUsers)
      setShowDeleteDialog(false)
    }
  }

  const count = selectedUsers.length

  if (count === 0) {
    return null
  }

  return (
    <>
      <div className="flex items-center gap-2">
        <div className="text-sm text-muted-foreground">
          {count} user{count !== 1 ? 's' : ''} selected
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" disabled={disabled}>
              Export
              <ChevronDown className="ml-2 h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuLabel>Export Format</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={exportToCSV}>
              <Download className="mr-2 h-4 w-4" />
              Export as CSV
            </DropdownMenuItem>
            <DropdownMenuItem onClick={exportToJSON}>
              <FileJson className="mr-2 h-4 w-4" />
              Export as JSON
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {onDelete && (
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setShowDeleteDialog(true)}
            disabled={disabled}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            Delete ({count})
          </Button>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete{' '}
              <strong>{count}</strong> user{count !== 1 ? 's' : ''} and remove all their
              data from the system.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete {count} user{count !== 1 ? 's' : ''}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
