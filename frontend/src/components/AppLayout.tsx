import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

/** Shared nav shell for every authenticated page. */
export function AppLayout() {
  const { username, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-title">Classiflow - Scrapper Console</span>
        <nav className="app-nav">
          <NavLink to="/upload" className={({ isActive }) => (isActive ? "active" : "")}>
            New scrape
          </NavLink>
          <NavLink to="/executions" className={({ isActive }) => (isActive ? "active" : "")}>
            Executions
          </NavLink>
          <NavLink to="/files" className={({ isActive }) => (isActive ? "active" : "")}>
            Files
          </NavLink>
        </nav>
        <div className="app-user">
          {username && <span className="app-username">{username}</span>}
          <button type="button" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
