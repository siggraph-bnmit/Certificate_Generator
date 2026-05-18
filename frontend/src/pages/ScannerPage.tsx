import { useCallback, useEffect, useState } from 'react'

const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

type CsvStatus = { loaded: boolean; total?: number; attended?: number; absent?: number }

export default function ScannerPage() {
  const [csvStatus,  setCsvStatus]  = useState<CsvStatus>({ loaded: false })
  const [uploading,  setUploading]  = useState(false)
  const [uploadMsg,  setUploadMsg]  = useState<{ ok: boolean; text: string } | null>(null)

  const loadStatus = useCallback(() => {
    fetch(`${BASE}/api/scan-csv-status`)
      .then((r) => r.json())
      .then(setCsvStatus)
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadStatus()
  }, [loadStatus])

  const handleFile = async (file: File) => {
    setUploading(true)
    setUploadMsg(null)
    const form = new FormData()
    form.append('file', file)
    try {
      const res  = await fetch(`${BASE}/api/upload-scan-csv`, { method: 'POST', body: form })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Upload failed')
      setUploadMsg({
        ok:   true,
        text: data.warning
          ? `Loaded ${data.total} rows. Warning: ${data.warning}`
          : `Loaded ${data.total} rows — ready to scan.`,
      })
      loadStatus()
    } catch (e: unknown) {
      setUploadMsg({ ok: false, text: e instanceof Error ? e.message : 'Upload failed' })
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold text-gray-900">Attendance Scanner</h1>

      {/* Step 1 — upload CSV */}
      <div className="bg-white rounded-lg border p-4 space-y-3">
        <p className="text-sm font-medium text-gray-700">
          Step 1 — Upload the attendance CSV
        </p>
        <p className="text-xs text-gray-500">
          This must be the same CSV used when sending QR codes. It must have{' '}
          <code className="bg-gray-100 px-1 rounded">Token</code> and{' '}
          <code className="bg-gray-100 px-1 rounded">Attended</code> columns.
        </p>

        {csvStatus.loaded && (
          <div className="flex items-center gap-4 text-sm">
            <span className="text-green-600 font-medium">CSV loaded</span>
            <span className="text-gray-500">Total: {csvStatus.total}</span>
            <span className="text-green-600">Attended: {csvStatus.attended}</span>
            <span className="text-gray-500">Absent: {csvStatus.absent}</span>
          </div>
        )}

        <div className="flex items-center gap-3">
          <label className="cursor-pointer inline-flex items-center px-3 py-1.5 border rounded-lg text-sm text-gray-700 hover:bg-gray-50 transition-colors">
            {uploading ? 'Uploading…' : csvStatus.loaded ? 'Replace CSV' : 'Upload CSV'}
            <input
              type="file"
              accept=".csv"
              className="hidden"
              disabled={uploading}
              onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
            />
          </label>
        </div>

        {uploadMsg && (
          <p className={`text-xs ${uploadMsg.ok ? 'text-green-600' : 'text-red-500'}`}>
            {uploadMsg.text}
          </p>
        )}
      </div>

      {/* Step 2 — open scanner */}
      <div className="bg-white rounded-lg border p-4 space-y-3">
        <p className="text-sm font-medium text-gray-700">Step 2 — Open the scanner</p>
        <p className="text-xs text-gray-500">
          Opens the webcam QR scanner in a new tab. Use on the device that will scan QR codes at
          the entrance.
        </p>
        <a
          href={`${BASE}/scanner`}
          target="_blank"
          rel="noopener noreferrer"
          className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            csvStatus.loaded
              ? 'bg-blue-600 text-white hover:bg-blue-700'
              : 'bg-gray-100 text-gray-400 cursor-not-allowed pointer-events-none'
          }`}
        >
          Open Scanner
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
            />
          </svg>
        </a>
        {!csvStatus.loaded && (
          <p className="text-xs text-gray-400">Upload the CSV above first to enable the scanner.</p>
        )}
      </div>

      {/* Workflow reminder */}
      <div className="bg-gray-50 rounded-lg border p-4 text-sm text-gray-600">
        <p className="font-medium text-gray-700 mb-2">Full event workflow</p>
        <ol className="list-decimal list-inside space-y-1">
          <li>
            Send QR codes via <code className="bg-gray-100 px-1 rounded text-xs">MODE=qr</code>{' '}
            — participants receive unique QR codes by email
          </li>
          <li>Upload the same CSV here, then open the Scanner above on event day</li>
          <li>Each scan marks the participant as attended; changes sync to Supabase</li>
          <li>
            After the event, run{' '}
            <code className="bg-gray-100 px-1 rounded text-xs">MODE=html</code> or{' '}
            <code className="bg-gray-100 px-1 rounded text-xs">MODE=attachment</code> — only
            attendees receive certificates
          </li>
        </ol>
      </div>
    </div>
  )
}
