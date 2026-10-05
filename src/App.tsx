import { lazy, Suspense } from "react";
import { AccessScreen } from "./AccessScreen";
import { EDITOR_PATH } from "./editor/path";
import { OrganizerDashboard } from "./organizer/OrganizerDashboard";
import { ParticipantWaitingScreen } from "./participant/ParticipantWaitingScreen";
import { useAccessSession } from "./useAccessSession";

// The editor brings a code field and Python, which a participant never needs.
const TaskEditor = lazy(() => import("./editor/TaskEditor"));

function SessionApp() {
  const { session, setSession, authenticate, logout } = useAccessSession();

  if (!session) return <AccessScreen onAuthenticate={authenticate} />;
  if (session.role === "organizer") {
    return <OrganizerDashboard session={session} onLogout={logout} />;
  }
  return (
    <ParticipantWaitingScreen
      session={session}
      onSessionChange={setSession}
      onLogout={logout}
    />
  );
}

export function App() {
  if (window.location.pathname === EDITOR_PATH) {
    return (
      <Suspense fallback={null}>
        <TaskEditor />
      </Suspense>
    );
  }
  return <SessionApp />;
}
