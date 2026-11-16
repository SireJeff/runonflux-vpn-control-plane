import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import toast from 'react-hot-toast'

/**
 * Merge Tailwind CSS classes with proper precedence
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Format currency to USD
 */
export function formatCurrency(amount: number | string): string {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num)
}

/**
 * Format date to relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(date: string | Date): string {
  const now = new Date()
  const then = new Date(date)
  const seconds = Math.floor((now.getTime() - then.getTime()) / 1000)

  const intervals = {
    year: 31536000,
    month: 2592000,
    week: 604800,
    day: 86400,
    hour: 3600,
    minute: 60,
  }

  for (const [unit, secondsInUnit] of Object.entries(intervals)) {
    const interval = Math.floor(seconds / secondsInUnit)
    if (interval >= 1) {
      return `${interval} ${unit}${interval > 1 ? 's' : ''} ago`
    }
  }

  return 'Just now'
}

/**
 * Format date to readable string
 */
export function formatDate(date: string | Date, includeTime: boolean = false): string {
  const d = new Date(date)

  if (includeTime) {
    return d.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/**
 * Format traffic (GB value) with megabyte precision.
 * - >= 1 GB → "X.XX GB" (2 decimals ≈ 10 MB resolution)
 * - >= 0.01 GB → "X.XX GB"
 * - > 0 → "X MB"
 * - 0 → "0 MB"
 */
export function formatTraffic(gb: number): string {
  if (gb >= 0.01) {
    return gb.toFixed(2) + ' GB'
  }
  const mb = Math.round(gb * 1024)
  if (mb > 0) {
    return mb + ' MB'
  }
  return '0 MB'
}

/**
 * Format a package snapshot's traffic value for display.
 * The backend order snapshot stores the numeric `traffic_gb` key
 * (see worker_api order_service snapshot). Returns "X.X GB" or "-".
 */
export function formatSnapshotTrafficGb(
  snapshot: { traffic_gb?: number } | null | undefined,
): string {
  const gb = snapshot?.traffic_gb
  return gb ? `${Number(gb).toFixed(1)} GB` : '-'
}

/**
 * Format number with abbreviations (1K, 1M, 1B)
 */
export function formatNumber(num: number): string {
  if (num >= 1000000000) {
    return (num / 1000000000).toFixed(1) + 'B'
  }
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

/**
 * Get percentage with sign and color
 */
export function formatPercentage(value: number | null): {
  text: string
  color: string
} {
  if (value === null || value === undefined) {
    return { text: 'N/A', color: 'text-muted-foreground' }
  }

  const sign = value > 0 ? '+' : ''
  const color = value > 0 ? 'text-green-600' : value < 0 ? 'text-red-600' : 'text-muted-foreground'

  return {
    text: `${sign}${value.toFixed(1)}%`,
    color,
  }
}

/**
 * Get status badge color
 */
export function getStatusColor(status: string): string {
  const statusColors: Record<string, string> = {
    // Subscription statuses
    active: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
    inactive: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
    expired: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',

    // Ticket statuses
    open: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
    in_progress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
    resolved: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
    closed: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',

    // Payment statuses
    pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
    completed: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
    failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',

    // Health statuses
    healthy: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
    unhealthy: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  }

  return statusColors[status.toLowerCase()] || 'bg-gray-100 text-gray-800'
}

/**
 * Get priority badge color
 */
export function getPriorityColor(priority: string): string {
  const priorityColors: Record<string, string> = {
    low: 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300',
    medium: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
    high: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
    urgent: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  }

  return priorityColors[priority.toLowerCase()] || 'bg-gray-100 text-gray-800'
}

/**
 * Truncate text with ellipsis
 */
export function truncate(text: string, length: number): string {
  if (text.length <= length) return text
  return text.substring(0, length) + '...'
}

/**
 * Copy text to clipboard
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    toast.success('Copied to clipboard')
    return true
  } catch (error) {
    toast.error('Failed to copy')
    return false
  }
}

/**
 * Generate display name from username by replacing underscores/hyphens with spaces
 * and capitalizing each word
 */
export function generateDisplayName(username: string): string {
  if (!username) return ''
  return username
    .replace(/[_\-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim()
}

/**
 * Generate remark for VPN user based on username
 */
export function generateRemark(username: string): string {
  if (!username) return ''
  return `VPN user – ${generateDisplayName(username)}`
}
