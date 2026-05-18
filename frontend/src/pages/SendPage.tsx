import { useCallback, useRef, useState } from 'react'
import {
  DoneSummary,
  ProgressEvent,
  openProgressStream,
  startSend,
  validateCsv,
} from '../lib/api'

type CsvInfo = { total: number; columns: string[] }

const MODES = [
  { value: 'html',       label: 'HTML Email',    desc: 'Personalised HTML email' },
  { value: 'qr',         label: 'QR Code',       desc: 'Email unique QR codes' },
  { value: 'attachment', label: 'PDF Attachment', desc: 'Generate PDF and attach' },
]

const LOG_COLOR: Record<string, string> = {
  ok:      'text-green-400',
  fail:    'text-red-400',
  error:   'text-red-300 font-semibold',
  retry:   'text-yellow-400',
  info:    'text-gray-400',
  summary: 'text-white font-semibold',
}

export default function SendPage() {
  const [csvInfo,    setCsvInfo]    = useState<CsvInfo | null>(null)
  const [mode,       setMode]       = useState('html')
  const [log,        setLog]        = useState<ProgressEvent[]>([])
  const [running,    setRunning]    = useState(false)
  const [summary,    setSummary]    = useState<DoneSummary | null>(null)
  const [uploadErr,  setUploadErr]  = useState<string | null>(null)
  const [uploading,  setUploading]  = useState(false)
  const logEndRef = useRef<HTMLDivElement>(null)

  const addLog = (entry: ProgressEvent) => {
    setLog(prev => [...prev, entry])
    setTimeout(() => logEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 30)
  }

  const handleFile = useCallback(async (file: File) => {
    setUploadErr(null)
    setCsvInfo(null)
    setUploading(true)
    try {
      const result = await validateCsv(file)
      setCsvInfo(result)
    } catch (e: unknown) {
      setUploadErr(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }, [])

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const handleSend = async () => {
    if (!csvInfo || running) return
    setLog([])
    setSummary(null)
    setRunning(true)

    try {
      await startSend(mode)
    } catch (e: unknown) {
      addLog({ type: 'error', message: e instanceof Error ? e.message : 'Start failed' })
      setRunning(false)
      return
    }

    openProgressStream(
      addLog,
      (done) => {
        setSummary(done)
        setRunning(false)
      },
      () => {
        addLog({ type: 'error', message: 'Connection to server lost.' })
        setRunning(false)
      },
    )
  }

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold text-gray-900">Send Certificates</h1>

      {/* CSV upload */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => !uploading && document.getElementById('csv-input')?.click()}
        className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-blue-400 transition-colors select-none"
      >
        <input
          id="csv-input"
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
        {uploading ? (
          <p className="text-gray-400 text-sm">Validating…</p>
        ) : csvInfo ? (
          <div className="text-sm space-y-1">
            <p className="font-medium text-green-600">{csvInfo.total} participants loaded</p>
            <p className="text-gray-500">Columns: {csvInfo.columns.join(', ')}</p>
            <p className="text-gray-400 text-xs">Click to replace</p>
          </div>
        ) : (
          <p className="text-gray-400 text-sm">Drop CSV here, or click to browse</p>
        )}
        {uploadErr && <p className="text-red-500 text-sm mt-2">{uploadErr}</p>}
      </div>

      {/* Mode selector */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Mode</label>
        <div className="grid grid-cols-3 gap-3">
          {MODES.map((m) => (
            <button
              key={m.value}
              onClick={() => setMode(m.value)}
              className={`p-3 rounded-lg border text-left text-sm transition-colors ${
                mode === m.value
                  ? 'border-blue-500 bg-blue-50 text-blue-700'
                  : 'border-gray-200 hover:border-gray-300 text-gray-700'
              }`}
            >
              <p className="font-medium">{m.label}</p>
              <p className="text-xs text-gray-500 mt-0.5">{m.desc}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Send button */}
      <button
        onClick={handleSend}
        disabled={!csvInfo || running}
        className="w-full py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {running ? 'Sending…' : 'Start Send'}
      </button>

      {/* Live log */}
      {log.length > 0 && (
        <div className="bg-gray-900 rounded-lg p-4 font-mono text-xs max-h-80 overflow-y-auto space-y-0.5">
          {log.map((entry, i) => (
            <div key={i} className={LOG_COLOR[entry.type] || 'text-gray-300'}>
              {entry.message}
            </div>
          ))}
          <div ref={logEndRef} />
        </div>
      )}

      {/* Summary */}
      {summary && (
        <div
          className={`rounded-lg p-4 border text-sm ${
            summary.failed > 0
              ? 'bg-yellow-50 border-yellow-200'
              : 'bg-green-50 border-green-200'
          }`}
        >
          <p className="font-medium text-gray-900">
            Done — Sent: {summary.sent} | Failed: {summary.failed} | Total: {summary.total}
          </p>
          {summary.failed > 0 && (
            <p className="text-gray-600 mt-1 text-xs">
              Failed entries are logged. Re-upload the same CSV and run again to retry only failed
              participants.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
