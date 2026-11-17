async (page) => {
  const org = 'zte';
  const siteId = '46903';
  const base = `https://app.mokahr.com/campus-recruitment/${org}/${siteId}`;
  const output = [];
  for (const pageNum of [1, 2]) {
    await page.goto((pageNum === 1 ? `${base}#/jobs?project=100022014` : `${base}#/jobs?project=100022014&page=2`), { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForFunction(() => Array.from(document.querySelectorAll('a[href^="#/job/"]')).some(a => a.innerText.includes('发布于')), null, { timeout: 25000 });
    const jobs = await page.locator('a[href^="#/job/"]').evaluateAll((els) => els.filter((a) => a.innerText.includes('发布于')).map((a) => {
      const listText = a.innerText.trim();
      const lines = listText.split(/\n+/).map(x => x.trim()).filter(Boolean);
      const title = lines.find(x => x !== '急' && !x.includes('发布于') && !/^(本科|硕士|博士)$/.test(x)) || '';
      const posted = (listText.match(/发布于\s*(\d{4}-\d{2}-\d{2})/) || [])[1] || null;
      return { title, posted_date: posted, list_text: listText, href: a.getAttribute('href') };
    }));
    for (const job of jobs) {
      const jobId = (job.href.match(/#\/job\/([^?]+)/) || [])[1] || '';
      const detailUrl = `${base}${job.href}`;
      await page.goto(detailUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForFunction((arg) => window.location.hash.includes(arg.jobId) && document.body.innerText.includes('职位描述') && document.body.innerText.includes(arg.title), { jobId, title: job.title }, { timeout: 25000 });
      const visibleText = await page.locator('body').innerText();
      if (/安全验证|人机验证|请完成验证|验证码/.test(visibleText)) throw new Error(`Possible verification gate encountered at ${detailUrl}`);
      output.push({ org, siteId, source_job_id: jobId, title: job.title, posted_date: job.posted_date, list_text: job.list_text, detail_url: page.url(), visible_text: visibleText });
    }
  }
  await page.evaluate((value) => localStorage.setItem('__campus_bulk_zte_details__', value), JSON.stringify(output));
  return { company: org, job_count_captured: output.length, distinct_ids: new Set(output.map(x => x.source_job_id)).size, first_titles: output.slice(0, 3).map(x => x.title), last_titles: output.slice(-3).map(x => x.title), storage: '__campus_bulk_zte_details__' };
}

