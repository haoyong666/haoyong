import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
import json
import re

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
SEND_EMAIL = os.environ["SEND_EMAIL"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
RECEIVE_EMAIL = os.environ["RECEIVE_EMAIL"]

# ===== 用财联社电报接口（免费、实时、中文）=====
def fetch_cls_news(max_count=60):
    """抓取财联社电报最新新闻（不需要API Key）"""
    url = "https://www.cls.cn/api/sw?app=CailianpressWeb&os=web&sv=8.4.6"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.cls.cn/telegraph",
    }
    params = {
        "type": "telegram",  # 电报快讯
        "keyword": "",
        "page": 0,
        "pageSize": max_count,
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        data = resp.json()
        if data.get("error") == 0 and "data" in data:
            articles = []
            for item in data["data"]:
                title = item.get("content", "").strip()
                if not title:
                    continue
                ctime = datetime.fromtimestamp(item.get("ctime", 0)).strftime("%Y-%m-%d %H:%M")
                link = f"https://www.cls.cn/detail/{item.get('id', '')}"
                summary = title[:100]  # 摘要就是前100字
                articles.append({
                    "title": title,
                    "link": link,
                    "published": ctime,
                    "summary": summary
                })
            return articles
        else:
            print("财联社接口返回异常")
            return []
    except Exception as e:
        print(f"抓取财联社失败: {e}")
        return []

# ===== 采集新闻 =====
all_news = fetch_cls_news(60)

# 简单去重（按标题）
seen = set()
unique_news = []
for n in all_news:
    if n["title"] not in seen:
        seen.add(n["title"])
        unique_news.append(n)

# 只保留前60条
unique_news = unique_news[:60]

def generate_report(articles):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    if not articles:
        return "今日暂无相关宏观新闻。", 0

    news_text = ""
    for i, a in enumerate(articles):
        news_text += f"{i+1}. [{a['title'][:80]}]({a['link']}) ({a['published']})\n"

    prompt = f"""当前北京时间：{now_str}。以下是财联社今日实时电报新闻列表（共{len(articles)}条），请直接从中挑选出对国内股市有重要影响的宏观、政策、经济类新闻，最多15条。要求：
1. 每条新闻用一句话总结，不超过50字，并保留原文链接。
2. 开头写：“以下为今日宏观利好新闻，共X条”，并注明生成时间：{now_str}。
3. 如果实在没有相关新闻，请回复“今日暂无相关宏观新闻”。
4. 只从下面列表中选择，不要使用旧知识。

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
    print(f"[{datetime.now()}] 开始采集财联社电报...")
    report, count = generate_report(unique_news)
    print(f"简报生成完毕，共{count}条，发送中...")
    send_email(report, count)
    print("结束。")
