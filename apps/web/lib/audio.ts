// Audio capture + base64 helper for voice input.

export async function blobToBase64(blob: Blob): Promise<string> {
  const arrayBuffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(arrayBuffer);
  // Chunked to avoid call-stack overflow on large audio
  const chunkSize = 0x8000;
  let binary = "";
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode.apply(
      null,
      Array.from(bytes.subarray(i, i + chunkSize)) as number[],
    );
  }
  return btoa(binary);
}

export function base64ToBlobUrl(base64: string, mime = "audio/wav"): string {
  const bytes = atob(base64);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return URL.createObjectURL(new Blob([arr], { type: mime }));
}

export async function startRecording(): Promise<MediaRecorder> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      sampleRate: 16000,
    },
  });
  const recorder = new MediaRecorder(stream, {
    mimeType: "audio/webm;codecs=opus",
  });
  recorder.start();
  return recorder;
}

export function stopRecording(recorder: MediaRecorder): Promise<Blob> {
  return new Promise((resolve) => {
    recorder.addEventListener(
      "dataavailable",
      (e) => {
        if (e.data.size > 0) resolve(e.data);
      },
      { once: true },
    );
    recorder.stop();
    recorder.stream.getTracks().forEach((t) => t.stop());
  });
}
