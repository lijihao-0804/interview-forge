"""Public exam shelf links, including the two tracked library modules."""

from html import escape


EXAM_GROUPS = (
    ("按公司准备", (
        ("企业高频算法题库", "../company-topics/index.html", "查看目标公司的高频算法题与考察热度。", "company-topics"),
        ("企业高频题解", "../../books/company-solutions/index.html", "按公司阅读解题思路与参考代码。", ""),
        ("AI 岗笔试真题导航", "../ai-exam-index/index.html", "按公司、日期和岗位查找 2026 年笔试原题来源。", "ai-exam-index"),
    )),
    ("练机试编程", (
        ("AI 岗机试真题库", "../../books/ai-exam/index.html", "练习 AI 岗机试、Agent 手撕与企业 ACM 编程题。", ""),
        ("华为 OD 机试题库", "../../books/huawei-od/index.html", "按分值和题目名称查找华为 OD 机试题。", ""),
        ("企业机考真题", "../../books/company-oj/index.html", "按公司阅读机考原题、输入输出格式与样例。", ""),
        ("ACM 在线练习", "../../books/ai-exam/acm-playground.html", "选择输入模板，运行 Python 或 Java 代码并对比输出。", ""),
    )),
    ("做选择题", (
        ("AI 岗笔试选择题", "../../pages/quiz.html?bank=ai-exam", "按考点答题，查看判分与解析。", ""),
        ("AI 术语选择题", "../../pages/quiz.html", "练习大模型与 Agent 术语。", ""),
    )),
)

TRACKED_MODULES = {module_id for _, rows in EXAM_GROUPS for _, _, _, module_id in rows if module_id}
EXAM_SEARCH_MODULES = "company-topics ai-exam-index huawei-od company-solutions company-oj ai-exam"


def exam_hub_body(topbar: str) -> str:
    groups = []
    for title, rows in EXAM_GROUPS:
        links = []
        for name, href, description, module_id in rows:
            status = f'<small data-exam-progress="{module_id}" hidden></small>' if module_id else ""
            links.append(
                f'<li><a href="{escape(href)}"><strong>{escape(name)}</strong>'
                f'<span>{escape(description)}</span>{status}</a></li>'
            )
        groups.append(f'<section><h2>{escape(title)}</h2><ul>{"".join(links)}</ul></section>')
    return (
        f'<div class="shell">{topbar}<main class="exam-hub"><header><h1>企业笔试与机试</h1>'
        '<p>查找目标公司的考题，或直接开始编程和选择题练习。</p></header>'
        f'<div class="exam-groups">{"".join(groups)}</div></main></div>'
    )


EXAM_HEAD = """<style>
.exam-hub{max-width:1080px;margin:40px auto}
.exam-hub h1{font-size:clamp(1.75rem,4vw,2.6rem);line-height:1.2;margin:0}
.exam-hub header p,.exam-groups a span{color:var(--muted)}
.exam-groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,255px),1fr));gap:20px;margin-top:32px;align-items:start}
.exam-groups section{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
.exam-groups h2{font-size:1.1rem;margin:0 0 6px}
.exam-groups ul{list-style:none;padding:0;margin:0}
.exam-groups li+li{border-top:1px solid var(--line)}
.exam-groups a{display:grid;padding:12px 4px;gap:2px}
.exam-groups a span,.exam-groups small{font-size:.88rem}
.exam-groups small{color:var(--success)}
@media(max-width:600px){.exam-hub{margin:24px auto}.exam-groups{gap:12px;margin-top:20px}}
</style>"""


EXAM_PROGRESS = """<script>
(async function(){
  const auth=window.InterviewForgeGuestAuth;
  if(!auth || (await auth.ready()).status!=='authenticated')return;
  async function load(path){
    const response=await auth.request(path,{cache:'no-store'});
    if(response.ok)return response.json();
  }
  const [library,daily]=await Promise.all([
    load('/api/library').catch(()=>null),load('/api/daily').catch(()=>null)
  ]);
  if(!auth.isAuthenticated())return;
  for(const label of document.querySelectorAll('[data-exam-progress]')){
    const id=label.dataset.examProgress;
    const progress=library?.modules?.[id], due=daily?.summary?.modules?.[id];
    const parts=[];
    if(progress)parts.push('已完成 '+progress.completed+' / '+progress.total+' 章');
    if(due?.due)parts.push('待复习 '+due.due+' 章');
    label.textContent=parts.join(' · ');
    label.hidden=!parts.length;
  }
})().catch(()=>{});
</script>"""
