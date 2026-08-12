import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, LockKeyhole, ShieldAlert } from "lucide-react";
import { api } from "./api";
import { App } from "./App";
import type { AuthUser } from "./types";

export function AuthGate() {
  // Session lookup happens before App mounts, preventing protected queries from
  // briefly running as an anonymous user. Mock identities are fetched only
  // after session lookup fails and exist only when AUTH_MODE=mock.
  const queryClient = useQueryClient();
  const session = useQuery({
    queryKey: ["auth", "me"],
    queryFn: api.authMe,
    retry: false,
  });
  const users = useQuery({
    queryKey: ["auth", "mock-users"],
    queryFn: api.mockUsers,
    enabled: session.isError,
    retry: false,
  });
  const login = useMutation({
    mutationFn: api.mockLogin,
    onSuccess: (user) => queryClient.setQueryData(["auth", "me"], user),
  });
  const logout = async () => {
    await api.logout();
    queryClient.clear();
    window.location.reload();
  };

  if (session.isLoading) {
    return (
      <AuthSurface>
        <Loader2 className="spin" />
        <h1>Checking your LiMon access…</h1>
      </AuthSurface>
    );
  }
  if (session.data && !session.data.hasAccess) {
    return (
      <AuthSurface>
        <ShieldAlert />
        <h1>Access not granted</h1>
        <p>
          {session.data.displayName} is authenticated by SSO but has no LiMon
          application role.
        </p>
        <button onClick={logout}>Sign in with another identity</button>
      </AuthSurface>
    );
  }
  if (session.data) return <App user={session.data} onLogout={logout} />;

  return (
    <AuthSurface>
      <LockKeyhole />
      <span className="auth-eyebrow">MOCK CACIB SSO</span>
      <h1>Sign in to LiMon</h1>
      <p>Select a development identity to test application access and roles.</p>
      {users.isLoading ? (
        <div className="auth-loading">
          <Loader2 className="spin" /> Loading development identities…
        </div>
      ) : users.isError ? (
        <div className="auth-backend-error" role="alert">
          <ShieldAlert />
          <div>
            <strong>Mock SSO is unavailable</strong>
            <span>
              Restart the FastAPI backend with AUTH_MODE=mock, then refresh this
              page. {users.error.message}
            </span>
          </div>
        </div>
      ) : (
        <div className="mock-identities">
          {users.data?.map((user) => (
            <button
              key={user.username}
              disabled={login.isPending}
              onClick={() => login.mutate(user.username)}
            >
              <strong>{user.displayName}</strong>
              <span>{user.roles.join(", ") || "No application access"}</span>
            </button>
          ))}
        </div>
      )}
      {login.isError && <p className="auth-error">{login.error.message}</p>}
    </AuthSurface>
  );
}

function AuthSurface({ children }: { children: React.ReactNode }) {
  return (
    <main className="auth-page">
      <section className="auth-panel">{children}</section>
    </main>
  );
}
