import { createContext, useContext } from 'react';

/**
 * The pages in English and Brazilian Portuguese. Only the page itself is
 * translated: what the server writes (check messages, errors) and what the
 * AI writes keep their own language. The consent question is the exception:
 * in Portuguese, the page builds it from the preview's facts.
 */

export const LANGUAGES = { en: 'English', pt: 'Português' };
export const LOCALES = { en: 'en-US', pt: 'pt-BR' };
const STORAGE_KEY = 'devai-language';

const MESSAGES = {
  en: {
    'app.noToken.before': 'Open this page with the address ',
    'app.noToken.after':
      ' printed in your terminal: it carries the key that lets this page talk to DevAI.',
    'app.project': 'project',
    'app.provider': 'AI provider',
    'app.language': 'Language',
    'app.refresh': 'Refresh',
    'app.dismiss': 'Dismiss',
    'app.footer':
      'Runs on this computer only. Nothing goes to an AI until you press Send on a preview, and nothing is written until you confirm.',
    'provider.default': 'AI: default',
    'provider.opencode': 'AI: OpenCode free model (online)',
    'provider.ollama': 'AI: Ollama (this computer)',
    'notice.posted': 'Posted on GitHub: ',
    'notice.postedAfter': ". To remove it, delete the comment there: DevAI can't.",
    'notice.written': 'Written: {files}. Undo with: ',
    'notice.nothingCommitted': '. Nothing was committed.',
    'tab.overview': 'Overview',
    'tab.review': 'Review',
    'tab.tests': 'Tests',
    'tab.docs': 'Docs',
    'tab.fix': 'Fix',
    'tab.github': 'GitHub',
    loading: 'Reading the project…',
    yes: 'yes',
    no: 'no',
    none: 'none',
    'none.found': 'None.',
    filesCount: '{count} file(s)',
    'overview.files': 'Files',
    'overview.git': 'Git',
    'overview.languages': 'Languages',
    'overview.frameworks': 'Frameworks',
    'overview.noneDetected': 'none detected',
    'overview.tests': 'Tests',
    'overview.findings': 'Findings',
    'overview.aiTitle': 'AI analysis',
    'overview.aiHint':
      'Sends a summary of the project (no source code) to a free model, after you see it.',
    'overview.aiButton': 'Analyze with AI…',
    'review.none': 'No changes to review.',
    'review.checks': 'Checks',
    'review.aiTitle': 'AI review',
    'review.aiHint': 'Sends the changed lines (secrets hidden), after you see them.',
    'review.aiButton': 'Review with AI…',
    'tests.summary': '{tests} test file(s){frameworks}, {sources} source file(s) checked.',
    'tests.allCovered': 'Every checked file seems to have tests.',
    'tests.noTestFile': 'no test file',
    'tests.untested': ' names no test mentions: {names}',
    'tests.aiButton': 'Write tests with AI…',
    'tests.estimate': 'An estimate from file and symbol names. DevAI never runs tests: you do.',
    'docs.noNames': 'No public functions or classes found.',
    'docs.documented': '{documented} of {total} public names documented.',
    'docs.withoutDocs': 'Names without docs',
    'docs.aiButton': 'Write docs with AI…',
    'docs.noReadme': 'No README at the project root.',
    'docs.notChecked': '{path}: not checked (only Markdown is read).',
    'docs.sections': '{path}: sections found: {found}; missing: {missing}.',
    'docs.failing': 'Commands in the README that would fail:',
    'docs.failingItem': ' (line {line}): no package.json has this script',
    'docs.readmeButton': 'Write README sections with AI…',
    'topic.installation': 'installation',
    'topic.usage': 'usage',
    'topic.tests': 'tests',
    'topic.license': 'license',
    'fix.hint':
      'Describe a change and name up to 3 files. The AI proposes it as a diff; nothing is written until you confirm, and only if those files are committed and unchanged.',
    'fix.what': 'What should change?',
    'fix.files': 'Files (paths in the project, one per line)',
    'fix.aiButton': 'Propose a fix with AI…',
    'github.intro':
      '{repo}: read with your GitHub CLI (gh). DevAI never merges, closes, approves or creates anything; a comment is posted only after you read it and confirm.',
    'github.pulls': 'Open pull requests',
    'github.issues': 'Open issues',
    'github.draft': ' · draft',
    'github.check': 'Check',
    'github.planButton': 'Plan with AI…',
    'github.pullChecks': '{count} file(s) changed. Local checks, no AI:',
    'findings.none': 'No findings.',
    'severity.high': 'HIGH',
    'severity.medium': 'MEDIUM',
    'severity.low': 'LOW',
    'ai.preparing': 'Preparing what would be sent… (nothing is sent yet)',
    'ai.before': 'Before anything is sent',
    'ai.leaves': 'Leaves this computer: ',
    'ai.stays': 'Stays on this computer: ',
    'ai.note': 'Note: {note}.',
    'ai.size':
      '{characters} characters (~{tokens} tokens), {redacted} line(s) hidden as possible secrets.',
    'ai.exactly': 'Exactly what would be sent',
    'ai.waiting': 'Waiting for the AI… this can take a minute.',
    'ai.send': 'Send',
    'ai.cancel': 'Cancel',
    'ai.answer': 'AI answer',
    'ai.close': 'Close',
    'ai.posted': 'Posted on {files}: ',
    'ai.done': 'Done: {files}. Undo with: ',
    'apply.apply': 'Apply',
    'apply.cant': "Can't apply now: {reason}.",
    'apply.write': 'Apply to {files}…',
    'apply.create': 'Create {files}…',
    'apply.comment': 'Post as a comment on {files}…',
    'apply.commentBefore': 'Post this comment on {files} as ',
    'apply.commentAfter':
      '? Everyone who can see it on GitHub will see it. Mentions and #references are broken on purpose.',
    'apply.yesPost': 'Yes, post it',
    'apply.createConfirm': "Create {files}? It is created only if it doesn't exist yet.",
    'apply.writeConfirm':
      'Write these changes to {files}? DevAI checks again that nothing changed since it read them. Undo with git restore.',
    'apply.yesCreate': 'Yes, create it',
    'apply.yesWrite': 'Yes, write it',
    'result.none': 'No answer.',
    'result.usage': '{model} · {input} tokens in / {output} out',
    'result.rejected': 'Rejected by DevAI: {reason}. Nothing will be changed.',
    'result.docsCheckedPython':
      'Only documentation changed: checked. Without docstrings, the code parses to exactly the same syntax tree as before.',
    'result.docsCheckedJs':
      'Only documentation changed: checked. Each addition is a single /** */ comment right above an export, with no code in it.',
    'result.readmeCreated':
      'A new README.md: checked. devai docs finds each section, and every npm command in it runs a script that exists.',
    'result.readmeAdded':
      'Only additions: checked. Every line of the README is still there, unchanged and in order, and no new npm command fails.',
    'result.commentBlocked': "Can't offer it as a comment: {reason}.",
    'result.notes': 'Notes from the AI',
    'result.writtenByAi': 'Written by AI. Read it before applying anything.',
    'result.risks': 'Risks',
    'result.recommendations': 'Recommendations',
    'result.effort': '[{effort} effort]',
    'effort.small': 'small',
    'effort.medium': 'medium',
    'effort.large': 'large',
    'result.limitations': 'Limitations',
    'result.issues': 'Issues',
    'result.noneFound': 'None found.',
    'result.suggestion': 'Suggestion: {text}',
    'result.discarded': "{count} issue(s) about code the AI wasn't shown were discarded.",
    'result.suggestedTests': 'Suggested tests',
    'result.noChange': 'No usable change in the answer.',
    'result.added': 'Added: {items}',
    'result.notUsed': 'Not used',
    'result.links': 'Links the AI wrote (check them)',
    'result.notAsked': 'Not asked',
    'result.filesToLook': 'Files to look at',
    'result.filesDropped': "{count} file(s) the AI wasn't shown were left out.",
    'result.steps': 'Steps',
    'result.tests': 'Tests',
    'result.questions': 'Open questions',
    'result.noFixChange': 'No change proposed.',
    'result.howToVerify': 'How to verify',
    'result.newFile': 'New file: ',
    'result.runThem': 'Run them yourself with: ',
    'result.neverRuns': '. DevAI never runs them.',
    'question.files': 'Send {count} file(s) (~{tokens} tokens) to {destination}? Files: {files}.',
    'question.summary':
      'Send a summary of the project, no source code (~{tokens} tokens), to {destination}?',
    'question.issue': 'Send issue {issue}{files} (~{tokens} tokens) to {destination}?',
    'question.issueFiles': ' and {count} file(s): {files}',
  },
  pt: {
    'app.noToken.before': 'Abra esta página pelo endereço que o ',
    'app.noToken.after':
      ' mostrou no seu terminal: ele traz a chave que deixa esta página falar com o DevAI.',
    'app.project': 'projeto',
    'app.provider': 'Provedor de IA',
    'app.language': 'Idioma',
    'app.refresh': 'Atualizar',
    'app.dismiss': 'Fechar',
    'app.footer':
      'Roda só neste computador. Nada vai para uma IA até você apertar Enviar numa prévia, e nada é gravado até você confirmar.',
    'provider.default': 'IA: padrão',
    'provider.opencode': 'IA: modelo grátis do OpenCode (online)',
    'provider.ollama': 'IA: Ollama (este computador)',
    'notice.posted': 'Publicado no GitHub: ',
    'notice.postedAfter': '. Para remover, apague o comentário lá: o DevAI não consegue.',
    'notice.written': 'Gravado: {files}. Para desfazer: ',
    'notice.nothingCommitted': '. Nada foi commitado.',
    'tab.overview': 'Visão geral',
    'tab.review': 'Revisão',
    'tab.tests': 'Testes',
    'tab.docs': 'Documentação',
    'tab.fix': 'Correção',
    'tab.github': 'GitHub',
    loading: 'Lendo o projeto…',
    yes: 'sim',
    no: 'não',
    none: 'nenhuma',
    'none.found': 'Nenhum.',
    filesCount: '{count} arquivo(s)',
    'overview.files': 'Arquivos',
    'overview.git': 'Git',
    'overview.languages': 'Linguagens',
    'overview.frameworks': 'Frameworks',
    'overview.noneDetected': 'nenhum detectado',
    'overview.tests': 'Testes',
    'overview.findings': 'Achados',
    'overview.aiTitle': 'Análise com IA',
    'overview.aiHint':
      'Envia um resumo do projeto (sem código-fonte) para um modelo grátis, depois que você vê o que vai.',
    'overview.aiButton': 'Analisar com IA…',
    'review.none': 'Nenhuma mudança para revisar.',
    'review.checks': 'Checagens',
    'review.aiTitle': 'Revisão com IA',
    'review.aiHint': 'Envia as linhas alteradas (com secrets escondidos), depois que você as vê.',
    'review.aiButton': 'Revisar com IA…',
    'tests.summary':
      '{tests} arquivo(s) de teste{frameworks}, {sources} arquivo(s) de código verificado(s).',
    'tests.allCovered': 'Todo arquivo verificado parece ter testes.',
    'tests.noTestFile': 'sem arquivo de teste',
    'tests.untested': ' nomes que nenhum teste cita: {names}',
    'tests.aiButton': 'Escrever testes com IA…',
    'tests.estimate':
      'Uma estimativa pelos nomes de arquivos e funções. O DevAI nunca roda testes: quem roda é você.',
    'docs.noNames': 'Nenhuma função ou classe pública encontrada.',
    'docs.documented': '{documented} de {total} nomes públicos documentados.',
    'docs.withoutDocs': 'Nomes sem documentação',
    'docs.aiButton': 'Escrever docs com IA…',
    'docs.noReadme': 'Nenhum README na raiz do projeto.',
    'docs.notChecked': '{path}: não verificado (só Markdown é lido).',
    'docs.sections': '{path}: seções encontradas: {found}; faltando: {missing}.',
    'docs.failing': 'Comandos do README que falhariam:',
    'docs.failingItem': ' (linha {line}): nenhum package.json tem esse script',
    'docs.readmeButton': 'Escrever seções do README com IA…',
    'topic.installation': 'instalação',
    'topic.usage': 'uso',
    'topic.tests': 'testes',
    'topic.license': 'licença',
    'fix.hint':
      'Descreva uma mudança e cite até 3 arquivos. A IA propõe como um diff; nada é gravado até você confirmar, e só se esses arquivos estiverem commitados e sem alterações.',
    'fix.what': 'O que deve mudar?',
    'fix.files': 'Arquivos (caminhos no projeto, um por linha)',
    'fix.aiButton': 'Propor uma correção com IA…',
    'github.intro':
      '{repo}: lido pelo seu GitHub CLI (gh). O DevAI nunca faz merge, fecha, aprova ou cria nada; um comentário só é publicado depois que você lê e confirma.',
    'github.pulls': 'Pull requests abertos',
    'github.issues': 'Issues abertas',
    'github.draft': ' · rascunho',
    'github.check': 'Checar',
    'github.planButton': 'Planejar com IA…',
    'github.pullChecks': '{count} arquivo(s) alterado(s). Checagens locais, sem IA:',
    'findings.none': 'Nenhum achado.',
    'severity.high': 'ALTA',
    'severity.medium': 'MÉDIA',
    'severity.low': 'BAIXA',
    'ai.preparing': 'Preparando o que seria enviado… (nada foi enviado ainda)',
    'ai.before': 'Antes de enviar qualquer coisa',
    'ai.leaves': 'Sai deste computador: ',
    'ai.stays': 'Fica neste computador: ',
    'ai.note': 'Observação: {note}.',
    'ai.size':
      '{characters} caracteres (~{tokens} tokens), {redacted} linha(s) escondida(s) por parecer(em) secrets.',
    'ai.exactly': 'Exatamente o que seria enviado',
    'ai.waiting': 'Esperando a IA… pode levar um minuto.',
    'ai.send': 'Enviar',
    'ai.cancel': 'Cancelar',
    'ai.answer': 'Resposta da IA',
    'ai.close': 'Fechar',
    'ai.posted': 'Publicado em {files}: ',
    'ai.done': 'Feito: {files}. Para desfazer: ',
    'apply.apply': 'Aplicar',
    'apply.cant': 'Não dá para aplicar agora: {reason}.',
    'apply.write': 'Aplicar em {files}…',
    'apply.create': 'Criar {files}…',
    'apply.comment': 'Publicar como comentário em {files}…',
    'apply.commentBefore': 'Publicar este comentário em {files} como ',
    'apply.commentAfter':
      '? Todos que podem ver no GitHub vão ver. Menções e #referências foram quebradas de propósito.',
    'apply.yesPost': 'Sim, publicar',
    'apply.createConfirm': 'Criar {files}? Só é criado se ainda não existir.',
    'apply.writeConfirm':
      'Gravar estas mudanças em {files}? O DevAI confere de novo se nada mudou desde que leu. Para desfazer: git restore.',
    'apply.yesCreate': 'Sim, criar',
    'apply.yesWrite': 'Sim, gravar',
    'result.none': 'Sem resposta.',
    'result.usage': '{model} · {input} tokens enviados / {output} recebidos',
    'result.rejected': 'Recusado pelo DevAI: {reason}. Nada será alterado.',
    'result.docsCheckedPython':
      'Só a documentação mudou: conferido. Sem as docstrings, o código gera exatamente a mesma árvore sintática de antes.',
    'result.docsCheckedJs':
      'Só a documentação mudou: conferido. Cada acréscimo é um único comentário /** */ logo acima de um export, sem código dentro.',
    'result.readmeCreated':
      'Um README.md novo: conferido. O devai docs encontra cada seção, e todo comando npm nele roda um script que existe.',
    'result.readmeAdded':
      'Só acréscimos: conferido. Toda linha do README continua lá, igual e na mesma ordem, e nenhum comando npm novo falha.',
    'result.commentBlocked': 'Não dá para oferecer como comentário: {reason}.',
    'result.notes': 'Observações da IA',
    'result.writtenByAi': 'Escrito por IA. Leia antes de aplicar qualquer coisa.',
    'result.risks': 'Riscos',
    'result.recommendations': 'Recomendações',
    'result.effort': '[esforço {effort}]',
    'effort.small': 'pequeno',
    'effort.medium': 'médio',
    'effort.large': 'grande',
    'result.limitations': 'Limitações',
    'result.issues': 'Problemas',
    'result.noneFound': 'Nenhum encontrado.',
    'result.suggestion': 'Sugestão: {text}',
    'result.discarded': '{count} problema(s) sobre código que a IA não viu foram descartados.',
    'result.suggestedTests': 'Testes sugeridos',
    'result.noChange': 'Nenhuma mudança aproveitável na resposta.',
    'result.added': 'Adicionado: {items}',
    'result.notUsed': 'Não usado',
    'result.links': 'Links que a IA escreveu (confira)',
    'result.notAsked': 'Não pedido',
    'result.filesToLook': 'Arquivos para olhar',
    'result.filesDropped': '{count} arquivo(s) que a IA não viu ficaram de fora.',
    'result.steps': 'Passos',
    'result.tests': 'Testes',
    'result.questions': 'Perguntas em aberto',
    'result.noFixChange': 'Nenhuma mudança proposta.',
    'result.howToVerify': 'Como verificar',
    'result.newFile': 'Arquivo novo: ',
    'result.runThem': 'Rode você mesmo com: ',
    'result.neverRuns': '. O DevAI nunca roda os testes.',
    'question.files':
      'Enviar {count} arquivo(s) (~{tokens} tokens) para {destination}? Arquivos: {files}.',
    'question.summary':
      'Enviar um resumo do projeto, sem código-fonte (~{tokens} tokens), para {destination}?',
    'question.issue': 'Enviar a issue {issue}{files} (~{tokens} tokens) para {destination}?',
    'question.issueFiles': ' e {count} arquivo(s): {files}',
  },
};

