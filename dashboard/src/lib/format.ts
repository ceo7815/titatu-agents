const IL = 'Asia/Jerusalem'

export function formatUsd(value: number): string {
  const abs = Math.abs(value)
  const maximumFractionDigits = abs > 0 && abs < 0.01 ? 6 : abs < 1 ? 4 : 2
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits,
  }).format(value)
}

export function formatTokens(value: number): string {
  return new Intl.NumberFormat('he-IL').format(value)
}

export function toJerusalemDay(iso: string): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: IL,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(iso))
}

export function toJerusalemMonth(iso: string): string {
  return toJerusalemDay(iso).slice(0, 7)
}

export function formatDayHe(day: string): string {
  const [y, m, d] = day.split('-').map(Number)
  const date = new Date(Date.UTC(y, m - 1, d, 12))
  return new Intl.DateTimeFormat('he-IL', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  }).format(date)
}

export function formatMonthHe(month: string): string {
  const [y, m] = month.split('-').map(Number)
  const date = new Date(Date.UTC(y, m - 1, 1, 12))
  return new Intl.DateTimeFormat('he-IL', {
    month: 'long',
    year: 'numeric',
  }).format(date)
}

export function formatTimeHe(iso: string): string {
  return new Intl.DateTimeFormat('he-IL', {
    timeZone: IL,
    hour: '2-digit',
    minute: '2-digit',
    day: 'numeric',
    month: 'short',
  }).format(new Date(iso))
}

export function relativeHe(iso: string | null): string {
  if (!iso) return 'אין עדיין'
  const then = new Date(iso).getTime()
  const now = Date.now()
  const diffMin = Math.round((now - then) / 60000)
  if (diffMin < 1) return 'עכשיו'
  if (diffMin < 60) return `לפני ${diffMin} דק׳`
  const hours = Math.round(diffMin / 60)
  if (hours < 24) return hours === 1 ? 'לפני שעה' : `לפני ${hours} שעות`
  const days = Math.round(hours / 24)
  if (days === 1) return 'אתמול'
  if (days < 7) return `לפני ${days} ימים`
  return formatTimeHe(iso)
}

export function todayJerusalem(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: IL,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

export function monthJerusalem(): string {
  return todayJerusalem().slice(0, 7)
}
