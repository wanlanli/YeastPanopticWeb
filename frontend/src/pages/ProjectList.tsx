import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { Project } from '../api/types';
import { useAuthStore } from '../store/useAuthStore';
import './ProjectList.css';

export function ProjectList() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState('');
  const { user, loading, logout } = useAuthStore();

  useEffect(() => {
    api.listProjects().then(setProjects);
  }, [user]);

  async function createProject() {
    if (!name.trim()) return;
    const created = await api.createProject(name.trim());
    setProjects((prev) => [created, ...prev]);
    setName('');
  }

  return (
    <div className="project-list-page">
      <div className="page-header">
        <div>
          <h1>YeastPanoptic</h1>
          <p className="subtitle">Microscopy image annotation &amp; quantification</p>
        </div>
        {!loading && (
          <div className="auth-status">
            {user ? (
              <>
                <span>{user.email}</span>
                <button onClick={() => logout()}>Sign out</button>
              </>
            ) : (
              <>
                <Link to="/login">Sign in</Link>
                <Link to="/register" className="auth-status-cta">
                  Create account
                </Link>
              </>
            )}
          </div>
        )}
      </div>

      {!loading && !user && (
        <div className="sandbox-banner">
          Trying it out without an account — your uploads and analyses here are
          temporary and will be deleted after a couple of hours.{' '}
          <Link to="/register">Sign in</Link> to keep your work permanently.
        </div>
      )}

      <div className="create-project">
        <input
          placeholder="New project name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && createProject()}
        />
        <button onClick={createProject} disabled={!name.trim()}>
          Create
        </button>
      </div>

      <ul className="project-grid">
        {projects.map((p) => (
          <li key={p.id} className="project-card">
            <div className="project-card-name">
              {p.name}
              {p.is_sample && <span className="project-badge project-badge-sample">Sample</span>}
              {p.is_sandbox && <span className="project-badge project-badge-sandbox">Temporary</span>}
            </div>
            <div className="project-card-links">
              <Link to={`/project/${p.id}/viewer`}>Viewer</Link>
              <Link to={`/project/${p.id}/quantification`}>Quantification</Link>
            </div>
          </li>
        ))}
        {projects.length === 0 && <li className="empty-hint">No projects yet — create one above.</li>}
      </ul>
    </div>
  );
}
