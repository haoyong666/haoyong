import requests
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

# 从 GitHub Secrets 读取敏感信息
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
SEND_EMAIL = os.environ["SEND_EMAIL"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
RECEIVE_EMAIL = os.environ["RECEIVE_EMAIL"]

# 搜索关键词（包含股票简称和代码，提高命中率）
stock_queries = [
    "美畅股份 OR 300861",
    "中密控股 OR 300470",
    "正丹股份 OR 300641",
    "华宇软件 OR 300271",
    "大秦铁路 OR 601006",
    "海螺水泥 OR 600585",
    "港迪技术 OR 港迪股份 OR 301079"
]

def fetch_news(query, count=5):
    """从 Bing News 抓取最新新闻"""
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
        print(f"抓取 {query} 失败: {e}")
        return []

def call_deepseek(all_news):
    """调用 DeepSeek 整理简报"""
    # 拼接新闻文本
    news_text = ""
    for stock, articles in all_news.items():
        news_text += f"\n## {stock}\n"
        if not articles:
            news_text += "暂无相关新闻\n"
        else:
            for a in articles:
                news_text += f"- [{a['title']}]({a['link']}) ({a['published']})\n  摘要: {a['summary']}\n"

    prompt =  f"""你是专业的股市情报分析助手，当前日期时间是 {datetime.now().strftime('%Y-%m-%d %H:%M')}（北京时间）。
请根据以下今日最新资讯（新闻发布时间均为今天或昨天），生成一份邮件简报。要求：

1. 按股票分类，筛选出可能影响股价走势的关键消息（利好、利空、中性）。
2. 每条消息用一句话概括，并说明可能的影响性质，**必须保留原文中的链接**，并且**必须保留原文中给出的发布时间**（不要自己编造时间）。
3. 如果某只股票今日无重要消息，直接写“今日暂无重大影响消息”。
4. 简报生成时间必须写当前真实时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}（北京时间），**禁止使用任何其他日期**。
5. 文末加上“本报告由AI生成，仅供参考，不构成投资建议。”的风险提示。
6. **严格禁止**使用你内部知识库中的任何旧新闻，只能基于下面提供的今日新闻整理。

{news_text}

请直接输出整理后的纯文本邮件内容，不要用代码块包裹。"""

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 2500
    }
    try:
        resp = requests.post("https://api.deepseek.com/v1/chat/completions",
                             headers=headers, json=data, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"DeepSeek 调用失败: {e}")
        return "AI总结失败，请稍后重试。"

def send_email(content):
    now = datetime.now()
    hour = now.hour
    if hour < 11:
        period = "早间"
    elif hour < 16:
        period = "午间"
    else:
        period = "晚间"
    subject = f"📈 股票影响情报 {period}简报 - {now.strftime('%Y-%m-%d %H:%M')}"
    
    msg = MIMEMultipart("alternative")
    msg["From"] = SEND_EMAIL
    msg["To"] = RECEIVE_EMAIL
    msg["Subject"] = subject
    
    html = f"""<html><body style="font-family:Microsoft YaHei,sans-serif; font-size:15px; line-height:1.6;">
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
        print("邮件发送成功")
    except Exception as e:
        print(f"邮件发送失败: {e}")

if __name__ == "__main__":
    print(f"[{datetime.now()}] 开始采集新闻...")
    all_news = {}
    for q in stock_queries:
        name = q.split(" OR ")[0]
        all_news[name] = fetch_news(q, count=5)
    
    report = call_deepseek(all_news)
    print("AI简报生成完毕，准备发送...")
    send_email(report)
    print("任务结束。")
