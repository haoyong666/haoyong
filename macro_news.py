import requests
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]  # 保留，未使用但防止报错
SEND_EMAIL = os.environ["SEND_EMAIL"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
RECEIVE_EMAIL = os.environ["RECEIVE_EMAIL"]

def fetch_bing_news(query, count=15):
    """从 Bing News RSS 获取最新新闻，不做任何时效性过滤"""
    url = f"https://www.bing.com/news/search?q={requests.utils.quote(query)}&format=rss&cc=cn&setmkt=zh-CN&sortby=date"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        feed = feedparser.parse(resp.text)
        if not feed.entries:
            return []
        articles = []
        for entry in feed.entries[:count]:
            articles.append({
                "title": entry.title,
                "link": entry.link,
                "published": entry.get("published", "")
            })
        return articles
    except Exception as e:
        print(f"抓取失败: {e}")
        return []

# 多个宏观关键词确保覆盖面
queries = [
    "宏观 经济 政策",
    "A股 利好 新闻",
    "今日 财经 头条",
    "央行 财政部 最新",
    "国际 经济 形势",
]

all_articles = []
for q in queries:
    all_articles.extend(fetch_bing_news(q, count=5))

# 去重
seen = set()
unique_articles = []
for a in all_articles:
    if a["link"] not in seen:
        seen.add(a["link"])
        unique_articles.append(a)

# 取前15条
selected = unique_articles[:15]

# 构建邮件内容
now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
if selected:
    lines = [f"以下为今日宏观相关新闻，共{len(selected)}条（北京时间 {now_str}）"]
    for i, a in enumerate(selected, 1):
        lines.append(f"{i}. [{a['title']}]({a['link']})")
    body = "\n".join(lines)
    count = len(selected)
else:
    body = "今日暂无宏观新闻，请稍后重试。"
    count = 0

# 发送邮件
def send_email(content, count):
    now = datetime.now()
    period = "早间" if now.hour < 11 else ("午间" if now.hour < 16 else "晚间")
    subject = f"📰 宏观新闻 {period}简报（{count}条） - {now.strftime('%m-%d %H:%M')}"
    msg = MIMEMultipart("alternative")
    msg["From"] = SEND_EMAIL
    msg["To"] = RECEIVE_EMAIL
    msg["Subject"] = subject
    html = f"""<html><body style="font-family:Microsoft YaHei; font-size:15px; line-height:1.8;">
{content.replace(chr(10), '<br>')}
<br><hr>
<p style="color:gray; font-size:12px;">本邮件由自动化脚本生成，仅供参考。</p >
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
    print(f"[{datetime.now()}] 开始采集宏观新闻...")
    send_email(body, count)
    print("结束。")
