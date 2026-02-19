import { useState } from 'react'
import VoiceRecorder from './VoiceRecorder'
import { summarizeTable } from '../api/client'

const QUESTIONS = [
  { key: 'usage', prompt: 'What do you use this table for?' },
  { key: 'metrics', prompt: 'What metrics or KPIs come from this table?' },
  { key: 'stakeholders', prompt: 'Who are the key stakeholders for this data?' },
]

export default function TableDescriber({ table, onComplete }) {
  const [step, setStep] = useState(0)
  const [transcripts, setTranscripts] = useState({})
  const [summary, setSummary] = useState('')
  const [summarizing, setSummarizing] = useState(false)
  const [editing, setEditing] = useState(false)

  const objectName = `${table.database}.${table.schema_name}.${table.name}`
  const currentQuestion = QUESTIONS[step]
  const allQuestionsAnswered = step >= QUESTIONS.length

  const handleTranscript = (text) => {
    const updated = { ...transcripts, [currentQuestion.key]: text }
    setTranscripts(updated)

    if (step + 1 < QUESTIONS.length) {
      setStep(step + 1)
    } else {
      generateSummary(updated)
    }
  }

  const generateSummary = async (txts) => {
    setSummarizing(true)
    try {
      const result = await summarizeTable(objectName, txts)
      setSummary(result)
    } catch (err) {
      setSummary(`Error generating summary: ${err.message}`)
    } finally {
      setSummarizing(false)
    }
  }

  const handleApprove = () => {
    onComplete(summary)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-gray-900">
          Describe: <span className="text-snow-600">{table.name}</span>
        </h2>
        <p className="mt-1 text-sm text-gray-500">{objectName}</p>
      </div>

      {/* Progress */}
      <div className="flex gap-1.5">
        {QUESTIONS.map((q, i) => (
          <div
            key={q.key}
            className={`h-1.5 flex-1 rounded-full transition-colors ${
              i < step
                ? 'bg-emerald-400'
                : i === step && !allQuestionsAnswered
                  ? 'bg-snow-400'
                  : allQuestionsAnswered
                    ? 'bg-emerald-400'
                    : 'bg-gray-200'
            }`}
          />
        ))}
      </div>

      {/* Collected transcripts */}
      {Object.keys(transcripts).length > 0 && (
        <div className="space-y-2">
          {QUESTIONS.filter((q) => transcripts[q.key]).map((q) => (
            <div
              key={q.key}
              className="rounded-lg border border-gray-100 bg-gray-50 px-4 py-3"
            >
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                {q.prompt}
              </p>
              <p className="mt-1 text-sm text-gray-700">{transcripts[q.key]}</p>
            </div>
          ))}
        </div>
      )}

      {/* Current question */}
      {!allQuestionsAnswered && (
        <VoiceRecorder
          prompt={currentQuestion.prompt}
          onFinish={handleTranscript}
        />
      )}

      {/* Summary */}
      {summarizing && (
        <div className="flex items-center gap-3 rounded-lg border border-snow-200 bg-snow-50 p-4">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-snow-600 border-t-transparent"></div>
          <span className="text-sm text-snow-700">Generating summary...</span>
        </div>
      )}

      {summary && !summarizing && (
        <div className="space-y-3">
          <label className="text-sm font-medium text-gray-700">
            Generated Description
          </label>
          {editing ? (
            <textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              rows={4}
              className="w-full rounded-lg border border-gray-300 p-3 text-sm focus:border-snow-500 focus:outline-none focus:ring-1 focus:ring-snow-500"
            />
          ) : (
            <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-800">
              {summary}
            </div>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => setEditing(!editing)}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50"
            >
              {editing ? 'Preview' : 'Edit'}
            </button>
            <button
              onClick={handleApprove}
              className="rounded-lg bg-snow-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-snow-700"
            >
              Approve & Continue to Columns
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
