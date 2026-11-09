/* Module 3 - CI/CD Monitoring: Jenkins jobs and GitHub Actions workflow runs. */
import { ChevronDown, ChevronRight, ExternalLink, Play, RotateCw } from "lucide-react";
import { Fragment, useState } from "react";
import { api, qs } from "../api";
import LogDrawer from "../components/LogDrawer";
import { Empty, Loading, Notice, PageHeader, Panel, Status } from "../components/ui";
import usePolling from "../hooks/usePolling";
import useToast from "../hooks/useToast";
import { duration, timeAgo } from "../utils/format";

function Jenkins({ openLog, notify }) {
  const { data, error, loading, refresh } = usePolling(() => api.get("/api/cicd/jenkins/jobs"), 10000);
  const [busy, setBusy] = useState(null);

  const build = async (job) => {
    setBusy(job);
    try {
      await api.post(`/api/cicd/jenkins/build?${qs({ job })}`);
      notify(`Build queued for ${job}`);
      setTimeout(refresh, 3000);
    } catch (e) {
      notify(e.message, "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Panel title="Jenkins" subtitle="Jobs and their last build" flush>
      {loading && !data && <Loading />}
      {error && !data && <div className="pad"><Notice error={error} /></div>}
      {data && data.length === 0 && <Empty>Jenkins has no jobs yet. Create a Pipeline job from the Jenkinsfile in this repo.</Empty>}
      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Job</th><th>Status</th><th>Build</th><th>Duration</th><th>Started</th><th>Health</th><th className="num">Actions</th></tr>
            </thead>
            <tbody>
              {data.map((j) => {
                const b = j.last_build || {};
                return (
                  <tr key={j.name}>
                    <td><a href={j.url} target="_blank" rel="noreferrer" className="link">{j.name}</a></td>
                    <td><Status value={j.status} /></td>
                    <td>{b.number ? `#${b.number}` : "-"}</td>
                    <td>{b.building ? "running" : b.duration ? duration(b.duration / 1000) : "-"}</td>
                    <td className="muted">{b.timestamp ? timeAgo(b.timestamp) : "-"}</td>
                    <td className="muted" title={j.health}>{j.health_score ?? "-"}{j.health_score !== null && j.health_score !== undefined ? "%" : ""}</td>
                    <td className="num actions">
                      {b.number && (
                        <button
                          className={`btn sm ${j.status === "failed" ? "ai" : "ghost"}`}
                          onClick={() =>
                            openLog({
                              title: `${j.name} #${b.number}`,
                              source: "Jenkins console output",
                              context: `Jenkins job ${j.name}, build #${b.number}, result ${j.status}`,
                              load: () => api.get(`/api/cicd/jenkins/console?${qs({ job: j.name, build: b.number })}`).then((r) => r.log),
                            })
                          }
                        >
                          {j.status === "failed" ? "Diagnose" : "Console"}
                        </button>
                      )}
                      <button className="btn ghost sm" disabled={busy === j.name} onClick={() => build(j.name)}>
                        <Play size={14} /> Build
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function RunJobs({ repo, runId, openLog }) {
  const { data, error } = usePolling(() => api.get(`/api/cicd/github/jobs?${qs({ repo, run_id: runId })}`), 0);
  if (error) return <Notice error={error} />;
  if (!data) return <Loading label="Loading jobs" />;
  return (
    <ul className="job-steps">
      {data.map((job) => (
        <li key={job.id}>
          <div className="job-head">
            <Status value={job.status} label={job.name} />
            <button
              className={`btn sm ${job.status === "failed" ? "ai" : "ghost"}`}
              onClick={() =>
                openLog({
                  title: `${repo}: ${job.name}`,
                  source: "GitHub Actions job log",
                  context: `GitHub Actions job '${job.name}' in ${repo}, status ${job.status}`,
                  load: () => api.get(`/api/cicd/github/logs?${qs({ repo, job_id: job.id })}`).then((r) => r.log),
                })
              }
            >
              {job.status === "failed" ? "Diagnose" : "Log"}
            </button>
          </div>
          <ol>
            {job.steps.map((s) => (
              <li key={s.number}><Status value={s.status} label={s.name} /></li>
            ))}
          </ol>
        </li>
      ))}
    </ul>
  );
}

function GitHub({ openLog, notify }) {
  const { data, error, loading, refresh } = usePolling(() => api.get("/api/cicd/github/runs?limit=15"), 30000);
  const [open, setOpen] = useState(null);

  const rerun = async (run) => {
    try {
      await api.post(`/api/cicd/github/rerun?${qs({ repo: run.repo, run_id: run.id })}`);
      notify(`Re-running failed jobs of ${run.workflow} #${run.run_number}`);
      setTimeout(refresh, 4000);
    } catch (e) {
      notify(e.message, "error");
    }
  };

  return (
    <Panel title="GitHub Actions" subtitle="Latest workflow runs. Open a run to see its jobs and steps." flush>
      {loading && !data && <Loading />}
      {error && !data && <div className="pad"><Notice error={error} /></div>}
      {data && data.length === 0 && <Empty>No workflow runs yet. Push a commit to trigger .github/workflows/ci.yml.</Empty>}
      {data && data.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th aria-label="Expand" /><th>Workflow</th><th>Status</th><th>Commit</th><th>Branch</th><th>Started</th><th className="num">Actions</th></tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <Fragment key={r.id}>
                  <tr className="clickable" onClick={() => setOpen(open === r.id ? null : r.id)}>
                    <td>{open === r.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</td>
                    <td>
                      <div>{r.workflow} <span className="muted">#{r.run_number}</span></div>
                      <div className="cell-sub">{r.title}</div>
                    </td>
                    <td><Status value={r.status} /></td>
                    <td className="mono-cell">{r.commit}</td>
                    <td>{r.branch}</td>
                    <td className="muted">{timeAgo(r.created_at)}</td>
                    <td className="num actions" onClick={(e) => e.stopPropagation()}>
                      {r.status === "failed" && (
                        <button className="btn ghost sm" onClick={() => rerun(r)}><RotateCw size={14} /> Re-run</button>
                      )}
                      <a className="btn ghost sm icon" href={r.url} target="_blank" rel="noreferrer" aria-label="Open on GitHub">
                        <ExternalLink size={14} />
                      </a>
                    </td>
                  </tr>
                  {open === r.id && (
                    <tr className="expanded">
                      <td colSpan={7}><RunJobs repo={r.repo} runId={r.id} openLog={openLog} /></td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

export default function CICD() {
  const [logView, setLogView] = useState(null);
  const [notify, toast] = useToast();
  return (
    <>
      <PageHeader
        title="Pipelines"
        description="Builds from Jenkins and GitHub Actions. Failed builds can be diagnosed by the AI from their real log."
      />
      <Jenkins openLog={setLogView} notify={notify} />
      <GitHub openLog={setLogView} notify={notify} />
      <LogDrawer view={logView} onClose={() => setLogView(null)} />
      {toast}
    </>
  );
}
