'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useSiteName } from '@/lib/branding'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { setAuthToken, setRefreshToken, setUserRole } from '@/lib/api/client'
import { useAuth } from '@/hooks/useAuth'
import type { UserResponse } from '@/types/api'
import { Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import type { LoginRequest } from '@/types/api'

export default function EndUserLoginPage() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const siteName = useSiteName()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  const loginMutation = useMutation({
    mutationFn: async (data: LoginRequest) => {
      return api.auth.login(data)
    },
    onSuccess: (data) => {
      setAuthToken(data.access_token)
      if (data.refresh_token) {
        setRefreshToken(data.refresh_token)
      }
      setUserRole(data.role)

      // Seed the auth cache so layout/useAuth sees the user immediately.
      // Without this, useAuth's query stays null (cached from initial no-token
      // load) until the next page refresh, and the dashboard renders as if
      // the user is still unauthenticated.
      queryClient.setQueryData(['auth', 'user'], {
        id: 0,
        username: data.username,
        role: data.role as UserResponse['role'],
        display_name: data.display_name,
        status: 'active',
      } satisfies UserResponse)
      // Force a refetch in the background to populate the real id + any
      // additional fields the login response doesn't include.
      queryClient.invalidateQueries({ queryKey: ['auth', 'user'] })

      toast.success(`Welcome, ${data.display_name || data.username}!`)
      router.push('/user/connections')
    },
    onError: (error: any) => {
      const message = error.response?.data?.detail || 'Login failed. Please check your credentials.'
      toast.error(message)
    },
  })

  // Redirect if already authenticated (side effect, not during render)
  useEffect(() => {
    if (isAuthenticated) {
      router.push('/user/connections')
    }
  }, [isAuthenticated, router])

  // Show spinner while verifying the existing session or while redirecting
  if (authLoading || isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-green-50 to-teal-100 dark:from-gray-900 dark:to-gray-800">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) return
    loginMutation.mutate({ username, password })
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-green-50 to-teal-100 dark:from-gray-900 dark:to-gray-800">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1 text-center">
          <div className="flex justify-center mb-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-foreground">
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
                  d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418"
                />
              </svg>
            </div>
          </div>
          <CardTitle className="text-2xl font-bold">{siteName}</CardTitle>
          <CardDescription>Sign in to your account</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="user-username">Username</Label>
              <Input
                id="user-username"
                type="text"
                placeholder="Enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                disabled={loginMutation.isPending}
                autoComplete="username"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="user-password">Password</Label>
              <Input
                id="user-password"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={loginMutation.isPending}
                autoComplete="current-password"
              />
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={loginMutation.isPending}
            >
              {loginMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Signing in...
                </>
              ) : (
                'Sign In'
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
