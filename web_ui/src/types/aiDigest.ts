export type DigestFormat = 'by_topic' | 'by_feed' | 'overall'

export interface AiDigestConfig {
  enabled: boolean
  cron: string
  window_hours: number
  max_articles: number
  formats: DigestFormat[]
  webhook_url: string
  next_run?: string | null
}