/** The text for `key` in `language`, with {name} placeholders filled. */
export function translate(language, key, values = {}) {
  const text = MESSAGES[language]?.[key] ?? MESSAGES.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ''));
}

/** Every key of every language: the tests check none is missing. */
export function messageKeys(language) {
  return Object.keys(MESSAGES[language] ?? {});
}

export const LanguageContext = createContext('en');

/** t(key, values), the language, and its number locale, for components. */
export function useI18n() {
  const language = useContext(LanguageContext);
  const locale = LOCALES[language] ?? LOCALES.en;
  return {
    language,
    locale,
    t: (key, values) => translate(language, key, values),
    number: (value) => Number(value).toLocaleString(locale),
  };
}

/** The language chosen before in this browser, or the browser's own. */
export function initialLanguage(
  storage = safeStorage(),
  browserLanguage = globalThis.navigator?.language ?? 'en',
) {
  let saved = null;
  try {
    saved = storage?.getItem(STORAGE_KEY);
  } catch {
    saved = null; // a private window may refuse storage
  }
  if (saved in LANGUAGES) return saved;
  return browserLanguage.toLowerCase().startsWith('pt') ? 'pt' : 'en';
}

export function saveLanguage(language, storage = safeStorage()) {
  try {
    storage?.setItem(STORAGE_KEY, language);
  } catch {
    // Not saved: the page still switches, it just won't remember.
  }
}

