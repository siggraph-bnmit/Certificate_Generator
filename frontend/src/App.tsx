import { BrowserRouter, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import ConfigurePage from './pages/ConfigurePage'
import LogsPage from './pages/LogsPage'
import ScannerPage from './pages/ScannerPage'
import SendPage from './pages/SendPage'

const NAV = [
  { to: '/send',      label: 'Send' },
  { to: '/configure', label: 'Configure' },
  { to: '/logs',      label: 'Logs' },
  { to: '/scanner',   label: 'Scanner' },
]

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50 flex flex-col">
        <header className="bg-white border-b px-6 py-3 flex items-center gap-8 shadow-sm">
          <span className="font-bold text-gray-900 text-sm tracking-wide">
            Certificate Generator
          </span>
          <nav className="flex gap-6">
            {NAV.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `text-sm font-medium transition-colors ${
                    isActive ? 'text-blue-600' : 'text-gray-500 hover:text-gray-800'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </header>

        <main className="flex-1 p-6 max-w-3xl mx-auto w-full">
          <Routes>
            <Route path="/" element={<Navigate to="/send" replace />} />
            <Route path="/send"      element={<SendPage />} />
            <Route path="/configure" element={<ConfigurePage />} />
            <Route path="/logs"      element={<LogsPage />} />
            <Route path="/scanner"   element={<ScannerPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
