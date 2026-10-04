import { useEffect, useState } from 'react';

/** Load one report of a project; `version` changes to load it again. */
export function useView(api, projectId, view, version) {
  const [state, setState] = useState({ loading: true });
  useEffect(() => {
    let current = true;
    setState({ loading: true });
    api.view(projectId, view).then(
      (data) => current && setState({ data }),
      (problem) => current && setState({ error: problem.message }),
    );
    return () => {
      current = false;
    };
  }, [api, projectId, view, version]);
  return state;
}
