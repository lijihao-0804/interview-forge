"""Boundary fixtures for professional eligibility, distinct from student status."""
from build_topic import professional,years,normalize,track,adapt_soe_record
import json
from pathlib import Path
cases=[
 ('通信工程、计算机等相关专业','A'),
 ('本科及以上，专业：通信，电子等','B'),
 ('熟悉无线通信系统物理层技术，在6G相关专业领域有深入研究','D'),
 ('硕士毕业工作5年以上，材料，力学，通信，光电等相关专业领域','B'),
 ('计算机专业；熟悉通信协议和C++开发','D'),
 ('计算机、软件相关专业，熟悉通信协议','D'),
 ('信息与通信工程专业，硕士以上','B'),
 ('信息通信工程专业','B'),
 ('电子信息类相关专业，本科以上','C'),
 ('电子信息工程专业','D'),
 ('不接受通信工程专业','D'),
 ('Bachelors degree in Telecommunication Engineering','A'),
 ('通信工程师，具备专业能力','D'),
 ('专业：软件工程，熟悉通信工程经验','D'),
 ('专业：软件工程，具备通信专业知识','D'),
 ('专业要求：熟悉计算机或通信工程专业及相关知识','D'),
 ('专业要求：经济学、统计学等专业，具备通信行业营销经验者专业可适当放宽','D'),
 ('专业要求：通信相关或计算机相关专业','B'),
]
for text,expected in cases:
    actual,_=professional(text)
    assert actual==expected,(text,actual,expected)
assert years({},'至少3年以上相关研发经验')
assert years({'experience':'两年以上工作经验'},'')
assert not years({},'熟悉5G通信技术')
for text,expected in [('通信协议经验','D'),('熟悉通信系统','D'),('通信专业知识','D'),('通信专业经验','D'),('通信工程师','D'),('Telecommunications Engineering experience','D'),('通信工程','A'),('通信类','B')]:
    actual,_=professional(text,structured=True);assert actual==expected,(text,actual,expected)
fixture={'id':'fixture','source_job_id':'1','company':'fixture','title':'通信研发','major_evidence_scope':'job_specific','row_kind':'full_jd','requirements':'本科通信工程专业','full_text':'本科通信工程专业','description':'研发职责'}
for status,expected in [('社招，未明确是否应届',False),('校招入口已确认，届别未确认',True),('校招应届生（未明确毕业年份）',True),('未确认学生可投',False)]:
    actual=normalize({**fixture,'student_status':status},'fixture','A',['本科通信工程专业']);assert actual['student_confirmed']==expected,(status,actual['student_confirmed'])
assert not normalize({**fixture,'student_confirmed':'false'},'fixture','A',['本科通信工程专业'])['student_confirmed']
assert not normalize({**fixture,'row_kind':'unrecognized'},'fixture','A',['本科通信工程专业'])['skill_eligible']
assert not normalize({**fixture,'major_evidence_scope':''},'fixture','A',['本科通信工程专业'])['skill_eligible']
assert not normalize({**fixture,'row_kind':'batch_shared'},'fixture','A',['本科通信工程专业'])['skill_eligible']
for title,expected in [('射频算法工程师','射频、天线与电磁'),('通信算法工程师','通信算法与基带'),('云平台AI算法工程师','AI、数据与算法'),('网络解决方案工程师','解决方案、技术服务与交付'),('网络安全工程师','网络与信息安全'),('嵌入式软件工程师','嵌入式与终端硬件'),('后端软件开发','软件与系统开发'),('人力资源运营支撑','综合支撑与管理')]:assert track(title)==expected,(title,track(title),expected)
for title,expected in [('信号处理工程师','通信算法与基带'),('设计研发工程师','综合研发（阅读具体方向）')]:assert track(title)==expected
for degree,expected in [('硕士','D'),('本科及以上','C')]:assert normalize({**fixture,'degree_raw':degree,'requirements':'电子信息类等相关专业'},'fixture','C',['电子信息类等相关专业'])['tier']==expected
for raw,expected in [('公告介绍研发基地在武汉、北京；未按该岗位列明城市',['地点未明确']),('深圳市南山区（公司另有南京分公司；本条表列深圳）',['深圳']),('江苏省（公告未逐岗列明城市；用人单位为南京公司）',['江苏省（城市未明确）'])]:assert adapt_soe_record({'company':'fixture','city':raw})['city_tags']==expected
print(f'{len(cases)+8} major boundary, 3 experience, 8 eligibility/schema, 10 career, 2 degree catalog and 3 city fixtures passed')
root=Path(__file__).resolve().parents[1];(root/'evidence').mkdir(exist_ok=True);(root/'evidence/rule_verification.json').write_text(json.dumps({'passed':True,'professional_fixtures':len(cases)+8,'experience_fixtures':3,'student_schema_fixtures':8,'career_fixtures':10,'degree_catalog_fixtures':2,'city_fixtures':3,'total_checks':len(cases)+34}),encoding='utf-8')
