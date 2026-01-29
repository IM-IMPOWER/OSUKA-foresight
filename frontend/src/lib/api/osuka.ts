import apiClient from './client'

export type OsukaRunRequest = {
  category: string
  market?: string
  allow_external_brands?: boolean
  max_total?: number
  max_shopee_products?: number
  prefer_pdfs?: boolean
  preferred_brands?: string[]
}

export type OsukaRunResponse = {
  notebook_id: string
  sources_added: number
  table_note_id: string
  json_note_id: string
  shopee_summary_note_id?: string | null
  shopee_data_note_id?: string | null
  shopee_count?: number
  chat_session_id?: string
  products: Array<{
    brand_key?: string
    url: string
    title?: string
    snippet?: string
  }>
  logs?: string[]
  markdown_table?: string
}

export type OsukaRunStartResponse = {
  run_id: string
}

export type OsukaRunStatusResponse = {
  run_id: string
  status: 'running' | 'completed' | 'failed' | string
  logs: string[]
  result?: OsukaRunResponse
  error?: string
}

export const osukaApi = {
  run: async (data: OsukaRunRequest) => {
    const response = await apiClient.post<OsukaRunStartResponse>('/discovery/run', data)
    return response.data
  },
  status: async (runId: string) => {
    const response = await apiClient.get<OsukaRunStatusResponse>(`/discovery/run/${runId}`)
    return response.data
  },
}
