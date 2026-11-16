"use client"

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Users,
  BarChart3,
  Wallet,
  Server,
  Settings,
  Menu,
  LogOut,
  Bot,
  Package,
  ShoppingCart,
  Gift,
  Sparkles,
  Route,
  HelpCircle,
  Send,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet'
import { useAuth } from '@/hooks/useAuth'
import { HelpButton } from '@/components/help/HelpButton'

interface NavItem {
  title: string
  href: string
  icon: React.ComponentType<{ className?: string }>
  badge?: string
}

const navItems: NavItem[] = [
  {
    title: 'Dashboard',
    href: '/dashboard',
    icon: LayoutDashboard,
  },
  {
    title: 'Users',
    href: '/dashboard/users',
    icon: Users,
  },
  {
    title: 'Wallet',
    href: '/dashboard/wallet',
    icon: Wallet,
  },
  {
    title: 'Analytics',
    href: '/dashboard/analytics',
    icon: BarChart3,
  },
  {
    title: 'Bot Config',
    href: '/dashboard/bot-config',
    icon: Bot,
  },
  {
    title: 'Broadcasts',
    href: '/dashboard/broadcasts',
    icon: Send,
  },
  {
    title: 'Packages',
    href: '/dashboard/packages',
    icon: Package,
  },
  {
    title: 'Free Config',
    href: '/dashboard/free-config',
    icon: Sparkles,
  },
  {
    title: 'Routing Rules',
    href: '/dashboard/routing-rules',
    icon: Route,
  },
  {
    title: 'Orders',
    href: '/dashboard/orders',
    icon: ShoppingCart,
  },
  {
    title: 'Referral',
    href: '/dashboard/referral',
    icon: Gift,
  },
  {
    title: 'Help',
    href: '/dashboard/help',
    icon: HelpCircle,
  },
  {
    title: 'Settings',
    href: '/dashboard/settings',
    icon: Settings,
  },
]

interface SidebarContentProps {
  onNavigate?: () => void
}

function SidebarContent({ onNavigate }: SidebarContentProps) {
  const pathname = usePathname()
  const { user, logout } = useAuth()

  return (
    <div className="flex h-full flex-col">
      {/* Logo/Header */}
      <div className="border-b px-6 py-4">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
            <Server className="h-5 w-5 text-primary-foreground" />
          </div>
          <div>
            <h2 className="text-lg font-bold">FluxVPN</h2>
            <p className="text-xs text-muted-foreground">Admin Panel</p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <ScrollArea className="flex-1 px-3 py-4">
        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon
            const isActive = pathname === item.href

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                className={cn(
                  "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <Icon className={cn(
                  "h-4 w-4",
                  isActive ? "text-primary-foreground" : "text-muted-foreground group-hover:text-accent-foreground"
                )} />
                <span>{item.title}</span>
                {item.badge && (
                  <span className="ml-auto rounded-full bg-primary px-2 py-0.5 text-xs text-primary-foreground">
                    {item.badge}
                  </span>
                )}
              </Link>
            )
          })}
        </nav>
      </ScrollArea>

      {/* Footer - User info + Logout */}
      <div className="border-t p-4 space-y-3">
        <div className="px-2">
          <p className="text-sm font-medium truncate">{user?.display_name || user?.username || '—'}</p>
          <p className="text-xs text-muted-foreground capitalize">
            {user?.role === 'admin' ? 'Reseller' : user?.role || ''}
          </p>
        </div>
        <Button
          variant="ghost"
          className="w-full justify-start gap-3 text-muted-foreground hover:text-destructive"
          onClick={() => logout()}
        >
          <LogOut className="h-4 w-4" />
          Logout
        </Button>
      </div>
    </div>
  )
}

// Desktop Sidebar
export function Sidebar() {
  return (
    <aside className="hidden border-r bg-background lg:block lg:w-64">
      <SidebarContent />
    </aside>
  )
}

// Mobile Sidebar
export function MobileSidebar() {
  const [open, setOpen] = React.useState(false)

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          aria-label="Toggle navigation menu"
        >
          <Menu className="h-5 w-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-64 p-0">
        <SidebarContent onNavigate={() => setOpen(false)} />
      </SheetContent>
    </Sheet>
  )
}

// Header component for the top navigation bar
export function Header() {
  const { user } = useAuth()

  return (
    <header className="sticky top-0 z-40 border-b bg-background">
      <div className="flex h-16 items-center gap-4 px-6">
        <MobileSidebar />

        <div className="flex flex-1 items-center justify-between">
          <div className="lg:hidden">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
                <Server className="h-5 w-5 text-primary-foreground" />
              </div>
              <h2 className="text-lg font-bold">FluxVPN</h2>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-4">
            <HelpButton />
            {user && (
              <span className="hidden sm:inline text-sm text-muted-foreground">
                {user.display_name || user.username}
              </span>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}
