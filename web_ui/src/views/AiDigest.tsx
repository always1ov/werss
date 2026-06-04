import React, { useEffect, useState } from 'react'
import { useToast } from '@/hooks/use-toast'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { getAiDigestConfig, updateAiDigestConfig, runAiDigestNow } from '@/api/aiDigest'
import type { AiDigestConfig, DigestFormat } from '@/types/aiDigest'
import {
  Newspaper,
  Loader2,
  Save,
  Play,
  Clock,
  Settings2,
  Webhook,
} from 'lucide-react'

type CronPreset = 'multi_time' | 'every_6h' | 'every_12h' | 'custom'

// 可选时间点：6:00 ~ 22:00
const HOUR_OPTIONS = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22]

function hoursToLabel(h: number) {
  return `${h}:00`
}

function cronFromHours(hours: number[]): string {
  if (hours.length === 0) return '0 8 * * *'
  return `0 ${[...hours].sort((a, b) => a - b).join(',')} * * *`
}

function detectPreset(cron: string): { preset: CronPreset; hours: number[] } {
  if (cron === '0 */6 * * *') return { preset: 'every_6h', hours: [] }
  if (cron === '0 */12 * * *') return { preset: 'every_12h', hours: [] }
  // 单个或多个小时：0 8 * * * 或 0 8,12,18 * * *
  const m = cron.match(/^0 ([\d,]+) \* \* \*$/)
  if (m) {
    const hours = m[1].split(',').map(Number).filter(h => !isNaN(h))
    return { preset: 'multi_time', hours }
  }
  return { preset: 'custom', hours: [8] }
}

const FORMAT_OPTIONS: { value: DigestFormat; label: string; desc: string }[] = [
  { value: 'by_topic', label: '按主题聚合', desc: 'AI 识别热点话题，归纳各主题要点' },
  { value: 'by_feed', label: '按公众号分组', desc: '每个公众号一句话概括今日内容' },
  { value: 'overall', label: '整体综述', desc: '一段话总结所有文章的全局要点' },
]

