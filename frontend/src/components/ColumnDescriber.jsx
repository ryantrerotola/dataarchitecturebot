import { useState } from 'react'
import VoiceRecorder from './VoiceRecorder'
import { summarizeColumn } from '../api/client'

export default function ColumnDescriber({ table, columns, onComplete }) {
  const [currentIdx, setCurrentIdx] = useState(0)
  const [descriptions, setDescriptions] = useState({})
  const [summarizing, setSummarizing] = useState(false)
  const [editingCol, setEditingCol] = useState(null)

  const objectName = `${table.database}.${table.schema_name}.${table.name}`
  const currentCol = columns[currentIdx]
  const allDone = currentIdx >= columns.length

  const handleTranscript = async (text) => {
    const colName = currentCol.name
    setSummarizing(true)
    try {
      const summary = await summarizeColumn(objectName, colName, text)
      setDescriptions((prev) => ({ ...prev, [colName]: summary }))
    } catch (err) {
      setDescriptions((prev) => ({
        ...prev,
        [colName]: `Error: ${err.message}`,
      }))
    } finally {
      setSummarizing(false)
      if (currentIdx + 1 < columns.length) {
        setCurrentIdx(currentIdx + 1)
      } else {
        setCurrentIdx(columns.length)
      }
    }
  }

  const handleSkip = () => {
    setDescriptions((prev) => ({
      ...prev,
      [currentCol.name]: currentCol.comment || '',
    }))
    if (currentIdx + 1 < columns.length) {
      setCurrentIdx(currentIdx + 1)
    } else {
      setCurrentIdx(columns.length)
    }
  }

  const handleFinish = () => {
    const colDocs = columns.map((c) => ({
      name: c.name,
      description: descriptions[c.name] || c.comment || '',
    }))
    onComplete(colDocs)
  }

  const handleEditSave = (colName, newDesc) => {
    setDescriptions((prev) => ({ ...prev, [colName]: newDesc }))
    setEditingCol(null)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900">
          Column Descriptions:{' '}
          <span className="text-snow-600">{table.name}</span>
        </h2>
        <p className="mt-1 text-sm text-gray-500">
          {allDone
            ? 'All columns described. Review and finish.'
            : `Column ${currentIdx + 1} of ${columns.length}`}
        </p>
      </div>

      {/* Progress bar */}
      <div className="h-2 overflow-hidden rounded-full bg-gray-200">
        <div
          className="h-full rounded-full bg-snow-500 transition-all duration-300"
          style={{
            width: `${(Object.keys(descriptions).length / columns.length) * 100}%`,
          }}
        />
      </div>

      {/* Completed columns */}
      {Object.keys(descriptions).length > 0 && (
        <div className="max-h-64 space-y-2 overflow-y-auto">
          {columns
            .filter((c) => descriptions[c.name])
            .map((c) => (
              <div
                key={c.name}
                className="rounded-lg border border-gray-100 bg-gray-50 px-4 py-3"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-900">
                      {c.name}
                    </span>
                    <span className="text-xs text-gray-400">{c.data_type}</span>
                  </div>
                  <button
                    onClick={() => setEditingCol(c.name)}
                    className="text-xs text-snow-600 hover:underline"
                  >
                    Edit
                  </button>
                </div>
                {editingCol === c.name ? (
                  <div className="mt-2 flex gap-2">
                    <input
                      defaultValue={descriptions[c.name]}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleEditSave(c.name, e.target.value)
                      }}
                      className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm focus:border-snow-500 focus:outline-none"
                      autoFocus
                    />
                    <button
                      onClick={(e) => {
                        const input = e.target.previousElementSibling
                        handleEditSave(c.name, input.value)
                      }}
                      className="text-xs text-snow-600"
                    >
                      Save
                    </button>
                  </div>
                ) : (
                  <p className="mt-1 text-sm text-gray-600">
                    {descriptions[c.name]}
                  </p>
                )}
              </div>
            ))}
        </div>
      )}

      {/* Current column recorder */}
      {!allDone && !summarizing && (
        <div className="rounded-xl border border-snow-200 bg-snow-50 p-5">
          <div className="mb-3 flex items-center gap-2">
            <span className="rounded bg-snow-100 px-2 py-0.5 text-xs font-mono text-snow-700">
              {currentCol.data_type}
            </span>
            {currentCol.nullable && (
              <span className="text-xs text-gray-400">nullable</span>
            )}
          </div>
          <VoiceRecorder
            prompt={`What does the column "${currentCol.name}" represent?`}
            onFinish={handleTranscript}
          />
          <button
            onClick={handleSkip}
            className="mt-3 text-sm text-gray-500 hover:text-gray-700"
          >
            Skip this column
          </button>
        </div>
      )}

      {summarizing && (
        <div className="flex items-center gap-3 rounded-lg border border-snow-200 bg-snow-50 p-4">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-snow-600 border-t-transparent"></div>
          <span className="text-sm text-snow-700">Summarizing column description...</span>
        </div>
      )}

      {/* Finish button */}
      {allDone && (
        <button
          onClick={handleFinish}
          className="w-full rounded-lg bg-emerald-500 py-3 text-sm font-medium text-white transition hover:bg-emerald-600"
        >
          Finish & Save Documentation
        </button>
      )}
    </div>
  )
}
