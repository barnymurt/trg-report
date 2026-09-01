"use client";

import { Mic, Square, Loader2 } from "lucide-react";
import { useState, useRef } from "react";
import { blobToBase64, startRecording, stopRecording } from "@/lib/audio";

interface VoiceInputProps {
  onTranscript: (text: string) => void;
  onError?: (err: string) => void;
}

export function VoiceInput({ onTranscript, onError }: VoiceInputProps) {
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);

  const toggle = async () => {
    if (transcribing) return;
    if (recording) {
      const recorder = recorderRef.current!;
      const blob = await stopRecording(recorder);
      setRecording(false);
      setTranscribing(true);
      try {
        const base64 = await blobToBase64(blob);
        const res = await fetch("/api/stt/transcribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ audio_base64: base64, language: "en" }),
        });
        if (!res.ok) throw new Error(`stt ${res.status}`);
        const data = await res.json();
        onTranscript(data.text || "");
      } catch (e: any) {
        onError?.(e.message ?? "transcription failed");
      } finally {
        setTranscribing(false);
      }
    } else {
      try {
        recorderRef.current = await startRecording();
        setRecording(true);
      } catch (e: any) {
        onError?.(e.message ?? "microphone unavailable");
      }
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={recording ? "Stop recording" : "Start voice input"}
      className={`relative tap-large rounded-full p-4 transition-all ${
        recording
          ? "bg-danger text-white voice-pulse"
          : transcribing
            ? "bg-muted text-white"
            : "bg-accent hover:bg-accentHover text-white"
      }`}
    >
      {transcribing ? (
        <Loader2 className="h-6 w-6 animate-spin" />
      ) : recording ? (
        <Square className="h-6 w-6" />
      ) : (
        <Mic className="h-6 w-6" />
      )}
    </button>
  );
}
