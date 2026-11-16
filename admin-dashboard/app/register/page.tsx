'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { RegisterRequest } from '@/types/api'

export default function RegisterPage() {
  const router = useRouter()

  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [telegramId, setTelegramId] = useState('')
  const [whatsapp, setWhatsapp] = useState('')
  const [phone, setPhone] = useState('')
  const [notes, setNotes] = useState('')

  const registerMutation = useMutation({
    mutationFn: async (data: RegisterRequest) => {
      const response = await api.auth.register(data)
      return response
    },
    onSuccess: () => {
      router.push('/login?registered=true')
    },
    onError: (error: any) => {
      // Error is handled by axios interceptor, but we can add specific handling here
      const detail = error.response?.data?.detail
      if (detail) {
        // toast already shown by interceptor for most cases
      }
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    const data: RegisterRequest = {
      username,
      telegram_id: telegramId,
      display_name: displayName || undefined,
      whatsapp_number: whatsapp || undefined,
      phone_number: phone || undefined,
      notes: notes || undefined,
    }

    registerMutation.mutate(data)
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
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
                  d="M19 7.5v3m0 0v3m0-3h3m-3 0h-3m-2.25-4.125a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zM4 19.235v-.11a6.375 6.375 0 0112.75 0v.109A12.318 12.318 0 0110.374 21c-2.331 0-4.512-.645-6.374-1.766z"
                />
              </svg>
            </div>
          </div>
          <CardTitle className="text-2xl font-bold">Register</CardTitle>
          <CardDescription>Create an admin account</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username *</Label>
              <Input
                id="username"
                type="text"
                placeholder="3-50 characters"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                disabled={registerMutation.isPending}
                minLength={3}
                maxLength={50}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="display_name">Display Name (Optional)</Label>
              <Input
                id="display_name"
                type="text"
                placeholder="Your display name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                disabled={registerMutation.isPending}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="telegram_id">Telegram ID *</Label>
              <Input
                id="telegram_id"
                type="text"
                placeholder="Your Telegram user ID"
                value={telegramId}
                onChange={(e) => setTelegramId(e.target.value)}
                required
                disabled={registerMutation.isPending}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="whatsapp">WhatsApp Number (Optional)</Label>
              <Input
                id="whatsapp"
                type="text"
                placeholder="+1234567890"
                value={whatsapp}
                onChange={(e) => setWhatsapp(e.target.value)}
                disabled={registerMutation.isPending}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="phone">Phone Number (Optional)</Label>
              <Input
                id="phone"
                type="text"
                placeholder="+1234567890"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                disabled={registerMutation.isPending}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="notes">Notes (Optional)</Label>
              <Textarea
                id="notes"
                placeholder="Any additional information"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                disabled={registerMutation.isPending}
                rows={3}
              />
            </div>

            <Button type="submit" className="w-full" disabled={registerMutation.isPending}>
              {registerMutation.isPending ? 'Submitting...' : 'Register'}
            </Button>
          </form>

          <div className="mt-6 text-center text-sm text-muted-foreground">
            <p>
              Already have an account?{' '}
              <Link href="/login" className="text-primary underline-offset-4 hover:underline">
                Sign in
              </Link>
            </p>
            <p className="mt-2">
              Registration requires admin approval before access is granted.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
