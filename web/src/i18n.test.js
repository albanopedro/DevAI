import { describe, expect, test } from 'vitest';
import {
  consentQuestion,
  initialLanguage,
  LANGUAGES,
  messageKeys,
  saveLanguage,
  sentFiles,
  translate,
} from './i18n.js';

const placeholders = (text) => [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort();

describe('the dictionaries', () => {
  test('every text exists in every language', () => {
    const english = messageKeys('en').sort();
    for (const language of Object.keys(LANGUAGES)) {
      expect(messageKeys(language).sort()).toEqual(english);
    }
  });

  test('every translation keeps the same {placeholders}', () => {
    for (const key of messageKeys('en')) {
      expect([key, placeholders(translate('pt', key))]).toEqual([key, placeholders(translate('en', key))]);
    }
  });
});

describe('translate', () => {
  test('fills placeholders', () => {
    expect(translate('pt', 'docs.documented', { documented: 6, total: 15 })).toBe(
      '6 de 15 nomes públicos documentados.',
    );
  });

  test('falls back to English, then to the key', () => {
    expect(translate('fr', 'ai.send')).toBe('Send');
    expect(translate('pt', 'no.such.key')).toBe('no.such.key');
  });
});

describe('the language at start', () => {
  const storage = (value) => ({ getItem: () => value, setItem: () => {} });

  test('the one chosen before wins', () => {
    expect(initialLanguage(storage('pt'), 'en-US')).toBe('pt');
    expect(initialLanguage(storage('en'), 'pt-BR')).toBe('en');
  });

  test("otherwise, the browser's language", () => {
    expect(initialLanguage(storage(null), 'pt-BR')).toBe('pt');
    expect(initialLanguage(storage(null), 'pt-PT')).toBe('pt');
    expect(initialLanguage(storage(null), 'de-DE')).toBe('en');
    expect(initialLanguage(storage('klingon'), 'en-US')).toBe('en');
  });

  test('a browser that refuses storage still works', () => {
    const refusing = {
      getItem: () => {
        throw new Error('denied');
      },
      setItem: () => {
        throw new Error('denied');
      },
    };
    expect(initialLanguage(refusing, 'pt-BR')).toBe('pt');
    expect(() => saveLanguage('pt', refusing)).not.toThrow();
  });
});

describe('the consent question in Portuguese', () => {
  const t = (key, values) => translate('pt', key, values);
  const number = (value) => Number(value).toLocaleString('pt-BR');
  const preview = (task, context) => ({ task, context, tokens: 1352, destination: 'OpenCode (grátis)' });

  test('names the files that would be sent', () => {
    const question = consentQuestion(t, number, preview('docs', { file: { path: 'bookshelf/loans.py' } }));

    expect(question).toBe('Enviar 1 arquivo(s) (~1.352 tokens) para OpenCode (grátis)? Arquivos: bookshelf/loans.py.');
  });

  test('says when no source code goes', () => {
    expect(consentQuestion(t, number, preview('analysis', {}))).toBe(
      'Enviar um resumo do projeto, sem código-fonte (~1.352 tokens), para OpenCode (grátis)?',
    );
  });

  test('names the issue', () => {
    const context = { issue: { repo: 'octo/stats', number: 7 }, files: [{ path: 'stats.py' }] };

    expect(consentQuestion(t, number, preview('issue', context))).toBe(
      'Enviar a issue octo/stats#7 e 1 arquivo(s): stats.py (~1.352 tokens) para OpenCode (grátis)?',
    );
  });

  test('every task says which files', () => {
    expect(sentFiles('review', { diffs: [{ path: 'a.py' }] })).toEqual(['a.py']);
    expect(sentFiles('pull', { diffs: [{ path: 'b.py' }] })).toEqual(['b.py']);
    expect(sentFiles('fix', { files: [{ path: 'c.py' }] })).toEqual(['c.py']);
    expect(sentFiles('readme', { readme: { exists: true, path: 'README.md' } })).toEqual(['README.md']);
    expect(sentFiles('readme', { readme: { exists: false, path: null } })).toEqual([]);
    expect(sentFiles('tests', { source: { path: 's.py' }, existing_tests: [{ path: 'tests/test_s.py' }] })).toEqual([
      's.py',
      'tests/test_s.py',
    ]);
    expect(sentFiles('analysis', {})).toEqual([]);
  });
});
