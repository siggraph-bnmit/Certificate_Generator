import { useEffect, useState } from 'react'
import { getLogs } from '../lib/api'

type LogEntry = {
  email:     string
  name:      string
  status:    string
  timestamp: string
  error:     string
}

const STATUS_STYLE: Record<string, string> = {
  sent:      'bg-green-100 text-green-700',
  qr_sent:   'bg-blue-100 text-blue-700',
  failed:    'bg-red-100 text-red-600',
  qr_failed: 'bg-red-100 text-red-600',
}

export default function LogsPage() {
  const [logs,    setLogs]    = useState<LogEntry[]>([])
  const [filter,  setFilter]  = useState('all')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getLogs()
      .then(setLogs)
      .catch(() => setLogs([]))
      .finally(() => setLoading(false))
  }, [])

  const statuses = ['all', ...Array.from(new Set(logs.map((l) => l.status)))]
  const filtered = filter === 'all' ? logs : logs.filter((l) => l.status === filter)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Send Logs</h1>
        <div className="flex gap-2 flex-wrap">
          {statuses.map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1 rounded-full text-xs font-medium capitalize transition-colors ${
                filter === s
                  ? 'bg-gray-800 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="text-gray-400 text-sm">Loading…</p>
      ) : filtered.length === 0 ? (
        <p className="text-gray-400 text-sm">No entries found.</p>
      ) : (
        <div className="bg-white rounded-lg border overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                {['Time', 'Name', 'Email', 'Status', 'Error'].map((h) => (
                  <th key={h} className="text-left px-4 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((entry, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-4 py-2.5 text-gray-400 whitespace-nowrap font-mono text-xs">
                    {entry.timestamp}
                  </td>
                  <td className="px-4 py-2.5 text-gray-800">{entry.name}</td>
                  <td className="px-4 py-2.5 text-gray-500">{entry.email}</td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                        STATUS_STYLE[entry.status] || 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {entry.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-red-400 text-xs">{entry.error}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
