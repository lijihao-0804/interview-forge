({graph, sample, source, statements}) => {
    const stage = document.querySelector(".dk-stage");
    const next = [...document.querySelectorAll(".dk-btn")].find(b=>b.textContent.includes("下一步"));
    const steps = graph ? graph.frames.length : sample.steps.length + 2;
    const issues = [], history = [];
    const check = (ok, text, index) => { if (!ok) issues.push("step " + (index+1) + ": " + text); };
    const same = (a,b) => JSON.stringify(a) === JSON.stringify(b);
    const read = sel => stage.querySelector(sel)?.textContent;
    function localMatches(el, value) {
        if (!el) return false;
        if (value && Array.isArray(value.$set)) {
            return el.textContent === "{" + value.$set.map(v=>JSON.stringify(v)).join(", ") +
                (value.$size > value.$set.length ? ", …" : "") + "}";
        }
        if (Array.isArray(value)) {
            if (!value.length) return el.textContent === "[]";
            if (value.every(Array.isArray)) {
                return same([...el.querySelectorAll(":scope > table > tr, :scope > table > tbody > tr")].map(
                    r=>[...r.cells].map(c=>JSON.parse(c.textContent))), value);
            }
            return same([...el.querySelectorAll(":scope > ol > li > span")].map(n=>JSON.parse(n.textContent)),value);
        }
        if (value && typeof value==="object" && Object.keys(value).length) {
            return variables(el.querySelector(":scope > dl"), value);
        }
        return el.textContent === JSON.stringify(value);
    }
    function variables(dl, expected) {
        if (!dl) return false;
        const names = [...dl.querySelectorAll(":scope > dt")];
        return names.length === Object.keys(expected).length && names.every(dt => {
            const key = dt.firstChild?.textContent ?? "";
            return Object.hasOwn(expected,key) && localMatches(dt.nextElementSibling, expected[key]);
        });
    }
    for (let i=0; i<steps; i++) {
        const title = read(".dk-head");
        const desc = document.querySelector(".dk-desc").textContent;
        const why = desc.replace(/^\d+\.\s*/, "");
        check(!!why && desc.startsWith((i+1)+". "), "missing step narration", i);
        check(document.querySelector(".dk-progress + .dk-progress").textContent === (i+1)+" / "+steps, "wrong progress", i);
        check(document.documentElement.scrollWidth <= innerWidth+2, "horizontal page overflow", i);
        let item = {step:i+1, title, explanation:why};
        if (graph) {
            const ref = graph.frames[i];
            const cells = [...stage.querySelectorAll(".dk-cells > .dk-cell")].map(n=>n.textContent);
            const code = read("pre");
            check(title===ref.label && why===ref.why && read(".dk-log")===ref.state &&
                same(cells,ref.cells.map(String)), "graph or narration differs from authored step", i);
            const compactIndent = row => row.replace(/^\s*(\d+)\s+/, "$1 ");
            check(!!code && Array.isArray(ref.code) && same(code.split("\n").map(compactIndent),
                ref.code.map(compactIndent)), "no matching Python code", i);
            if (code) for (const row of code.split("\n")) {
                const parsed = row.match(/^\s*(\d+)\s+(.+)$/);
                check(parsed && source[Number(parsed[1])-1]?.trim() === parsed[2].trim(), "code differs from published solution", i);
            }
            Object.assign(item, {cells, state:read(".dk-log"), code});
        } else if (i>0 && i<steps-1) {
            const [position,line,method,locals,returning] = sample.steps[i-1];
            const sourceLine = source[line-1].trim();
            check(title===method+" · 第 "+line+" 行" && read("pre")===sourceLine,
                "line or method differs from executed Python", i);
            const statement = statements[line];
            check((stage.querySelectorAll("pre")[1]?.textContent ?? null) === (statement ?? null),
                "full Python statement differs from source", i);
            check(variables(stage.querySelector(".dk-trace-vars"),locals), "variable drawing differs from execution", i);
            check(read(".dk-note")?.includes(position+" / "+sample.count), "wrong execution position", i);
            check(why.includes(method) || why.includes(sourceLine.replace(/^(if|elif|while|for|return)\s*/,"").replace(/:$/,"")),
                "narration fails to identify operation", i);
            Object.assign(item,{position,line,method,code:statement || sourceLine,returning});
        } else if (i===0) {
            check(read("pre")===sample.input,"input differs",i);
        }
        history.push(item);
        check(next.disabled === (i===steps-1), "next button state", i);
        if (i<steps-1) next.click();
    }
    return {steps, history, actual:graph ? history.at(-1).state : JSON.parse(read("pre")), issues};
}
