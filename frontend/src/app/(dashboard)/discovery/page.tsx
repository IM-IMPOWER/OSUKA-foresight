'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

import { AppShell } from '@/components/layout/AppShell'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { useTranslation } from '@/lib/hooks/use-translation'
import { osukaApi, OsukaRunResponse, OsukaRunStatusResponse } from '@/lib/api/osuka'
import { toast } from 'sonner'
import ReactMarkdown from 'react-markdown'

type RunState = {
  response?: OsukaRunResponse
  error?: string
}

export default function OsukaPage() {
  const { t } = useTranslation()
  const [category, setCategory] = useState('')
  const [market, setMarket] = useState('')
  const [allowExternal, setAllowExternal] = useState(true)
  const [preferPdfs, setPreferPdfs] = useState(false)
  const [preferredBrands, setPreferredBrands] = useState('')
  const [maxTotal, setMaxTotal] = useState('10')
  const [loading, setLoading] = useState(false)
  const [runState, setRunState] = useState<RunState>({})
  const [debugOpen, setDebugOpen] = useState(true)
  const [localLogs, setLocalLogs] = useState<string[]>([])
  const [runId, setRunId] = useState<string | null>(null)
  const [runStatus, setRunStatus] = useState<OsukaRunStatusResponse | null>(null)

  useEffect(() => {
    if (!runId) {
      return
    }

    let cancelled = false
    const poll = async () => {
      try {
        const status = await osukaApi.status(runId)
        if (cancelled) {
          return
        }
        setRunStatus(status)
        if (status.status === 'completed' && status.result) {
          setRunState({ response: status.result })
          setRunId(null)
          return
        }
        if (status.status === 'failed') {
          setRunState({ error: status.error || t.common.error })
          setRunId(null)
          return
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : t.common.error
          setRunState({ error: message })
          setRunId(null)
        }
      }
    }

    const interval = setInterval(poll, 2000)
    poll()

    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [runId, t.common.error])

  const handleRun = async () => {
    if (!category.trim()) {
      toast.error(t.common.required)
      return
    }

    setLoading(true)
    setRunState({})
    setLocalLogs([t.osuka.logsStarting])
    setRunStatus(null)

    const preferredList = preferredBrands
      .split(',')
      .map(item => item.trim())
      .filter(Boolean)
    const maxTotalNumber = Number.parseInt(maxTotal, 10)

    try {
      setLocalLogs((prev) => [...prev, t.osuka.logsRequestSent])
        const response = await osukaApi.run({
          category: category.trim(),
          market: market.trim() || undefined,
          allow_external_brands: allowExternal,
          prefer_pdfs: preferPdfs,
          max_total: Number.isFinite(maxTotalNumber) && maxTotalNumber > 0 ? maxTotalNumber : 10,
          max_shopee_products: 10,
          preferred_brands: preferredList.length ? preferredList : undefined,
        })
      setRunId(response.run_id)
      setLocalLogs((prev) => [...prev, t.osuka.logsResponseReceived])
      toast.success(t.common.success)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : t.common.error
      setRunState({ error: message })
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AppShell>
      <div className="flex flex-col h-full w-full max-w-none px-6 py-6 space-y-6 overflow-auto">
        <div>
          <h1 className="text-3xl font-bold">{t.osuka.title}</h1>
          <p className="mt-2 text-muted-foreground">{t.osuka.description}</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>{t.osuka.formTitle}</CardTitle>
            <CardDescription>{t.osuka.formDescription}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="osuka-category">{t.osuka.categoryLabel}</Label>
              <Input
                id="osuka-category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder={t.osuka.categoryPlaceholder}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="osuka-market">{t.osuka.marketLabel}</Label>
              <Input
                id="osuka-market"
                value={market}
                onChange={(e) => setMarket(e.target.value)}
                placeholder={t.osuka.marketPlaceholder}
              />
            </div>

            <div className="flex items-center gap-2">
              <Checkbox
                id="osuka-allow-external"
                checked={allowExternal}
                onCheckedChange={(checked) => setAllowExternal(Boolean(checked))}
              />
              <Label htmlFor="osuka-allow-external">{t.osuka.allowExternalLabel}</Label>
            </div>

            <div className="flex items-center gap-2">
              <Checkbox
                id="osuka-prefer-pdfs"
                checked={preferPdfs}
                onCheckedChange={(checked) => setPreferPdfs(Boolean(checked))}
              />
              <Label htmlFor="osuka-prefer-pdfs">{t.osuka.preferPdfsLabel}</Label>
            </div>

            <div className="space-y-2">
              <Label htmlFor="osuka-preferred-brands">{t.osuka.preferredBrandsLabel}</Label>
              <Input
                id="osuka-preferred-brands"
                value={preferredBrands}
                onChange={(e) => setPreferredBrands(e.target.value)}
                placeholder={t.osuka.preferredBrandsPlaceholder}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="osuka-max-total">{t.osuka.maxTotalLabel}</Label>
              <Input
                id="osuka-max-total"
                type="number"
                min="1"
                value={maxTotal}
                onChange={(e) => setMaxTotal(e.target.value)}
                placeholder="10"
              />
            </div>

            <div className="flex items-center gap-3">
              <Button onClick={handleRun} disabled={loading}>
                {loading ? t.common.processing : t.osuka.runButton}
              </Button>
            </div>
          </CardContent>
        </Card>

        {runState.error && (
          <Card>
            <CardHeader>
              <CardTitle>{t.common.error}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-red-500">{runState.error}</p>
            </CardContent>
          </Card>
        )}

        {runState.response && (
          <Card>
            <CardHeader>
              <CardTitle>{t.osuka.resultsTitle}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="text-sm text-muted-foreground">
                {t.osuka.productsFound.replace('{count}', String(runState.response.products.length))}
              </div>
              <div className="text-sm text-muted-foreground">
                {t.osuka.sourcesAdded.replace('{count}', String(runState.response.sources_added))}
              </div>
              <div className="text-sm">
                <Link href={`/notebooks/${runState.response.notebook_id}`} className="text-primary underline">
                  {t.osuka.openNotebook}
                </Link>
              </div>
              {runState.response.chat_session_id && (
                <div className="text-sm">
                  <Link
                    href={`/notebooks/${runState.response.notebook_id}?chat=${runState.response.chat_session_id}`}
                    className="text-primary underline"
                  >
                    {t.osuka.openChat}
                  </Link>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {runState.response?.markdown_table && (
          <Card>
            <CardHeader>
              <CardTitle>{t.osuka.tableTitle}</CardTitle>
              <CardDescription>{t.osuka.tableDescription}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-md border p-4 bg-muted/40">
                <div className="text-xs uppercase text-muted-foreground mb-2">{t.osuka.chatYou}</div>
                <div className="text-sm">{t.osuka.tablePrompt}</div>
              </div>
              <div className="rounded-md border p-4">
                <div className="text-xs uppercase text-muted-foreground mb-2">{t.osuka.chatModel}</div>
                <div className="prose prose-sm max-w-none">
                  <ReactMarkdown>{runState.response.markdown_table}</ReactMarkdown>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {(localLogs.length > 0 || runStatus?.logs?.length || runState.response?.logs?.length) && (
          <Card>
            <CardHeader className="pb-2">
              <Collapsible open={debugOpen} onOpenChange={setDebugOpen}>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{t.osuka.logsTitle}</CardTitle>
                  <CollapsibleTrigger asChild>
                    <Button variant="ghost" size="sm">
                      {debugOpen ? t.common.close : t.common.details}
                    </Button>
                  </CollapsibleTrigger>
                </div>
                <CollapsibleContent>
                  <CardDescription>{t.osuka.logsDescription}</CardDescription>
                </CollapsibleContent>
              </Collapsible>
            </CardHeader>
            <CardContent>
              <div className="space-y-1 text-xs text-muted-foreground max-h-64 overflow-auto pr-2">
                {localLogs.map((line, idx) => (
                  <div key={`local-${idx}`}>{line}</div>
                ))}
                {runStatus?.logs?.map((line, idx) => (
                  <div key={`remote-${idx}`}>{line}</div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </AppShell>
  )
}
