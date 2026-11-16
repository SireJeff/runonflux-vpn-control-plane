'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useRouter } from 'next/navigation'
import {
  LayoutDashboard,
  Users,
  ShoppingCart,
  Server,
  BarChart3,
  Globe,
  Settings,
  Menu,
  X,
  LogOut,
  Shield,
  HelpCircle,
  Gift,
  Radio,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet'
import { useAuth } from '@/hooks/useAuth'
import React from 'react'
import { HelpButton } from '@/components/help/HelpButton'

interface NavItem {
  title: string
  href: string
  icon: React.ComponentType<{ className?: string }>
  badge?: string
}

const superAdminNavItems: NavItem[] = [
  {
    title: 'Dashboard',
    href: '/super/dashboard',
    icon: LayoutDashboard,
  },
  {
    title: 'Admins',
    href: '/super/admins',
    icon: Users,
  },
  {
    title: 'Orders',
    href: '/super/orders',
    icon: ShoppingCart,
  },
  {
    title: 'Apps',
    href: '/super/apps',
    icon: Server,
  },
  {
    title: 'Domains',
    href: '/super/domains',
    icon: Globe,
  },
  {
    title: 'Analytics',
    href: '/super/analytics',
    icon: BarChart3,
  },
  {
    title: 'Free Config',
    href: '/super/free-config',
    icon: Gift,
  },
  {
    title: 'Broadcasts',
    href: '/super/broadcasts',
    icon: Radio,
  },
  {
    title: 'Help',
    href: '/super/help',
    icon: HelpCircle,
  },
  {
    title: 'Settings',
    href: '/super/settings',
    icon: Settings,
  },
]

interface SidebarContentProps {
  onNavigate?: () => void
}

function SuperAdminSidebarContent({ onNavigate }: SidebarContentProps) {
  const pathname = usePathname()
  const { logout, user } = useAuth()

  const handleLogout = () => {
    logout()
  }

  return (
    <div className="flex h-full flex-col">
      {/* Logo/Header */}
      <div className="border-b px-6 py-4">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
            <Shield className="h-5 w-5 text-primary-foreground" />
          </div>
          <div>
            <h2 className="text-lg font-bold">FluxVPN</h2>
            <p className="text-xs text-muted-foreground">Super Admin</p>
          </div>
        </div>
      </div>

      {/* User info */}
      {user && (
        <div className="border-b px-6 py-3">
          <p className="text-sm font-medium">{user.display_name || user.username}</p>
          <p className="text-xs text-muted-foreground capitalize">{user.role?.replace('_', ' ')}</p>
        </div>
      )}

      {/* Navigation */}
      <ScrollArea className="flex-1 px-3 py-4">
        <nav className="space-y-1">
          {superAdminNavItems.map((item) => {
            const Icon = item.icon
            const isActive = pathname === item.href

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                className={cn(
                  'group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all',
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                )}
              >
                <Icon
                  className={cn(
                    'h-4 w-4',
                    isActive
                      ? 'text-primary-foreground'
                      : 'text-muted-foreground group-hover:text-accent-foreground'
                  )}
                />
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

      {/* Footer - Logout */}
      <div className="border-t p-4">
        <Button
          variant="ghost"
          className="w-full justify-start gap-3 text-muted-foreground hover:text-destructive"
          onClick={handleLogout}
        >
          <LogOut className="h-4 w-4" />
          Logout
        </Button>
      </div>
    </div>
  )
}

// Desktop Sidebar
function SuperAdminSidebar() {
  return (
    <aside className="hidden border-r bg-background lg:block lg:w-64">
      <SuperAdminSidebarContent />
    </aside>
  )
}

// Mobile Sidebar
function SuperAdminMobileSidebar() {
  const [open, setOpen] = React.useState(false)

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Toggle navigation menu">
          <Menu className="h-5 w-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-64 p-0">
        <SuperAdminSidebarContent onNavigate={() => setOpen(false)} />
      </SheetContent>
    </Sheet>
  )
}

// Header
function SuperAdminHeader() {
  const { user } = useAuth()
  const pathname = usePathname()

  // Derive page title from pathname
  const pageTitle = superAdminNavItems.find((item) => item.href === pathname)?.title || 'Dashboard'

  return (
    <header className="sticky top-0 z-40 border-b bg-background">
      <div className="flex h-16 items-center gap-4 px-6">
        <SuperAdminMobileSidebar />

        <div className="flex flex-1 items-center justify-between">
          <div className="lg:hidden">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
                <Shield className="h-5 w-5 text-primary-foreground" />
              </div>
              <h2 className="text-lg font-bold">FluxVPN</h2>
            </div>
          </div>

          <h1 className="hidden lg:block text-lg font-semibold">{pageTitle}</h1>

          <div className="ml-auto flex items-center gap-3">
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

export default function SuperAdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Desktop Sidebar */}
      <SuperAdminSidebar />

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header with Mobile Menu */}
        <SuperAdminHeader />

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto bg-muted/40 p-6">{children}</main>
      </div>
    </div>
  )
}
