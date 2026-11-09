/* Side drawer that shows a log (build console, container or pod log) with "Explain with AI". */
import { ScrollText, X } from "lucide-react";
import { useEffect, useState } from "react";
import AiExplainPanel, { ExplainButton } from "./AiExplain";
import LogViewer from "./LogViewer";
import { Loading, Notice } from "./ui";

/** view = { title, source, context, load: () => Promise<string> } | null */
export default function LogDrawer({ view, onClose }) {
  const [state, setState] = useState({ text: "", loading: false, error: null });
  const [explain, setExplain] = useState(null);

  useEffect(() => {
    if (!view) return undefined;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- start of an async request
    setState({ text: "", loading: true, error: null });
    view
      .load()
      .then((text) => !cancelled && setState({ text, loading: false, error: null }))
      .catch((error) => !cancelled && setState({ text: "", loading: false, error }));
    return () => {
      cancelled = true;
    };
  }, [view]);

  if (!view) return null;
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose}>
        <aside className="drawer wide" role="dialog" aria-modal="true" aria-label={view.title} onClick={(e) => e.stopPropagation()}>
          <div className="drawer-head">
            <div>
              <h2><ScrollText size={18} /> {view.title}</h2>
              <p className="panel-sub">{view.source}</p>
            </div>
            <div className="panel-actions">
              {state.text && (
                <ExplainButton
                  onClick={() =>
                    setExplain({ title: view.title, text: state.text, source: view.source, context: view.context })
                  }
                />
              )}
              <button className="btn ghost icon" onClick={onClose} aria-label="Close">
                <X size={18} />
              </button>
            </div>
          </div>
          <div className="drawer-body">
            {state.loading && <Loading label="Fetching log" />}
            <Notice error={state.error} />
            {!state.loading && !state.error && <LogViewer text={state.text} height={10000} />}
          </div>
        </aside>
      </div>
      <AiExplainPanel request={explain} onClose={() => setExplain(null)} />
    </>
  );
}
