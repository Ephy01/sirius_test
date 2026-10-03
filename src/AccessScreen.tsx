import { FormEvent, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";
import { normalizeAccessCode } from "./auth";
import { ArrowIcon, Brand } from "./components";

type Authenticate = (code: string) => Promise<void>;

export function AccessScreen({ onAuthenticate }: { onAuthenticate: Authenticate }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function submitAccess(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = normalizeAccessCode(code);
    if (!normalized) {
      setError("Введите код доступа.");
      inputRef.current?.focus();
      return;
    }

    setBusy(true);
    setError("");

    try {
      await onAuthenticate(normalized);
    } catch (caught) {
      setBusy(false);
      setError(
        caught instanceof ApiError || caught instanceof Error
          ? caught.message
          : "Не удалось проверить код. Повторите попытку.",
      );
      inputRef.current?.focus();
    }
  }

  return (
    <div className="access-page">
      <header className="public-header">
        <Brand />
        <div className="public-header__meta">
          <span>ver. 0.0.1 under development</span>
        </div>
      </header>

      <main className="access-layout">
        <section className="gate-panel" aria-labelledby="gateTitle">
          <div className="gate-panel__content">
            <h2 id="gateTitle">Введите код доступа</h2>

            <form className="access-form" onSubmit={submitAccess} noValidate>
              <div className={`access-input ${error ? "access-input--error" : ""}`}>
                <span aria-hidden="true">SG</span>
                <input
                  ref={inputRef}
                  id="accessCode"
                  name="accessCode"
                  aria-label="Персональный код"
                  value={code}
                  onChange={(event) => {
                    setCode(event.target.value.toUpperCase());
                    setError("");
                  }}
                  autoComplete="one-time-code"
                  autoCapitalize="characters"
                  spellCheck={false}
                  maxLength={24}
                  placeholder="XXXX-XXXX"
                  aria-describedby="accessHint accessError"
                  aria-invalid={Boolean(error)}
                />
              </div>
              <p className="field-hint" id="accessHint">
                Дефисы и регистр не имеют значения
              </p>
              <p className="field-error" id="accessError" role="alert">
                {error}
              </p>
              <button className="primary-action" type="submit" disabled={busy || !code.trim()}>
                <span>{busy ? "Проверяем код…" : "Продолжить"}</span>
                <ArrowIcon />
              </button>
            </form>
          </div>
        </section>
      </main>
    </div>
  );
}
