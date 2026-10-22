const $ = selector => document.querySelector(selector);
let plan = null;
function node(tag, text) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  return element;
}
async function api(path, body, headers = {}) {
  const response = await fetch(path, body ? {method: 'POST', headers: {'Content-Type': 'application/json', ...headers}, body: JSON.stringify(body)} : {});
  const data = await response.json();
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Check task titles, owners and valid calendar dates, then try again.');
  return data;
}
function show(value) {
  plan = value;
  $('#state').textContent = value.state.toUpperCase();
  $('#tasks').replaceChildren();
  for (const task of value.tasks) {
    const article = node('article');
    article.className = 'task'; article.dataset.id = task.id;
    for (const [key, text] of [['title', 'Task title'], ['owner', 'Owner · blank means unknown'], ['due_date', 'Due date · blank means unknown'], ['priority', 'Priority'], ['acceptance', 'Completion criteria']]) {
      const label = node('label', text);
      const field = node(key === 'acceptance' ? 'textarea' : key === 'priority' ? 'select' : 'input');
      if (key === 'priority') for (const option of ['unknown', 'high', 'medium', 'low']) {
        const choice = node('option', option[0].toUpperCase() + option.slice(1)); choice.value = option; field.append(choice);
      }
      if (key === 'due_date') field.type = 'date';
      if (key === 'acceptance') field.placeholder = 'Define what must be true for this task to be complete.';
      field.id = `${task.id}-${key}`; field.dataset.field = key;
      field.value = task[key] || (key === 'priority' ? 'unknown' : '');
      field.maxLength = key === 'title' ? 240 : key === 'owner' ? 60 : key === 'due_date' ? 10 : 600;
      field.disabled = value.state !== 'draft'; label.htmlFor = field.id;
      article.append(label, field);
    }
    const quote = node('blockquote', `Line ${task.source_line}: ${task.source_quote}`);
    quote.className = 'source'; article.append(quote);
    const references = node('div'); references.className = 'refs';
    for (const reference of task.references) {
      const link = node('a', reference.title + ' ↗'); link.href = reference.url;
      link.target = '_blank'; link.rel = 'noopener noreferrer'; references.append(link);
    }
    article.append(references); $('#tasks').append(article);
  }
  $('#actions').hidden = false;
  $('#approve').hidden = $('#reject').hidden = value.state !== 'draft';
  $('#publish').hidden = value.state !== 'approved';
  $('#publish-jira').hidden = !['approved', 'published'].includes(value.state);
  $('#history').replaceChildren();
  for (const event of value.events) $('#history').append(node('li', `${event.action.replaceAll('_', ' ')} · ${event.details}`));
  $('#issues').replaceChildren();
  for (const issue of value.jira_exports || []) {
    const line = node('p', `Jira ${issue.state}: ${issue.issue_key || issue.marker}`);
    if (issue.issue_url) { const link = node('a', 'Open issue ↗'); link.href = issue.issue_url; link.target = '_blank'; link.rel = 'noopener noreferrer'; line.append(link); }
    $('#issues').append(line);
  }
  for (const issue of value.issues) {
    const card = node('div', `LOCAL-${issue.id} · ${issue.title} · ${issue.owner || 'Unassigned'} · ${issue.priority || 'unknown'} priority`);
    card.className = 'issue'; $('#issues').append(card);
  }
}
async function busy(operation) {
  const buttons = [...document.querySelectorAll('button')];
  buttons.forEach(button => button.disabled = true);
  try { await operation(); }
  catch (error) { $('#status').textContent = error.message; }
  finally { buttons.forEach(button => button.disabled = false); }
}
$('#sample').onclick = () => busy(async () => {
  $('#transcript').value = (await api('/api/sample')).transcript;
  $('#status').textContent = 'Example loaded. Find its explicit commitments.';
});
$('#extract').onclick = () => busy(async () => {
  const value = await api('/api/plans', {transcript: $('#transcript').value, engine: $('#engine').value}); show(value);
  $('#status').textContent = `${value.tasks.length} actions found. Check titles, owners, dates, priorities and completion criteria.`;
});
function edited() {
  return [...document.querySelectorAll('.task')].map(article => {
    const task = {id: article.dataset.id};
    for (const field of article.querySelectorAll('[data-field]')) task[field.dataset.field] = field.value;
    return task;
  });
}
for (const [id, decision] of [['approve', 'approve'], ['reject', 'reject']]) $(`#${id}`).onclick = () => busy(async () => {
  show(await api(`/api/plans/${plan.id}/review`, {version: plan.version, decision, tasks: edited()}));
  $('#status').textContent = decision === 'approve' ? 'Approved. Create local issues when ready.' : 'Draft rejected. Create a new draft from revised notes.';
});
$('#publish').onclick = () => busy(async () => {
  show(await api(`/api/plans/${plan.id}/publish`, {idempotency_key: `publish-${plan.id}`}));
  $('#status').textContent = 'Local issues created. Repeated requests cannot create duplicates. Nothing sent externally.';
});
$('#download').onclick = () => {
  if (!plan) return;
  const snapshot = plan.state === 'draft' ? {...plan, tasks: edited(), export_note: 'Unsaved browser edits; this draft has not been approved.'} : plan;
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob), link = node('a'); link.href = url;
  link.download = 'sprint-plan.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
};

$('#publish-jira').onclick = () => busy(async () => {
  if (!confirm('Send the approved tasks and source lines to the configured Jira project? This creates external issues.')) return;
  const token = $('#publish-token').value;
  try {
    show(await api(`/api/plans/${plan.id}/publish/jira`, {expected_version: plan.version, confirm_external_write: true}, {'X-Publish-Token': token}));
    $('#status').textContent = 'Jira export complete. Existing recorded issues were reused.';
  } finally { $('#publish-token').value = ''; }
});
