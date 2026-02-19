import { useEffect } from 'react'
import useSpeechRecognition from '../hooks/useSpeechRecognition'

export default function VoiceRecorder({ prompt, onFinish, disabled }) {
  const { isListening, transcript, interimText, isSupported, start, stop, reset } =
    useSpeechRecognition()

  useEffect(() => {
    reset()
  }, [prompt, reset])

  if (!isSupported) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
        Speech recognition is not supported in this browser. Please use Chrome or Edge.
      </div>
    )
  }

  const handleDone = () => {
    stop()
    if (transcript.trim()) {
      onFinish(transcript.trim())
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-lg font-medium text-gray-800">{prompt}</p>

      {/* Recording controls */}
      <div className="flex items-center gap-3">
        {!isListening ? (
          <button
            onClick={start}
            disabled={disabled}
            className="inline-flex items-center gap-2 rounded-full bg-snow-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-snow-700 focus:outline-none focus:ring-2 focus:ring-snow-500 focus:ring-offset-2 disabled:opacity-50"
          >
            <MicIcon />
            Start Recording
          </button>
        ) : (
          <button
            onClick={stop}
            className="inline-flex items-center gap-2 rounded-full bg-red-500 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-red-600 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
          >
            <StopIcon />
            Stop Recording
          </button>
        )}

        {transcript && !isListening && (
          <button
            onClick={handleDone}
            className="inline-flex items-center gap-2 rounded-full bg-emerald-500 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2"
          >
            <CheckIcon />
            Use This
          </button>
        )}
      </div>

      {/* Recording indicator */}
      {isListening && (
        <div className="flex items-center gap-3 text-sm text-red-600">
          <span className="relative flex h-3 w-3">
            <span className="animate-pulse-ring absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
            <span className="relative inline-flex h-3 w-3 rounded-full bg-red-500"></span>
          </span>
          Listening...
        </div>
      )}

      {/* Transcript display */}
      {(transcript || interimText) && (
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <p className="text-sm text-gray-700">
            {transcript}
            {interimText && (
              <span className="text-gray-400"> {interimText}</span>
            )}
          </p>
        </div>
      )}
    </div>
  )
}

function MicIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
    </svg>
  )
}

function StopIcon() {
  return (
    <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
      <rect x="6" y="6" width="12" height="12" rx="1" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
    </svg>
  )
}
