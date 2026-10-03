import { AccessScreen } from "./AccessScreen";
import { OrganizerDashboard } from "./organizer/OrganizerDashboard";
import { ParticipantWaitingScreen } from "./participant/ParticipantWaitingScreen";
import { useAccessSession } from "./useAccessSession";

export function App() {
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
