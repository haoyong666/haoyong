import requests
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import os
import re

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
SEND_EMAIL = os.environ["SEND_EMAIL"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
RECEIVE_EMAIL = os.environ["RECEIVE_EMAIL"]

# 更精准的财经/政治关键词（针对中文新闻源）
QUERIES = [
    "今日 经济 政策 利好 A股",
    "证监会 股市 行情 利好",
    "央行 降准 降息 宏观",
    "中国 政治 经济 新闻 今天",
    "全球 市场 美联储 影响 A股",
    "产业 升级 新能源 半导体 基建",
    "贸易 协议 国际 关系 中国",
]

def fetch_news(query, count=8):
    """抓取Bing新闻，放宽时效性至3天，并保留所有近期新闻"""
    url = f"https://www.bing.com/news/search?q={requests.utils.quote(query)}&format=rss&cc=cn&setmkt=zh-CN&sortby=date"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        feed = feedparser.parse(r.text)
        if not feed.entries:
            return []
        # 取最近3天的日期字符串
        dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(3)]
        articles = []
        for entry in feed.entries[:count*2]:
            pub = entry.get("published", "")
            # 只要包含最近3天日期 或 包含“小时前”“分钟前”等，就保留
            if any(d in pub for d in dates) or any(kw in pub for kw in ["小时前", "分钟前", "刚刚"]):
                articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "published": pub,
                    "summary": entry.get("summary", "").replace('<div','').replace('</div>','').strip()
                })
        # 如果过滤后一篇都没有，则直接取前5篇作为兜底（不管日期）
        if not articles:
            for entry in feed.entries[:count]:
                articles.append({
                    "title": entry.title,
                    "link": entry.link,
                    "published": entry.get("published", ""),
                    "summary": entry.get("summary", "").replace('<div','').replace('</div>','').strip()
                })
        return articles[:count]
    except Exception as e:
        print(f"抓取失败: {e}")
        return []

# 采集所有新闻并去重
all_news = []
for q in QUERIES:
    all_news.extend(fetch_news(q, count=6))

seen = set()
unique_news = []
for n in all_news:
    if n["link"] not in seen:
        seen.add(n["link"])
        unique_news.append(n)

# 最多保留60条给AI筛选
unique_news = unique_news[:60]

def generate_report(articles):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    if not articles:
        return "今日暂无相关宏观新闻。", 0
    news_text = ""
    for i, a in enumerate(articles):
        news_text += f"{i+1}. [{a['title']}]({a['link']}) ({a['published']})\n  摘要: {a['summary']}\n"

    prompt = f"""当前北京时间：{now_str}。下面是今日可能影响国内股市的宏观新闻候选（共{len(articles)}条），请严格按以下要求生成邮件简报：
1. 挑选与“经济、政治、政策、利于国内股市向好发展”最相关的新闻，最多15条（不足15条就发实际数量）。
2. 每条新闻用一句话总结核心要点，**严格不超过50字**，并保留原文链接。
3. 开头写：“以下为今日宏观利好新闻，共X条”，并注明生成时间：{now_str}。
4. 如果实在没有相关新闻，请回复“今日暂无相关宏观新闻”。
5. 禁止使用内部旧知识，只从下面候选里挑选。

{news_text[:4000]}"""

    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2000
    }
    try:
        resp = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=data, timeout=90)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        count = len(re.findall(r'^\d+\.', content, re.MULTILINE))
        return content, min(count, 15)
    except Exception as e:
        print(f"DeepSeek 错误: {e}")
        return f"AI总结失败，请检查API余额或网络。", 0

def send_email(content, count):
    now = datetime.now()
    period = "早间" if now.hour < 11 else ("午间" if now.hour < 16 else "晚间")
    subject = f"📰 宏观利好 {period}简报（{count}条） - {now.strftime('%m-%d %H:%M')}"
    msg = MIMEMultipart("alternative")
    msg["From"] = SEND_EMAIL
    msg["To"] = RECEIVE_EMAIL
    msg["Subject"] = subject
    html = f"""<html><body style="font-family:Microsoft YaHei; font-size:15px;">
{content.replace(chr(10), '<br>')}
<br><hr>
<p style="color:gray; font-size:12px;">本邮件由AI自动生成，仅供参考。</p >
</body></html>"""
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(SEND_EMAIL, EMAIL_PASSWORD)
        server.sendmail(SEND_EMAIL, [RECEIVE_EMAIL], msg.as_string())
        server.quit()
        print("邮件发送成功")
    except Exception as e:
        print(f"邮件发送失败: {e}")

if __name__ == "__main__":
    print(f"[{datetime.now()}] 开始采集...")
    report, count = generate_report(unique_news)
    print(f"简报生成完毕，共{count}条，发送中...")
    send_email(report, count)
    print("结束。")
