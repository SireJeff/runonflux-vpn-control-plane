import { Sidebar, Header } from '@/components/Sidebar'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Desktop Sidebar */}
      <Sidebar />

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header with Mobile Menu */}
        <Header />

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto bg-muted/40 p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
