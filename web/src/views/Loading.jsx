import { useI18n } from '../i18n.js';

/** The loading and error states every view shares. */
export default function Loading({ state, children }) {
  const { t } = useI18n();
  if (state.loading) return <p className="muted">{t('loading')}</p>;
  if (state.error) return <p className="error">{state.error}</p>;
  return children(state.data);
}
