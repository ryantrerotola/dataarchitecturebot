import { useState } from 'react'
import { exportAlation, exportAlationCombined } from '../api/client'

export default function ReviewExport({ documented, onBack }) {
  const tables = Array.from(documented.values())
  const [downloading, setDownloading] = useState(false)

  const handleDownloadSeparate = async () => {
    setDownloading(true)
    try {
      const result = await exportAlation(tables)
      downloadFile(result.tables.filename, result.tables.content, 'text/csv')
      downloadFile(result.columns.filename, result.columns.content, 'text/csv')
    } catch (err) {
      alert(`Export failed: ${err.message}`)
    } finally {
      setDownloading(false)
    }
  }

  const handleDownloadCombined = async () => {
    setDownloading(true)
    try {
      const blob = await exportAlationCombined(tables)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'alation_upload.csv'
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      alert(`Export failed: ${err.message}`)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">
          Review & Export
        </h2>
        <p className="mt-1 text-sm text-gray-500">
          {tables.length} table{tables.length !== 1 ? 's' : ''} documented
        </p>
      </div>

      {/* Documented tables */}
      <div className="space-y-4">
        {tables.map((t) => (
          <div
            key={`${t.database}.${t.schema_name}.${t.table_name}`}
            className="rounded-xl border border-gray-200 bg-white shadow-sm"
          >
            <div className="border-b border-gray-100 px-5 py-4">
              <h3 className="font-medium text-gray-900">
                {t.database}.{t.schema_name}.{t.table_name}
              </h3>
              <p className="mt-1 text-sm text-gray-600">{t.table_description}</p>
            </div>
            {t.columns.length > 0 && (
              <div className="px-5 py-3">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                      <th className="pb-2 pr-4">Column</th>
                      <th className="pb-2">Description</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {t.columns.map((c) => (
                      <tr key={c.name}>
                        <td className="py-2 pr-4 font-mono text-xs text-gray-700">
                          {c.name}
                        </td>
                        <td className="py-2 text-gray-600">
                          {c.description || (
                            <span className="italic text-gray-400">
                              No description
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Export buttons */}
      <div className="flex flex-wrap gap-3">
        <button
          onClick={handleDownloadCombined}
          disabled={downloading || tables.length === 0}
          className="inline-flex items-center gap-2 rounded-lg bg-snow-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-snow-700 disabled:opacity-50"
        >
          <DownloadIcon />
          Download Combined CSV
        </button>
        <button
          onClick={handleDownloadSeparate}
          disabled={downloading || tables.length === 0}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-5 py-2.5 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-50 disabled:opacity-50"
        >
          <DownloadIcon />
          Download Separate CSVs
        </button>
        <button
          onClick={onBack}
          className="rounded-lg border border-gray-300 bg-white px-5 py-2.5 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-50"
        >
          Document More Tables
        </button>
      </div>
    </div>
  )
}

function downloadFile(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function DownloadIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
    </svg>
  )
}
