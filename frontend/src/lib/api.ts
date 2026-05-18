const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

async function fetchJson(path: string, init?: RequestInit) {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export const getConfig = () => fetchJson('/api/config')

export const getJobStatus = () => fetchJson('/api/job-status')

export const getLogs = () => fetchJson('/api/logs')

export async function validateCsv(file: File) {
  const form = new FormData()
  form.append('file', file)
  return fetchJson('/api/validate-csv', { method: 'POST', body: form })
}

export async function startSend(csvTmpPath: string, mode: string) {
  const form = new FormData()
  form.append('csv_tmp_path', csvTmpPath)
  form.append('mode', mode)
  return fetchJson('/api/send', { method: 'POST', body: form })
}

export type ProgressEvent = { type: string; message: string }
export type DoneSummary   = { sent: number; failed: number; total: number }

export function openProgressStream(
  onEvent: (e: ProgressEvent) => void,
  onDone:  (summary: DoneSummary) => void,
  onError: (e: Event) => void,
): () => void {
  const es = new EventSource(`${BASE}/api/progress`)

  es.onmessage = (ev) => {
    const data = JSON.parse(ev.data)
    if (data.type === 'done') {
      onDone(data)
      es.close()
    } else if (data.type !== 'heartbeat') {
      onEvent(data)
    }
  }

  es.onerror = (e) => {
    onError(e)
    es.close()
  }

  return () => es.close()
}
