"""A separate, still-blinded reserve set frozen after the first baseline and before candidate results."""
from pathlib import Path
import hashlib
import json

from freeze import encoded, make_fixture


HERE=Path(__file__).resolve().parent

LONG_PREFACE = (
    "我把那天在楼里走的路线补全一下，免得下次混在一起。上午先去地下一层交回借来的装订器，"
    "再上楼问灯泡什么时候换。门边有两副折好的架子，走廊靠里的那一个才是可以搬走的。"
    "中午收拾桌面的时候发现夹子少了一只，写一张小纸条给管理员就行。下午茶点临时改在楼下，"
    "有人问过窗台上的东西能不能挪开，当时我的答复是等清洁的人到场。周末访客如果问路，"
    "门房会先请他们到旁边登记，然后由值日的同事领上来。我也和负责借钥匙的人确认过，"
    "落下的雨伞可以原地放两天，不用专程跑回来拿。楼里那场分享只有一小时，中间不会休息，"
    "答疑集中到散场以后处理。大门的标志还没换，入口照片可以等下一轮维护时补拍。"
    "至于和小组一起听讲的人，我后来查了周报才发现有人把不同周次的安排抄在了一张表里。"
    "为了把几件事说清，我把真正影响自己下次出门的决定单独写成最后一句。"
)

ROWS = [
    ("h01","author_vs_neighbor",177,
     "邻居先讲了他的做法，我也说了自己在半夜突然清醒时会怎么办。",
     "夜半失眠时，我只把深褐色沙漏倒扣在枕边。",
     "之前提过睡到半夜又睁眼时怎么办。请只抄我自己的做法那句，给出消息编号。",
     "半夜睁眼后自己会做的事", ["半夜","失眠","自己"],
     395, "邻居说起睡到半夜又睁眼时怎么办，我照抄了他的话：“我拿床头的漫画书看两页。”那是他自己的习惯。"),
    ("h02","quoted_first_person",461,
     "这是写作课的课堂记录。老师没请我们举自己的例子，只要求从受访者的口述里摘一句。采访对象是集邮的小周，下面一整句里的“我”指他。",
     "邮票边齿受了潮，我就用杏黄色的信封暂时分装。",
     "之前做采访时，我记下那位玩票花的朋友讲东西沾湿以后怎么收。能原样抄出他说的那句，连同消息编号给我吗？",
     "采访玩票花的朋友收藏沾湿以后怎么收",["采访","集邮","邮票"],
     847, "玩票花的朋友提到东西沾湿以后怎么收，我没记下他的解释，只写了自己的猜测：“我会把卡片摊在窗台上。”"),
    ("h03","long_personal_decision",589,
     LONG_PREFACE,
     "集体讲座结束后若公共汽车已经收班，我会到老榆树后面的车棚取折叠车。",
     "之前那条挺长的楼里杂事记录，我真正决定讲完了太迟赶不上末班车要怎么回家，说的是哪一句？请逐字引用并附消息编号。",
     "长记录里讲完太迟赶不上末班车怎么回家",["末班车","收班","公共汽车"],
     693, "讲完了太迟赶不上末班车那天，小梁留在大会堂等朋友，他把这条消息顺手转给了我。"),
    ("h04","two_clause_software",335,
     "读书会聊到了两条常被混为一谈的操作，我当时专门写了一个完整的分号句作提醒。先说的是保留老版本，这和搬运容器的例子关系不大。",
     "代码改坏时我先给当前分支贴上琥珀标签；撤销以后，再从旧快照抄回封面图。",
     "之前说程序改砸了别急着直接倒回去，我当时把事前和事后两件事写成同一句。请把整句和编号给我。",
     "程序改砸了回到上次确定版本前后两件事",["程序","分支","撤销"],
     797, "小邓说程序改砸了就直接倒回去。他事前会叫搭档停下改动，事后去查看构建页，我只是记的会议意见。"),
    ("h05","quoted_exact_overlap",1075,
     "同事向我借调音工具时顺嘴给了一个提醒，我把那句话记在这里。",
     "口琴校音时，我把哑光银色的簧片盒留在左手边。",
     "之前我记过同事关于“口琴校音”的提醒，他原话是什么？只摘提醒那句，附上我记录它的消息编号。",
     "口琴校音",["口琴校音","簧片","提醒"],
     711, "我另外写过口琴校音的个人练习计划，每个试音之间休息半分钟。这不是当时同事的提醒。"),
]


def reserve_fixture():
    base=make_fixture()
    protected={t["message_id"] for c in base["cases"] for t in c["target"]}
    protected.update(pos for c in base["cases"] for pos in c["distractors"])
    cases=[]
    for name,domain,idx,prefix,quote,question,short,terms,decoy,other in ROWS:
        assert idx not in protected and decoy not in protected and idx!=decoy
        protected.update((idx,decoy))
        base["corpus"][idx-1]=["user",prefix+quote]
        base["corpus"][decoy-1]=["user",other]
        cases.append({"case":name,"domain":domain,"kind":"literal" if name=="h05" else "paraphrase",
                      "question":question,"query":short,"literal_terms":terms,"target":[{"message_id":idx,"quote":quote}],
                      "distractors":[decoy]})
    assert len(LONG_PREFACE)>320
    base["cases"]=cases
    base["design"]={**base["design"],"run_order":["h02","h05","h03","h01","h04"],
                    "primary":"Separate reserve only, four paraphrases plus one literal positive. Never pool with the original eight.",
                    "controls":"Do not attribute a neighbour's first-person quotation to the user. Attribute an interviewee's first-person quotation to the interviewee. Include a source sentence beyond character 320 and a two-clause source.",
                    "sealed_after":"Original 13-case baseline; before any candidate output. No reserve case returned to implementation developers for training, prompting or threshold selection."}
    return base


if __name__=="__main__":
    data=reserve_fixture()
    blob=encoded(data)
    manifest={"sha256":hashlib.sha256(blob).hexdigest(),"rows":len(data["corpus"]),"cases":len(data["cases"])}
    for name,content in (("holdout-fixtures.json",blob),("holdout-lock.json",encoded(manifest))):
        path=HERE/name
        if path.exists() and path.read_bytes()!=content:
            raise ValueError("reserved fixture differs")
        path.write_bytes(content)
    print(json.dumps(manifest))
