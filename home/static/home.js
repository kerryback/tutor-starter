// Shared by the pages of tutors.example.edu.
const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const next = params.get('next') || '';

// The current ?next=, to carry from page to page.
function withNext(path) {
  if (!next) return path;
  return path + (path.includes('?') ? '&' : '?') + 'next=' + encodeURIComponent(next);
}

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} :
    {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  let data = {};
  try { data = await r.json(); } catch {}
  if (!r.ok) {
    const d = data.detail;
    throw new Error(typeof d === 'string' ? d : 'Something went wrong. Try again.');
  }
  return data;
}

// Run a form's submit handler with its button disabled and errors shown in msgId.
function onSubmit(formId, msgId, fn) {
  $(formId).addEventListener('submit', async e => {
    e.preventDefault();
    const btn = $(formId).querySelector('button[type=submit]');
    btn.disabled = true; $(msgId).textContent = ''; $(msgId).classList.remove('ok');
    try { await fn(); } catch (err) { $(msgId).textContent = err.message; }
    finally { btn.disabled = false; }
  });
}

function showOk(msgId, text) { $(msgId).textContent = text; $(msgId).classList.add('ok'); }
