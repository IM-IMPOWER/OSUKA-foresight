'use client'

import { useState } from 'react'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useCreateYoutubeSource } from '@/lib/hooks/use-sources'
import { useTranslation } from '@/lib/hooks/use-translation'

const schema = z.object({
  url: z.string().url(),
})

type FormData = z.infer<typeof schema>

interface AddYoutubeSourceDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  notebookId: string
}

function isYoutubeUrl(url: string): boolean {
  return /(^https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)\//i.test(url)
}

export function AddYoutubeSourceDialog({ open, onOpenChange, notebookId }: AddYoutubeSourceDialogProps) {
  const { t } = useTranslation()
  const [submitting, setSubmitting] = useState(false)
  const createYoutube = useCreateYoutubeSource()

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { url: '' },
  })

  const onSubmit = async (data: FormData) => {
    if (!isYoutubeUrl(data.url)) {
      toast.error(t.sources.invalidYoutubeUrl)
      return
    }
    try {
      setSubmitting(true)
      await createYoutube.mutateAsync({ url: data.url, notebookId })
      reset()
      onOpenChange(false)
    } catch {
      // errors handled in hook
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>{t.sources.addYoutube}</DialogTitle>
          <DialogDescription>{t.sources.addYoutubeDesc}</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Input
              placeholder="https://www.youtube.com/watch?v=..."
              {...register('url')}
            />
            {errors.url && (
              <p className="text-xs text-destructive">{errors.url.message}</p>
            )}
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t.common.cancel}
            </Button>
            <Button type="submit" disabled={submitting || createYoutube.isPending}>
              {submitting ? t.common.adding : t.common.add}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
