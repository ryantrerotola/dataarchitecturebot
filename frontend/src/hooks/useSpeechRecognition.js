import { useState, useRef, useCallback } from 'react'

const SpeechRecognition =
  window.SpeechRecognition || window.webkitSpeechRecognition

export default function useSpeechRecognition() {
  const [isListening, setIsListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [interimText, setInterimText] = useState('')
  const [isSupported] = useState(() => !!SpeechRecognition)
  const recognitionRef = useRef(null)

  const start = useCallback(() => {
    if (!SpeechRecognition) return

    const recognition = new SpeechRecognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'

    recognition.onresult = (event) => {
      let final = ''
      let interim = ''
      for (let i = 0; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) {
          final += result[0].transcript + ' '
        } else {
          interim += result[0].transcript
        }
      }
      setTranscript(final.trim())
      setInterimText(interim)
    }

    recognition.onerror = (event) => {
      if (event.error !== 'aborted') {
        console.error('Speech recognition error:', event.error)
      }
      setIsListening(false)
    }

    recognition.onend = () => {
      setIsListening(false)
      setInterimText('')
    }

    recognitionRef.current = recognition
    recognition.start()
    setIsListening(true)
    setTranscript('')
    setInterimText('')
  }, [])

  const stop = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
      recognitionRef.current = null
    }
    setIsListening(false)
  }, [])

  const reset = useCallback(() => {
    stop()
    setTranscript('')
    setInterimText('')
  }, [stop])

  return { isListening, transcript, interimText, isSupported, start, stop, reset }
}
