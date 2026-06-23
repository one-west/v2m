import { useState } from "react";
import { RecorderPanel } from "./features/recorder/RecorderPanel";
import { RecordingList } from "./features/recordings/RecordingList";
import { RecordingDetail } from "./features/recordings/RecordingDetail";
import { useRecordings } from "./hooks/useRecordings";
import { deleteRecording } from "./lib/api";

export function App() {
  const { recordings, loading, refresh } = useRecordings();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  async function handleDelete(id: string) {
    await deleteRecording(id);
    if (selectedId === id) setSelectedId(null);
    refresh();
  }

  return (
    <main className="app">
      <h1>V2M — 음성에서 회의록까지</h1>
      {selectedId ? (
        <RecordingDetail
          id={selectedId}
          onBack={() => {
            setSelectedId(null);
            refresh();
          }}
        />
      ) : (
        <>
          <RecorderPanel onUploaded={refresh} />
          {loading && recordings.length === 0 ? (
            <p className="loading">불러오는 중…</p>
          ) : (
            <RecordingList recordings={recordings} onSelect={setSelectedId} onDelete={handleDelete} />
          )}
        </>
      )}
    </main>
  );
}
