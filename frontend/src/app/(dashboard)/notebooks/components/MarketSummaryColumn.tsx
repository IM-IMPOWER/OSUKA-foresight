'use client'

import { useMemo } from 'react'
import { NoteResponse } from '@/lib/types/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { BarChart3 } from 'lucide-react'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { EmptyState } from '@/components/common/EmptyState'
import { CollapsibleColumn, createCollapseButton } from '@/components/notebooks/CollapsibleColumn'
import { useNotebookColumnsStore } from '@/lib/stores/notebook-columns-store'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useNote } from '@/lib/hooks/use-notes'

interface MarketSummaryColumnProps {
  notes?: NoteResponse[]
  isLoading: boolean
}

function pickMarketSummary(notes?: NoteResponse[]) {
  if (!notes || notes.length === 0) return undefined
  const candidates = notes.filter((note) => {
    const title = (note.title || '').toLowerCase()
    const content = (note.content || '').toLowerCase()
    return title.includes('shopee summary') || content.includes('market size gmv')
  })
  if (candidates.length === 0) return undefined
  const withContent = candidates.filter((note) => (note.content || '').trim().length > 0)
  const pool = withContent.length > 0 ? withContent : candidates
  return pool.sort((a, b) => new Date(b.updated).getTime() - new Date(a.updated).getTime())[0]
}

export function MarketSummaryColumn({ notes, isLoading }: MarketSummaryColumnProps) {
  const { t } = useTranslation()
  const { marketCollapsed, toggleMarket } = useNotebookColumnsStore()

  const summaryNote = useMemo(() => pickMarketSummary(notes), [notes])
  const { data: summaryNoteDetail } = useNote(summaryNote?.id, {
    enabled: Boolean(summaryNote?.id && !(summaryNote.content || '').trim()),
  })
  const displayNote = summaryNoteDetail ?? summaryNote
  const collapseButton = useMemo(
    () => createCollapseButton(toggleMarket, t.common.marketSummary),
    [toggleMarket, t.common.marketSummary]
  )

  return (
    <CollapsibleColumn
      isCollapsed={marketCollapsed}
      onToggle={toggleMarket}
      collapsedIcon={BarChart3}
      collapsedLabel={t.common.marketSummary}
    >
      <Card className="h-full flex flex-col flex-1 overflow-hidden">
        <CardHeader className="pb-3 flex-shrink-0">
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="text-lg">{t.common.marketSummary}</CardTitle>
            {collapseButton}
          </div>
        </CardHeader>

        <CardContent className="flex-1 overflow-y-auto min-h-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <LoadingSpinner />
            </div>
          ) : !summaryNote ? (
            <EmptyState
              icon={BarChart3}
              title={t.notebooks.noNotesYet}
              description={t.sources.createFirstNote}
            />
          ) : (
            <div className="p-3 border rounded-lg">
              {displayNote?.title && (
                <h4 className="text-sm font-medium mb-2">{displayNote.title}</h4>
              )}
              <div className="mb-2 text-xs text-muted-foreground">
                Debug: id={displayNote?.id} | updated={displayNote?.updated} | contentLen=
                {(displayNote?.content || '').length}
              </div>
              {(() => {
                const raw = displayNote?.content || ''
                const lines = raw.split(/\r?\n/)
                const firstNonEmptyIndex = lines.findIndex((line) => line.trim().length > 0)
                const firstLine = firstNonEmptyIndex >= 0 ? lines[firstNonEmptyIndex] : ''
                const rest =
                  firstNonEmptyIndex >= 0
                    ? lines.slice(firstNonEmptyIndex + 1).join('\n')
                    : ''
                return (
                  <>
                    {firstLine && (
                      <div className="text-lg font-bold mb-2">{firstLine}</div>
                    )}
                    {rest ? (
                      <pre className="text-sm whitespace-pre-wrap text-muted-foreground">
                        {rest}
                      </pre>
                    ) : raw && !firstLine ? (
                      <pre className="text-sm whitespace-pre-wrap text-muted-foreground">
                        {raw}
                      </pre>
                    ) : null}
                  </>
                )
              })()}
            </div>
          )}
        </CardContent>
      </Card>
    </CollapsibleColumn>
  )
}
