'use client'

import React from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import * as z from 'zod'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { UserResponse } from '@/types/api'
import { Loader2 } from 'lucide-react'

const editUserSchema = z.object({
  telegram_username: z.string().min(1, 'Username is required').optional(),
  email: z.string().email('Invalid email address').or(z.literal('')).optional(),
  language: z.string().min(2, 'Language code required'),
  wallet_balance: z.coerce
    .number()
    .min(0, 'Balance cannot be negative')
    .optional(),
})

type EditUserFormValues = z.infer<typeof editUserSchema>

interface EditUserFormProps {
  user: UserResponse | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (data: EditUserFormValues) => Promise<void>
  loading?: boolean
}

export function EditUserForm({
  user,
  open,
  onOpenChange,
  onSubmit,
  loading = false,
}: EditUserFormProps) {
  const form = useForm<EditUserFormValues>({
    resolver: zodResolver(editUserSchema),
    defaultValues: {
      telegram_username: user?.telegram_username || '',
      email: user?.email || '',
      language: user?.language || 'en',
      wallet_balance: parseFloat(user?.wallet_balance || '0'),
    },
  })

  // Reset form when user changes
  React.useEffect(() => {
    if (user) {
      form.reset({
        telegram_username: user.telegram_username || '',
        email: user.email || '',
        language: user.language || 'en',
        wallet_balance: parseFloat(user.wallet_balance || '0'),
      })
    }
  }, [user, form])

  const handleSubmit = async (data: EditUserFormValues) => {
    try {
      await onSubmit(data)
      onOpenChange(false)
    } catch (error) {
      // Error handling will be done by parent component
      console.error('Form submission error:', error)
    }
  }

  if (!user) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Edit User</DialogTitle>
          <DialogDescription>
            Update user information for #{user.id} - {user.telegram_username || 'No username'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
            {/* Username */}
            <FormField
              control={form.control}
              name="telegram_username"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Telegram Username</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Enter username"
                      {...field}
                      value={field.value || ''}
                    />
                  </FormControl>
                  <FormDescription>
                    User&apos;s Telegram username (without @)
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Email */}
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email Address</FormLabel>
                  <FormControl>
                    <Input
                      type="email"
                      placeholder="user@example.com"
                      {...field}
                      value={field.value || ''}
                    />
                  </FormControl>
                  <FormDescription>
                    User&apos;s email address (optional)
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Language */}
            <FormField
              control={form.control}
              name="language"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Language</FormLabel>
                  <Select
                    onValueChange={field.onChange}
                    defaultValue={field.value}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select language" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="en">English</SelectItem>
                      <SelectItem value="fa">Persian (فارسی)</SelectItem>
                      <SelectItem value="ar">Arabic (العربية)</SelectItem>
                      <SelectItem value="ru">Russian (Русский)</SelectItem>
                      <SelectItem value="zh">Chinese (中文)</SelectItem>
                      <SelectItem value="es">Spanish (Español)</SelectItem>
                      <SelectItem value="fr">French (Français)</SelectItem>
                      <SelectItem value="de">German (Deutsch)</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    User&apos;s preferred language
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Wallet Balance */}
            <FormField
              control={form.control}
              name="wallet_balance"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Wallet Balance (USD)</FormLabel>
                  <FormControl>
                    <div className="relative">
                      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                        $
                      </span>
                      <Input
                        type="number"
                        step="0.01"
                        min="0"
                        placeholder="0.00"
                        className="pl-7"
                        {...field}
                        value={field.value || 0}
                      />
                    </div>
                  </FormControl>
                  <FormDescription>
                    User&apos;s wallet balance in USD
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={loading}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Save Changes
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
