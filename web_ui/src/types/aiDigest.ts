export type DigestFormat = 'by_topic' | 'by_feed' | 'overall'

export interface AiDigestConfig {
  enabled: boolean
  schedules: string[]   // cron 数组，每条格式 "MM HH * * *"
  window_hours: number
  max_articles: number
  formats: DigestFormat[]
  webhook_url: string
  next_runs?: string[]
}
