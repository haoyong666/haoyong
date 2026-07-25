import requests
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

# ===== 配置（复用 GitHub Secrets）=====
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
SEND_EMAIL = os.environ["SEND_EMAIL"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
RECEIVE_EMAIL = os.environ["RECEIVE_EMAIL"]

# ===== 1. 新闻采集：多关键词提高权威机构命中率 =====
domestic_queries = [
    "央行 货币政策 OR 人民银行 降准降息",
    "国家统计局 CPI PPI GDP",
    "财政部 专项债 减税降费",
    "新华社 经济 权威发布",
    "国务院 常务会议 经济",
    "发改委 重大项目 投资",
    "商务部 外贸 消费",
]

global_queries = [
    "美联储 利率决议 OR FOMC",
    "欧洲央行 利率 OR ECB",
    "世界银行 全球经济展望",
    "IMF 世界经济展望",
    "路透社 全球经济 OR Reuters economy",
    "彭博社 经济 OR Bloomberg economy",
    "地缘政治 原油 供应链",
    "美国 非农就业 通胀 CPI",
    "日本央行 货币政策",
    "WTO 贸易 全球",
]

def fetch_bing_news(query, count=8):
    url = f"https://www.bing.com/news/search?q={requests.utils.quote(query)}&format=rss&cc=cn&setmkt=zh-CN"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        feed = feedparser.parse(r.text)
        articles = []
        for entry in feed.entries[:count]:
            articles.append({
                "title": entry.title,
                "link": entry.link,
                "published": entry.get("published", ""),
                "summary": entry.get("summary", "").replace('<div','').replace('</div>','').strip()
            })
        return articles
    except Exception as e:
        print(f"抓取失败: {e}")
        return []

# ===== 2. 组装所有候选新闻 =====
all_domestic = []
for q in domestic_queries:
    all_domestic.extend(fetch_bing_news(q, count=6))

all_global = []
for q in global_queries:
    all_global.extend(fetch_bing_news(q, count=6))

# 去重（简单按链接去重）
def deduplicate(articles):
    seen = set()
    unique = []
    for a in articles:
        if a['link'] not in seen:
            seen.add(a['link'])
            unique.append(a)
    return unique

all_domestic = deduplicate(all_domestic)
all_global = deduplicate(all_global)

# ===== 3. 调用 DeepSeek 精选并分析投资机会 =====
def generate_economic_report(domestic, global_):
    domestic_text = ""
    for i, a in enumerate(domestic):
        domestic_text += f"{i+1}. [{a['title']}]({a['link']}) ({a['published']})\n   {a['summary']}\n"

    global_text = ""
    for i, a in enumerate(global_):
        global_text += f"{i+1}. [{a['title']}]({a['link']}) ({a['published']})\n   {a['summary']}\n"

    prompt = f"""你是路透社资深财经主编，请根据下面提供的今日新闻列表，整理一份高质量的经济简报，发送给投资者。

要求：
1. 从国内新闻中，精选出 **15条** 真正来自权威机构（央行、统计局、财政部、新华社、国务院、发改委、商务部等）发布、且对宏观经济或市场有明显影响的消息。按重要性排序。
2. 从国际新闻中，精选出 **20条** 来自全球权威机构（美联储、欧央行、世界银行、IMF、路透、彭博、主要经济体官方数据等）的重要消息，按重要性排序。
3. 每条消息用一句中文概括核心内容，并保留原文链接（Markdown格式）。
4. 在简报末尾，增加一个「📈 股市投资机会」板块，结合上述国内外重大新闻，分析可能受益的板块、风险点，并给出2-3个具体的投资方向（A股、港股、美股相关均可）。
5. 开头注明简报生成时间。
6. 如果某类新闻数量不足（如国内不足15条或国际不足20条），请用你已知的今日重要经济数据/事件补充，但需注明“补充”。
7. 文末加上风险提示。

=== 国内候选新闻（共{len(domestic)}条）===
{domestic_text if domestic_text else "暂无数据"}

=== 国际候选新闻（共{len(global_)}条）===
{global_text if global_text else "暂无数据"}

请直接输出整理后的纯文本邮件内容，不要用代码块包裹。"""

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 3500
    }
    try:
        resp = requests.post("https://api.deepseek.com/v1/chat/completions",
                             headers=headers, json=data, timeout=90)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"DeepSeek 调用失败: {e}")
        return "AI总结生成失败，请稍后重试。"

# ===== 4. 发送邮件 =====
def send_report(content):
    now = datetime.now()
    hour = now.hour
    period = "早间" if hour < 14 else "晚间"
    subject = f"🌐 权威经济新闻 {period}简报 - {now.strftime('%Y-%m-%d %H:%M')}"

    msg = MIMEMultipart("alternative")
    msg["From"] = SEND_EMAIL
    msg["To"] = RECEIVE_EMAIL
    msg["Subject"] = subject

    html = f"""<html><body style="font-family:Microsoft YaHei,sans-serif; font-size:15px; line-height:1.7;">
{content.replace(chr(10), '<br>')}
<br><hr>
<p style="color:gray; font-size:12px;">本邮件由AI自动生成，仅供参考，不构成投资建议。</p >
</body></html>"""
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(SEND_EMAIL, EMAIL_PASSWORD)
        server.sendmail(SEND_EMAIL, [RECEIVE_EMAIL], msg.as_string())
        server.quit()
        print("经济新闻邮件发送成功")
    except Exception as e:
        print(f"邮件发送失败: {e}")

# ===== 主流程 =====
if __name__ == "__main__":
    print(f"[{datetime.now()}] 开始采集经济新闻...")
    report = generate_economic_report(all_domestic, all_global)
    print("简报生成完毕，发送中...")
    send_report(report)
    print("任务结束。")
