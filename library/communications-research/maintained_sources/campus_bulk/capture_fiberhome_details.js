async (page) => {
  const org = 'whfhtx';
  const siteId = '73922';
  const base = `https://app.mokahr.com/campus-recruitment/${org}/${siteId}`;
  const categories = [
    ['芯片研发', 115512], ['软件研发', 113478], ['硬件研发', 107614],
    ['技术支持', 113471], ['产品测试', 107869], ['智能制造', 117730],
    ['职能管理', 115828], ['博士职位', 137193], ['解决方案', 107605]
  ];
  const output = [];
  for (const [category, categoryId] of categories) {
    const listingUrl = `${base}#/jobs?zhineng%5B0%5D=${categoryId}`;
    await page.goto(listingUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForFunction(() => document.body.innerText.includes('结果') && Array.from(document.querySelectorAll('a[href^="#/job/"]')).some(a => a.innerText.includes('发布于')), null, { timeout: 25000 });
    const jobs = await page.locator('a[href^="#/job/"]').evaluateAll((els) => els.filter((a) => a.innerText.includes('发布于')).map((a) => {
      const listText = a.innerText.trim();
      const lines = listText.split(/\n+/).map(x => x.trim()).filter(Boolean);
      const title = lines.find(x => x !== '急' && !x.includes('发布于')) || '';
      const posted = (listText.match(/发布于\s*(\d{4}-\d{2}-\d{2})/) || [])[1] || null;
      return { title, posted_date: posted, list_text: listText, href: a.getAttribute('href') };
    }));
    for (const job of jobs) {
      const jobId = (job.href.match(/#\/job\/([^?]+)/) || [])[1] || '';
      const detailUrl = `${base}${job.href}`;
      await page.goto(detailUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await page.waitForFunction((arg) => window.location.hash.includes(arg.jobId) && document.body.innerText.includes('职位描述') && document.body.innerText.includes(arg.title), { jobId, title: job.title }, { timeout: 25000 });
      const visibleText = await page.locator('body').innerText();
      if (/拖动滑块|滑动验证|人机验证|请完成验证|验证码错误|安全验证/.test(visibleText)) throw new Error(`Possible verification gate encountered at ${detailUrl}`);
      output.push({ org, siteId, category, category_id: categoryId, source_job_id: jobId, title: job.title, posted_date: job.posted_date, list_text: job.list_text, detail_url: page.url(), visible_text: visibleText });
    }
  }
  await page.evaluate((value) => localStorage.setItem('__campus_bulk_fiberhome_details__', value), JSON.stringify(output));
  return { company: org, job_count_captured: output.length, distinct_ids: new Set(output.map(x => x.source_job_id)).size, categories: categories.length, first_titles: output.slice(0, 3).map(x => x.title), last_titles: output.slice(-3).map(x => x.title), storage: '__campus_bulk_fiberhome_details__' };
}