const AiDigest: React.FC = () => {
  const { toast } = useToast()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [config, setConfig] = useState<AiDigestConfig>({
    enabled: false,
    cron: '0 8 * * *',
    window_hours: 24,
    max_articles: 100,
    formats: ['by_topic'],
    webhook_url: '',
    next_run: null,
  })
  const [cronPreset, setCronPreset] = useState<CronPreset>('multi_time')
  const [selectedHours, setSelectedHours] = useState<number[]>([8])

  const loadConfig = async () => {
    setLoading(true)
    try {
      const res = await getAiDigestConfig() as any
      const data: AiDigestConfig = res?.data ?? res
      setConfig(data)
      const { preset, hours } = detectPreset(data.cron)
      setCronPreset(preset)
      if (hours.length > 0) setSelectedHours(hours)
    } catch {
      toast({ variant: 'destructive', title: '错误', description: '加载配置失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadConfig() }, [])

  const handleFormatChange = (fmt: DigestFormat, checked: boolean) => {
    setConfig(prev => ({
      ...prev,
      formats: checked
        ? [...prev.formats, fmt]
        : prev.formats.filter(f => f !== fmt),
    }))
  }

  const handlePresetChange = (preset: CronPreset) => {
    setCronPreset(preset)
    if (preset === 'every_6h') setConfig(prev => ({ ...prev, cron: '0 */6 * * *' }))
    if (preset === 'every_12h') setConfig(prev => ({ ...prev, cron: '0 */12 * * *' }))
    if (preset === 'multi_time') {
      const hrs = selectedHours.length > 0 ? selectedHours : [8]
      setSelectedHours(hrs)
      setConfig(prev => ({ ...prev, cron: cronFromHours(hrs) }))
    }
  }

  const handleHourToggle = (hour: number) => {
    setSelectedHours(prev => {
      const next = prev.includes(hour) ? prev.filter(h => h !== hour) : [...prev, hour]
      const hrs = next.length > 0 ? next : [hour]
      setConfig(c => ({ ...c, cron: cronFromHours(hrs) }))
      return hrs
    })
  }

  const save = async () => {
    if (config.formats.length === 0) {
      toast({ variant: 'destructive', title: '请至少选择一种摘要格式' })
      return
    }
    if (cronPreset === 'multi_time' && selectedHours.length === 0) {
      toast({ variant: 'destructive', title: '请至少选择一个推送时间点' })
      return
    }
    setSaving(true)
    try {
      await updateAiDigestConfig(config)
      toast({ title: '已保存', description: '配置已更新，定时任务将在下次启动时生效' })
      await loadConfig()
    } catch (e: any) {
      toast({ variant: 'destructive', title: '保存失败', description: e?.message || '未知错误' })
    } finally {
      setSaving(false)
    }
  }

  const runNow = async () => {
    setRunning(true)
    try {
      await runAiDigestNow()
      toast({ title: '已触发', description: 'AI 日报正在后台生成，请查看服务器日志或 webhook 消息' })
    } catch (e: any) {
      toast({ variant: 'destructive', title: '触发失败', description: e?.message || '未知错误' })
    } finally {
      setRunning(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-2xl">
      <div>
        <div className="flex items-center gap-2">
          <Newspaper className="h-7 w-7 text-primary" />
          <h1 className="text-3xl font-bold">AI 日报</h1>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          定时抓取最近一段时间的文章，用 AI 高度概括后推送到已配置的 webhook（钉钉 / 飞书 / 企微）。
        </p>
      </div>

      {/* 启用开关 + 下次执行 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">启用 AI 日报</CardTitle>
              <CardDescription className="mt-0.5">
                关闭后不影响已有推送任务，仍可手动触发
              </CardDescription>
            </div>
            <Switch
              checked={config.enabled}
              onCheckedChange={v => setConfig(prev => ({ ...prev, enabled: v }))}
            />
          </div>
        </CardHeader>
        {config.next_run && (
          <CardContent className="pt-0">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="h-4 w-4" />
              <span>下次执行：{config.next_run}</span>
            </div>
          </CardContent>
        )}
      </Card>

      {/* 定时设置 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Clock className="h-4 w-4" />
            定时配置
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>执行方式</Label>
            <Select value={cronPreset} onValueChange={v => handlePresetChange(v as CronPreset)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="multi_time">指定时间点</SelectItem>
                <SelectItem value="every_6h">每 6 小时</SelectItem>
                <SelectItem value="every_12h">每 12 小时</SelectItem>
                <SelectItem value="custom">自定义 cron</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {cronPreset === 'multi_time' && (
            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">点击选择每天推送的时间点（可多选）</Label>
              <div className="flex flex-wrap gap-2">
                {HOUR_OPTIONS.map(h => {
                  const active = selectedHours.includes(h)
                  return (
                    <button
                      key={h}
                      type="button"
                      onClick={() => handleHourToggle(h)}
                      className={`px-3 py-1 rounded-full text-sm border transition-colors ${
                        active
                          ? 'bg-primary text-primary-foreground border-primary'
                          : 'bg-background text-muted-foreground border-border hover:border-primary/50'
                      }`}
                    >
                      {hoursToLabel(h)}
                    </button>
                  )
                })}
              </div>
              {selectedHours.length === 0 && (
                <p className="text-xs text-destructive">请至少选择一个时间点</p>
              )}
            </div>
          )}

          {(cronPreset === 'every_6h' || cronPreset === 'every_12h') && (
            <p className="text-xs text-muted-foreground">
              建议改用「指定时间点」，避免凌晨推送
            </p>
          )}

          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">cron 表达式（分 时 日 月 周）</Label>
            <Input
              value={config.cron}
              onChange={e => {
                const v = e.target.value
                setConfig(prev => ({ ...prev, cron: v }))
                const { preset, hours } = detectPreset(v)
                setCronPreset(preset)
                if (preset === 'multi_time' && hours.length > 0) setSelectedHours(hours)
              }}
              placeholder="0 8,12,18 * * *"
            />
          </div>
        </CardContent>
      </Card>

      {/* 内容设置 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Settings2 className="h-4 w-4" />
            内容设置
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="window-hours">时间窗口（小时）</Label>
              <Input
                id="window-hours"
                type="number"
                min={1}
                max={168}
                value={config.window_hours}
                onChange={e => setConfig(prev => ({ ...prev, window_hours: Math.min(168, Math.max(1, Number(e.target.value))) }))}
              />
              <p className="text-xs text-muted-foreground">抓取最近几小时内的文章，1-168</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="max-articles">最大文章数</Label>
              <Input
                id="max-articles"
                type="number"
                min={10}
                max={500}
                value={config.max_articles}
                onChange={e => setConfig(prev => ({ ...prev, max_articles: Math.min(500, Math.max(10, Number(e.target.value))) }))}
              />
              <p className="text-xs text-muted-foreground">单次最多处理的文章数，10-500</p>
            </div>
          </div>

          <Separator />

          <div className="space-y-3">
            <Label>摘要格式（可多选）</Label>
            {FORMAT_OPTIONS.map(opt => (
              <div key={opt.value} className="flex items-start gap-3">
                <Checkbox
                  id={`fmt-${opt.value}`}
                  checked={config.formats.includes(opt.value)}
                  onCheckedChange={checked => handleFormatChange(opt.value, !!checked)}
                />
                <div className="grid gap-0.5">
                  <label htmlFor={`fmt-${opt.value}`} className="text-sm font-medium leading-none cursor-pointer">
                    {opt.label}
                  </label>
                  <p className="text-xs text-muted-foreground">{opt.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Webhook 设置 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Webhook className="h-4 w-4" />
            推送目标
          </CardTitle>
          <CardDescription>
            自动推送到环境变量中配置的 DINGDING_WEBHOOK / FEISHU_WEBHOOK / WECHAT_WEBHOOK。
            下方可额外指定一个专用 webhook 地址。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <Label htmlFor="webhook-url">额外 Webhook 地址（可选）</Label>
            <Input
              id="webhook-url"
              placeholder="https://..."
              value={config.webhook_url}
              onChange={e => setConfig(prev => ({ ...prev, webhook_url: e.target.value }))}
            />
            <p className="text-xs text-muted-foreground">
              留空则仅使用环境变量中已配置的 webhook；填写后会同时推送到这个地址
            </p>
          </div>
        </CardContent>
      </Card>

      {/* 操作按钮 */}
      <div className="flex items-center gap-3">
        <Button onClick={save} disabled={saving || running}>
          {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
          保存配置
        </Button>
        <Button variant="outline" onClick={runNow} disabled={saving || running}>
          {running ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
          立即生成并推送
        </Button>
        <Badge variant="secondary" className="ml-auto">
          {config.formats.length} 种格式
        </Badge>
      </div>
    </div>
  )
}

export default AiDigest
