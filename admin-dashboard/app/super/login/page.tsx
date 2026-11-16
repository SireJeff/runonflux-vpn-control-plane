'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { setAuthToken, setRefreshToken, setUserRole } from '@/lib/api/client'
import type { LoginRequest } from '@/types/api'

export default function SuperAdminLoginPage() {
  const router = useRouter()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const loginMutation = useMutation({
    mutationFn: async (data: LoginRequest) => {
      const response = await api.auth.login(data)
      return response
    },
    onSuccess: (data) => {
      if (data.role !== 'super_admin') {
        return
      }
      setAuthToken(data.access_token)
      if (data.refresh_token) {
        setRefreshToken(data.refresh_token)
      }
      setUserRole(data.role)
      router.push('/super/dashboard')
    },
    onError: (error: any) => {
      // Error handled by axios interceptor
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) return
    loginMutation.mutate({ username, password })
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-purple-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1 text-center">
          <div className="flex justify-center mb-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-purple-600 text-white">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
                className="h-8 w-8"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.745 3.745 0 011.043 3.296A3.745 3.745 0 0121 12z"
                />
              </svg>
            </div>
          </div>
          <CardTitle className="text-2xl font-bold">Super Admin</CardTitle>
          <CardDescription>FluxVPN platform management</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="sa-username">Username</Label>
              <Input
                id="sa-username"
                type="text"
                placeholder="Super admin username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                disabled={loginMutation.isPending}
                autoComplete="username"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="sa-password">Password</Label>
              <Input
                id="sa-password"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={loginMutation.isPending}
                autoComplete="current-password"
              />
            </div>

            <Button type="submit" className="w-full" disabled={loginMutation.isPending}>
              {loginMutation.isPending ? 'Signing in...' : 'Sign In'}
            </Button>
          </form>

          <div className="mt-6 text-center text-sm text-muted-foreground">
            <Link href="/login" className="text-primary underline-offset-4 hover:underline">
              Back to standard login
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
