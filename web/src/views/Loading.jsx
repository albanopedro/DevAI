/** The loading and error states every view shares. */
export default function Loading({ state, children }) {
  if (state.loading) return <p className="muted">Reading the project…</p>;
  if (state.error) return <p className="error">{state.error}</p>;
  return children(state.data);
}
