
async function loadWilayas() {
  const res = await fetch('/api/wilayas');
  return await res.json();
}
async function onWilayaChange() {
  // Daira list is admin-managed; if empty, keep free text
  const wilaya = document.getElementById('wilaya').value;
  const res = await fetch('/api/dairas?wilaya=' + encodeURIComponent(wilaya));
  const data = await res.json();
  const select = document.getElementById('daira_select');
  const input = document.getElementById('daira_text');
  if (data && data.length) {
    select.innerHTML = data.map(d => `<option value="${d}">${d}</option>`).join('');
    select.style.display = 'block';
    input.style.display = 'none';
  } else {
    select.style.display = 'none';
    input.style.display = 'block';
  }
}