function safeStorage() {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

/**
 * The consent question in Portuguese, from the preview's facts. In English,
 * the page shows the server's own question, word for word as in the terminal.
 */
export function consentQuestion(t, number, preview) {
  const context = preview.context ?? {};
  const files = sentFiles(preview.task, context);
  const values = { tokens: number(preview.tokens), destination: preview.destination };
  if (preview.task === 'issue' && context.issue) {
    const issue = `${context.issue.repo}#${context.issue.number}`;
    const extra = files.length
      ? t('question.issueFiles', { count: files.length, files: files.join(', ') })
      : '';
    return t('question.issue', { ...values, issue, files: extra });
  }
  if (files.length === 0) return t('question.summary', values);
  return t('question.files', { ...values, count: files.length, files: files.join(', ') });
}

/** The project files a task's context sends, by the shape of that context. */
export function sentFiles(task, context) {
  switch (task) {
    case 'review':
    case 'pull':
      return (context.diffs ?? []).map((diff) => diff.path);
    case 'docs':
      return context.file ? [context.file.path] : [];
    case 'readme':
      return context.readme?.exists ? [context.readme.path] : [];
    case 'fix':
    case 'issue':
      return (context.files ?? []).map((file) => file.path);
    case 'tests':
      return [context.source?.path, ...(context.existing_tests ?? []).map((test) => test.path)].filter(
        Boolean,
      );
    default:
      return [];
  }
}
