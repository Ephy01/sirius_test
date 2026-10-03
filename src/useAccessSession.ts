import { useEffect, useState } from "react";
import { ApiError, api } from "./api";
import {
  clearAccessSession,
  loadAccessSession,
  redeemAccessCode,
  saveAccessSession,
  type AccessSession,
} from "./auth";

export function useAccessSession() {
  const [session, setSession] = useState<AccessSession | null>(() => loadAccessSession());
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const handleHistoryChange = () => setPath(window.location.pathname);
    window.addEventListener("popstate", handleHistoryChange);
    return () => window.removeEventListener("popstate", handleHistoryChange);
  }, []);

  const expectedPath = session
    ? session.role === "organizer"
      ? "/organizer"
      : "/contest"
    : "/";

  useEffect(() => {
    if (path === expectedPath) return;
    window.history.replaceState(null, "", expectedPath);
    setPath(expectedPath);
  }, [expectedPath, path]);

  useEffect(() => {
    if (!session || session.role !== "participant") return;

    const controller = new AbortController();
    api
      .getParticipantContext({
        token: session.token,
        signal: controller.signal,
      })
      .then((context) => {
        const refreshed: AccessSession = {
          ...session,
          contest: context.contest,
          participant: context.participant,
          enrollment: context.enrollment,
          attempt: context.attempt,
        };
        saveAccessSession(refreshed);
        setSession(refreshed);
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        if (caught instanceof ApiError && caught.status === 401) {
          clearAccessSession();
          setSession(null);
        }
      });

    return () => controller.abort();
  }, [session?.role, session?.token]);

  async function authenticate(code: string) {
    const redeemedSession = await redeemAccessCode(code);
    let nextSession = redeemedSession;

    if (redeemedSession.role === "participant") {
      try {
        const context = await api.getParticipantContext({
          token: redeemedSession.token,
        });
        nextSession = {
          ...redeemedSession,
          contest: context.contest,
          participant: context.participant,
          enrollment: context.enrollment,
          attempt: context.attempt,
        };
        saveAccessSession(nextSession);
      } catch (caught) {
        clearAccessSession();
        throw caught;
      }
    }

    setSession(nextSession);
    const destination =
      nextSession.role === "organizer" ? "/organizer" : "/contest";
    window.history.pushState(null, "", destination);
    setPath(destination);
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }

  function logout() {
    clearAccessSession();
    setSession(null);
    window.history.pushState(null, "", "/");
    setPath("/");
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }

  return { session, setSession, authenticate, logout };
}
