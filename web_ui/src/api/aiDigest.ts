import http from './http'
import type { AiDigestConfig } from '@/types/aiDigest'

export const getAiDigestConfig = () =>
  http.get<AiDigestConfig>('/wx/ai-digest/config')

export const updateAiDigestConfig = (data: Partial<AiDigestConfig>) =>
  http.put<AiDigestConfig>('/wx/ai-digest/config', data)

export const runAiDigestNow = () =>
  http.post('/wx/ai-digest/run')
