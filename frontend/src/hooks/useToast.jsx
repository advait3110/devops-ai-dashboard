import { useRef, useState } from "react";

/** Small confirmation message after an action ("Build queued", "Container restarted"). */
export default function useToast() {
  const [toast, setToast] = useState(null);
  const timer = useRef(null);
  const show = (text, kind = "ok") => {
    clearTimeout(timer.current);
    setToast({ text, kind });
    timer.current = setTimeout(() => setToast(null), 4000);
  };
  const node = toast && (
    <div className={`toast toast-${toast.kind}`} role="status">
      {toast.text}
    </div>
  );
  return [show, node];
}
