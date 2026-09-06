import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { Project } from '../api/types';
import './ProjectList.css';

export function ProjectList() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState('');

  useEffect(() => {
    api.listProjects().then(setProjects);
  }, []);

  async function createProject() {
    if (!name.trim()) return;
    const created = await api.createProject(name.trim());
    setProjects((prev) => [created, ...prev]);
    setName('');
  }

  return (
    <div className="project-list-page">
      <h1>YeastPanoptic</h1>
      <p className="subtitle">Microscopy image annotation &amp; quantification</p>

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
            <div className="project-card-name">{p.name}</div>
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
