import { useEffect, useState } from 'react'
import { getConfig } from '../lib/api'

type Config = {
  gmail_address:      string
  gmail_configured:   boolean
  mode:               string
  send_delay:         string
  default_subject:    string
  attachment_subject: string
  qr_secret_set:      boolean
  pptx_template_set:  boolean
}

function Row({ label, value }: { label: string; value: string | boolean }) {
  return (
    <tr className="border-t border-gray-100">
      <td className="py-2.5 pr-6 text-sm text-gray-500 font-mono whitespace-nowrap">{label}</td>
      <td className="py-2.5 text-sm text-gray-900">
        {typeof value === 'boolean' ? (
          <span
            className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
              value ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'
            }`}
          >
            {value ? 'Set' : 'Not set'}
          </span>
        ) : value ? (
          value
        ) : (
          <span className="text-gray-400 italic">not set</span>
        )}
      </td>
    </tr>
  )
}

export default function ConfigurePage() {
  const [config, setConfig] = useState<Config | null>(null)
  const [error,  setError]  = useState<string | null>(null)

  useEffect(() => {
    getConfig().then(setConfig).catch((e: Error) => setError(e.message))
  }, [])

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold text-gray-900">Configuration</h1>

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
        <p className="font-medium">How to update settings</p>
        <p className="mt-1">
          All configuration is managed through environment variables. On Render, go to{' '}
          <strong>Dashboard → Your Service → Environment</strong> to add or change values.
          Sensitive credentials (Gmail password, QR secret) should only be set there — never
          committed to code.
        </p>
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      {config && (
        <div className="bg-white rounded-lg border p-4">
          <table className="w-full">
            <tbody>
              <Row label="GMAIL_ADDRESS"      value={config.gmail_address} />
              <Row label="GMAIL_APP_PASSWORD" value={config.gmail_configured} />
              <Row label="MODE"               value={config.mode} />
              <Row label="SEND_DELAY_SECONDS" value={config.send_delay} />
              <Row label="DEFAULT_SUBJECT"    value={config.default_subject} />
              <Row label="ATTACHMENT_SUBJECT" value={config.attachment_subject} />
              <Row label="QR_SECRET_KEY"      value={config.qr_secret_set} />
              <Row label="PPTX_TEMPLATE_PATH" value={config.pptx_template_set} />
            </tbody>
          </table>
        </div>
      )}

      <div className="bg-gray-50 rounded-lg border p-4 text-sm text-gray-600 space-y-1">
        <p className="font-medium text-gray-700">Required env vars</p>
        <ul className="space-y-1 mt-2">
          {[
            ['GMAIL_ADDRESS',      'Gmail address to send from'],
            ['GMAIL_APP_PASSWORD', '16-character Gmail App Password'],
            ['QR_SECRET_KEY',      'Required for QR and Scan modes'],
            ['PPTX_TEMPLATE_PATH', 'Required for Attachment mode'],
            ['FRONTEND_URL',       'Your Vercel deployment URL (enables CORS)'],
          ].map(([key, desc]) => (
            <li key={key}>
              <code className="bg-gray-100 px-1 rounded text-xs">{key}</code>
              {' — '}
              {desc}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
