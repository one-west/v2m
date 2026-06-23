import { useCallback, useRef, useState } from "react";

const MIME = "audio/webm;codecs=opus";

export interface UseRecorder {
  isRecording: boolean;
  elapsedMs: number;
  start: () => Promise<void>;
  stop: () => Promise<Blob>;
}

export function useRecorder(): UseRecorder {
  const [isRecording, setIsRecording] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const startedAtRef = useRef(0);

  const start = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = MediaRecorder.isTypeSupported(MIME) ? MIME : "";
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    chunksRef.current = [];
    rec.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    rec.start(1000);
    recorderRef.current = rec;
    startedAtRef.current = Date.now();
    setElapsedMs(0);
    setIsRecording(true);
    timerRef.current = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAtRef.current);
    }, 250);
  }, []);

  const stop = useCallback(() => {
    return new Promise<Blob>((resolve) => {
      const rec = recorderRef.current;
      if (!rec) {
        resolve(new Blob());
        return;
      }
      rec.onstop = () => {
        if (timerRef.current) window.clearInterval(timerRef.current);
        rec.stream.getTracks().forEach((t) => t.stop());
        setIsRecording(false);
        resolve(new Blob(chunksRef.current, { type: rec.mimeType || MIME }));
      };
      rec.stop();
    });
  }, []);

  return { isRecording, elapsedMs, start, stop };
}
