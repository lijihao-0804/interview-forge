/* Visibility is a convenience; the server authorizes every archive resource. */
(() => {
  const entry = document.getElementById('privateArchiveEntry');
  if (!entry) return;
  fetch('/api/private-archive-status', {credentials:'same-origin', cache:'no-store'})
    .then(response => response.ok ? response.json() : null)
    .then(status => {
      if (!status) return;
      entry.hidden = false;
      if (!status.available) entry.title = '档案尚未安装：请配置服务器上的私有附件路径';
    }).catch(() => {});
})();
